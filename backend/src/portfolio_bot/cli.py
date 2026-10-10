"""The `pb` command line entry point.

Subcommands that are not built yet are placeholders. Each one names the roadmap item that
will implement it, so running `pb` is an honest description of how much of the pipeline
exists.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg
from pydantic import ValidationError

from portfolio_bot import __version__
from portfolio_bot.db.migrate import MigrationError, run_migrations
from portfolio_bot.db.pool import close_pool, connection
from portfolio_bot.ingest.embedder import Embedder, SentenceTransformerEmbedder
from portfolio_bot.ingest.pipeline import IngestReport, ingest
from portfolio_bot.logging_config import configure_logging, get_logger
from portfolio_bot.retrieval.base import RetrievalStrategy, ScoredChunk
from portfolio_bot.retrieval.dense import DenseRetriever
from portfolio_bot.settings import Settings, get_settings

# Strategies `pb search --strategy` accepts. Lexical and hybrid join as they are built.
SEARCH_STRATEGIES = ("dense",)
# How much of a chunk's first line `pb search` shows, in characters.
SNIPPET_WIDTH = 100

# Subcommand name -> (description, roadmap item that implements it).
PLANNED_COMMANDS: dict[str, tuple[str, str]] = {
    "ask": ("Answer a question from retrieved context", "4.5"),
    "eval": ("Measure retrieval quality against the eval set", "3.6"),
}


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser, including one subparser per command."""
    parser = argparse.ArgumentParser(
        prog="pb",
        description="Command line interface to the portfolio bot pipeline.",
    )
    parser.add_argument("--version", action="version", version=f"pb {__version__}")

    subparsers = parser.add_subparsers(dest="command", metavar="command")
    subparsers.add_parser("migrate", help="Apply pending database migrations")

    ingest_parser = subparsers.add_parser(
        "ingest", help="Chunk, embed, and index everything in content/"
    )
    ingest_parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Corpus directory to mirror into the database (default: CONTENT_DIR). "
        "Documents stored from files not under it are deleted.",
    )
    ingest_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-process every document, changed or not. Needed after changing chunk settings.",
    )
    ingest_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without embedding or writing anything",
    )

    search_parser = subparsers.add_parser("search", help="Retrieve ranked chunks for a query")
    search_parser.add_argument("query", help="The question to search for")
    search_parser.add_argument(
        "--strategy",
        choices=SEARCH_STRATEGIES,
        default="dense",
        help="How to rank chunks (default: dense)",
    )
    search_parser.add_argument(
        "--k",
        type=_positive_int,
        default=None,
        help="How many chunks to return (default: TOP_K)",
    )

    for name, (description, item) in PLANNED_COMMANDS.items():
        subparsers.add_parser(name, help=f"{description} (roadmap {item})")

    return parser


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {number}")
    return number


def _build_embedder(settings: Settings) -> SentenceTransformerEmbedder:
    return SentenceTransformerEmbedder(
        settings.embedding_model_name,
        settings.embedding_model_revision,
        settings.embedding_batch_size,
        query_instruction=settings.embedding_query_instruction,
    )


def command_migrate(settings: Settings) -> int:
    """Apply pending migrations, reporting what was applied.

    Returns 1 with a readable message on the two failures a person actually hits: the
    database is not running, and a committed migration was edited.
    """
    try:
        applied = run_migrations(settings.database_url)
    except psycopg.OperationalError as error:
        print("Cannot reach the database. Is it running? Try 'make db-up'.", file=sys.stderr)
        print(f"  {error}", file=sys.stderr)
        return 1
    except MigrationError as error:
        print(f"Migration error: {error}", file=sys.stderr)
        return 1

    if not applied:
        print("no pending migrations")
        return 0

    for filename in applied:
        print(f"applied {filename}")
    plural = "s" if len(applied) > 1 else ""
    print(f"applied {len(applied)} migration{plural}")
    return 0


def command_ingest(
    settings: Settings, args: argparse.Namespace, embedder: Embedder | None = None
) -> int:
    """Mirror the corpus directory into the database and report what changed.

    `embedder` is for tests, which pass a fake so nothing downloads a model.

    Returns 1 when the database is unreachable or any document failed, so a script or CI job
    running this cannot mistake a partial ingest for a complete one.
    """
    root: Path = args.path if args.path is not None else settings.content_dir
    if not root.is_dir():
        print(f"Corpus directory not found: {root}", file=sys.stderr)
        return 1

    if embedder is None:
        embedder = _build_embedder(settings)

    try:
        with connection() as conn:
            report = ingest(
                conn,
                root,
                embedder,
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
                force=args.force,
                dry_run=args.dry_run,
            )
    except psycopg.OperationalError as error:
        print("Cannot reach the database. Is it running? Try 'make db-up'.", file=sys.stderr)
        print(f"  {error}", file=sys.stderr)
        return 1
    finally:
        close_pool()

    _print_ingest_report(report, dry_run=args.dry_run)
    return 1 if report.failed else 0


