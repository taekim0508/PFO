"""The `pb` command line entry point.

Subcommands that are not built yet are placeholders. Each one names the roadmap item that
will implement it, so running `pb` is an honest description of how much of the pipeline
exists.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

import psycopg
from pydantic import ValidationError

from portfolio_bot import __version__
from portfolio_bot.db.migrate import MigrationError, run_migrations
from portfolio_bot.db.pool import close_pool, connection
from portfolio_bot.evaluation.questions import EvalQuestion, EvalSetError, load_questions
from portfolio_bot.evaluation.runner import EvalReport, check_sections, evaluate, known_sections
from portfolio_bot.generation.client import (
    Message,
    ModelClient,
    ModelError,
    ModelRequestError,
    ModelUnavailableError,
    build_model_client,
)
from portfolio_bot.ingest.embedder import Embedder, SentenceTransformerEmbedder
from portfolio_bot.ingest.pipeline import IngestReport, ingest
from portfolio_bot.logging_config import configure_logging, get_logger
from portfolio_bot.retrieval.base import RetrievalStrategy, ScoredChunk
from portfolio_bot.retrieval.factory import STRATEGY_NAMES, build_strategy
from portfolio_bot.settings import Settings, get_settings

# How much of a chunk's first line `pb search` shows, in characters.
SNIPPET_WIDTH = 100

# Subcommand name -> (description, roadmap item that implements it).
# Short, so a ping measures the round trip rather than how long the model can write for.
PING_PROMPT = "Reply with one word: ready."

PLANNED_COMMANDS: dict[str, tuple[str, str]] = {
    "ask": ("Answer a question from retrieved context", "4.5"),
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
        choices=STRATEGY_NAMES,
        default="dense",
        help="How to rank chunks (default: dense)",
    )
    search_parser.add_argument(
        "--k",
        type=_positive_int,
        default=None,
        help="How many chunks to return (default: TOP_K)",
    )

    eval_parser = subparsers.add_parser(
        "eval", help="Measure retrieval quality against the evaluation set"
    )
    eval_commands = eval_parser.add_subparsers(dest="eval_command", metavar="eval_command")
    eval_run = eval_commands.add_parser("run", help="Score one strategy, question by question")
    eval_run.add_argument("--strategy", choices=STRATEGY_NAMES, required=True)
    eval_compare = eval_commands.add_parser("compare", help="Score every strategy in one table")
    for eval_command in (eval_run, eval_compare):
        eval_command.add_argument(
            "--k", type=_positive_int, default=None, help="Cutoff (default: TOP_K)"
        )
        eval_command.add_argument(
            "--file", type=Path, default=None, help="Evaluation set (default: EVAL_SET_PATH)"
        )
    eval_commands.add_parser(
        "sections", help="List every section, in the form the evaluation set expects"
    )

    model_parser = subparsers.add_parser("model", help="Check the generation model")
    model_commands = model_parser.add_subparsers(dest="model_command", metavar="model_command")
    ping_parser = model_commands.add_parser(
        "ping", help="Send one short prompt and print the reply, the model, and the latency"
    )
    ping_parser.add_argument(
        "--prompt", default=PING_PROMPT, help=f'What to send (default: "{PING_PROMPT}")'
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
            strategy: RetrievalStrategy = build_strategy(args.strategy, conn, embedder, settings)
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
    for rank, result in enumerate(results, start=1):
        print()
        _print_result(rank, result, strategy.name)
    return 0


def _print_result(rank: int, result: ScoredChunk, strategy: str) -> None:
    """Rank, score, and location, then the first line of prose underneath.

    The rank is the position in this list. When the result came from other strategies, as a
    fused one does, the rank each of them gave it is printed after the location, so a chunk
    only one arm found is as visible as one both did.
    """
    location = " > ".join([result.chunk.title, *result.chunk.heading_path])
    line = f"{rank:>3}  {result.score:.4f}  {location}"
    if any(p.strategy != strategy for p in result.provenance):
        line += "  [" + ", ".join(f"{p.strategy} {p.rank}" for p in result.provenance) + "]"
    print(line)
    print(f"{'':>3}  {'':>6}  {_first_line(result.chunk.text)}")


def _first_line(text: str) -> str:
    """The chunk's first line of prose. Heading lines repeat the path printed above it."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    line = next((line for line in lines if not line.startswith("#")), lines[0] if lines else "")
    if len(line) > SNIPPET_WIDTH:
        return line[: SNIPPET_WIDTH - 3] + "..."
    return line


