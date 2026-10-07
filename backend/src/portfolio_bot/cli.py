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
from portfolio_bot.settings import Settings, get_settings

# Subcommand name -> (description, roadmap item that implements it).
PLANNED_COMMANDS: dict[str, tuple[str, str]] = {
    "search": ("Retrieve ranked chunks for a query", "3.5"),
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
    for name, (description, item) in PLANNED_COMMANDS.items():
        subparsers.add_parser(name, help=f"{description} (roadmap {item})")

    return parser


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
        embedder = SentenceTransformerEmbedder(
            settings.embedding_model_name,
            settings.embedding_model_revision,
            settings.embedding_batch_size,
        )

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

    description, item = PLANNED_COMMANDS[args.command]
    print(f"pb {args.command}: not implemented yet.")
    print(f"  {description}")
    print(f"  Lands in roadmap item {item}.")
    return 0