def _print_ingest_report(report: IngestReport, *, dry_run: bool) -> None:
    verb = "would process" if dry_run else "processed"
    for source_path in report.processed:
        print(f"{verb} {source_path}")
    for source_path in report.deleted:
        print(f"{'would delete' if dry_run else 'deleted'} {source_path}")
    for source_path, reason in report.failed:
        print(f"failed {source_path}: {reason}", file=sys.stderr)

    print(
        f"documents: {len(report.processed)} {verb}, {len(report.unchanged)} unchanged, "
        f"{len(report.deleted)} {'to delete' if dry_run else 'deleted'}, "
        f"{len(report.failed)} failed"
    )
    if dry_run:
        print(f"chunks: {report.chunks_written} would be written")
    else:
        print(f"chunks: {report.chunks_written} written, {report.chunks_embedded} embedded")


def command_search(
    settings: Settings, args: argparse.Namespace, embedder: Embedder | None = None
) -> int:
    """Print the chunks a strategy ranks highest for a query.

    `embedder` is for tests, which pass a fake so nothing downloads a model.

    Returns 2 for a blank query, matching argparse's code for bad input, and 1 when the
    database is unreachable.
    """
    query: str = args.query.strip()
    if not query:
        print("The query is empty.", file=sys.stderr)
        return 2
    k: int = args.k if args.k is not None else settings.top_k
    if embedder is None:
        embedder = _build_embedder(settings)

    try:
        with connection() as conn:
            strategy: RetrievalStrategy = DenseRetriever(
                conn, embedder, ef_search=settings.hnsw_ef_search
            )
            results = strategy.retrieve(query, k)
    except psycopg.OperationalError as error:
        print("Cannot reach the database. Is it running? Try 'make db-up'.", file=sys.stderr)
        print(f"  {error}", file=sys.stderr)
        return 1
    finally:
        close_pool()

    # Collapsed to one line, so a pasted multi-line query cannot push the results around.
    print(f'{strategy.name}, k={k}: "{" ".join(query.split())}"')
    if not results:
        print("No results. Has the corpus been ingested? Try 'pb ingest'.")
        return 0
    for result in results:
        print()
        _print_result(result)
    return 0


def _print_result(result: ScoredChunk) -> None:
    rank = result.provenance[0].rank
    location = " > ".join([result.chunk.title, *result.chunk.heading_path])
    print(f"{rank:>3}  {result.score:.3f}  {location}")
    print(f"{'':>3}  {'':>5}  {_first_line(result.chunk.text)}")


def _first_line(text: str) -> str:
    """The chunk's first line of prose. Heading lines repeat the path printed above it."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    line = next((line for line in lines if not line.startswith("#")), lines[0] if lines else "")
    if len(line) > SNIPPET_WIDTH:
        return line[: SNIPPET_WIDTH - 3] + "..."
    return line


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit code.

    Returns rather than raises, so tests can call this directly without subprocesses or
    catching SystemExit. argparse signals --help, --version, and bad input by raising
    SystemExit, so those are converted back into return codes here.
    """
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_signal:
        return int(exit_signal.code or 0)

    if args.command is None:
        parser.print_help()
        return 0

    # Settings are loaded only once a real command runs, so --help and --version work on
    # a machine with no .env at all.
    try:
        settings = get_settings()
    except ValidationError as error:
        print("Configuration error. Compare your .env against .env.example.", file=sys.stderr)
        print(error, file=sys.stderr)
        return 1

    configure_logging(settings)
    logger = get_logger(__name__)
    logger.debug("running command", extra={"command": args.command})

    if args.command == "migrate":
        return command_migrate(settings)
    if args.command == "ingest":
        return command_ingest(settings, args)
    if args.command == "search":
        return command_search(settings, args)

    description, item = PLANNED_COMMANDS[args.command]
    print(f"pb {args.command}: not implemented yet.")
    print(f"  {description}")
    print(f"  Lands in roadmap item {item}.")
    return 0