def command_eval(
    settings: Settings, args: argparse.Namespace, embedder: Embedder | None = None
) -> int:
    """Run `pb eval run`, `compare`, or `sections`.

    `embedder` is for tests, which pass a fake so nothing downloads a model.

    Returns 1 when the file is missing or malformed, names a section the corpus does not
    have, or the database is unreachable.
    """
    if args.eval_command is None:
        print("usage: pb eval {run,compare,sections}. See 'pb eval --help'.", file=sys.stderr)
        return 2

    questions: list[EvalQuestion] = []
    if args.eval_command != "sections":
        path: Path = args.file if args.file is not None else settings.eval_set_path
        if not path.is_file():
            print(f"Evaluation set not found: {path}", file=sys.stderr)
            return 1
        try:
            questions = load_questions(path)
        except EvalSetError as error:
            print(f"Problems in {path}:\n{error}", file=sys.stderr)
            return 1
        if not questions:
            print(f"No questions yet. Add some to {path}.", file=sys.stderr)
            return 1
    if embedder is None:
        embedder = _build_embedder(settings)

    try:
        with connection() as conn:
            known = known_sections(conn)
            if args.eval_command == "sections":
                for section in sorted(known):
                    print(section)
                return 0
            check_sections(questions, known)
            k: int = args.k if args.k is not None else settings.top_k
            names = [args.strategy] if args.eval_command == "run" else list(STRATEGY_NAMES)
            reports = [
                evaluate(build_strategy(name, conn, embedder, settings), questions, k)
                for name in names
            ]
    except psycopg.OperationalError as error:
        print("Cannot reach the database. Is it running? Try 'make db-up'.", file=sys.stderr)
        print(f"  {error}", file=sys.stderr)
        return 1
    except EvalSetError as error:
        print(f"Problems in the evaluation set:\n{error}", file=sys.stderr)
        return 1
    finally:
        close_pool()

    if args.eval_command == "run":
        _print_eval_run(reports[0])
    else:
        _print_eval_compare(reports)
    return 0


def _print_eval_run(report: EvalReport) -> None:
    print(f"{report.strategy}, k={report.k}, {len(report.results)} questions")
    print()
    for result in report.results:
        hit = f"rank {result.first_hit}" if result.first_hit else "miss"
        print(f"  {hit:<7}  {result.question.question}")
    print()
    k = report.k
    print(
        f"recall@{k} {report.recall:.3f}   MRR {report.mrr:.3f}   "
        f"precision@{k} {report.precision:.3f}"
    )


def _print_eval_compare(reports: list[EvalReport]) -> None:
    k = reports[0].k
    print(f"k={k}, {len(reports[0].results)} questions")
    print()
    headers = ("strategy", f"recall@{k}", "MRR", f"precision@{k}")
    print(f"{headers[0]:<10}{headers[1]:>12}{headers[2]:>8}{headers[3]:>15}")
    for report in reports:
        print(
            f"{report.strategy:<10}{report.recall:>12.3f}{report.mrr:>8.3f}"
            f"{report.precision:>15.3f}"
        )


def command_model(
    settings: Settings, args: argparse.Namespace, client: ModelClient | None = None
) -> int:
    """Run a `pb model` subcommand. `ping` is the only one.

    `client` is for tests, which pass a fake so nothing calls a real endpoint. Returns 1
    when the endpoint refuses the request or cannot be reached.
    """
    if args.model_command != "ping":
        print("Usage: pb model ping [--prompt TEXT]", file=sys.stderr)
        return 2
    return asyncio.run(_ping(settings, args.prompt, client))


async def _ping(settings: Settings, prompt: str, client: ModelClient | None) -> int:
    # Only a client built here is closed here; one passed in belongs to the caller.
    built = None
    if client is None:
        built = client = build_model_client(settings)
    print(f"{client.model_name} at {settings.model_base_url}")
    started = time.perf_counter()
    try:
        completion = await client.complete([Message(role="user", content=prompt)])
    except ModelRequestError as error:
        print(f"The endpoint refused the request: {error}", file=sys.stderr)
        print("  Check MODEL_NAME and MODEL_API_KEY in .env.", file=sys.stderr)
        return 1
    except ModelUnavailableError as error:
        print(f"Cannot get an answer from {settings.model_base_url}.", file=sys.stderr)
        print(f"  {error}", file=sys.stderr)
        print("  If this is Ollama, is it running? Try 'make model-up'.", file=sys.stderr)
        return 1
    except ModelError as error:
        print(f"The endpoint answered, but not in a readable form: {error}", file=sys.stderr)
        return 1
    finally:
        if built is not None:
            await built.aclose()
    elapsed = time.perf_counter() - started

    tokens = (
        f"{completion.prompt_tokens} in, {completion.completion_tokens} out"
        if completion.prompt_tokens is not None and completion.completion_tokens is not None
        else "not reported"
    )
    print(f"  reply:        {' '.join(completion.text.split())}")
    print(f"  answered by:  {completion.model}")
    print(f"  finish:       {completion.finish_reason}")
    print(f"  tokens:       {tokens}")
    print(f"  latency:      {elapsed:.2f}s")
    return 0


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
    if args.command == "eval":
        return command_eval(settings, args)
    if args.command == "model":
        return command_model(settings, args)

    description, item = PLANNED_COMMANDS[args.command]
    print(f"pb {args.command}: not implemented yet.")
    print(f"  {description}")
    print(f"  Lands in roadmap item {item}.")
    return 0
