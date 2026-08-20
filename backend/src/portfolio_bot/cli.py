"""The `pb` command line entry point.

Subcommands that are not built yet are placeholders. Each one names the roadmap item that
will implement it, so running `pb` is an honest description of how much of the pipeline
exists.
"""

from __future__ import annotations

import argparse
import sys

import psycopg
from pydantic import ValidationError

from portfolio_bot import __version__
from portfolio_bot.db.migrate import MigrationError, run_migrations
from portfolio_bot.logging_config import configure_logging, get_logger
from portfolio_bot.settings import Settings, get_settings

# Subcommand name -> (description, roadmap item that implements it).
PLANNED_COMMANDS: dict[str, tuple[str, str]] = {
    "ingest": ("Chunk, embed, and index everything in content/", "2.5"),
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

    description, item = PLANNED_COMMANDS[args.command]
    print(f"pb {args.command}: not implemented yet.")
    print(f"  {description}")
    print(f"  Lands in roadmap item {item}.")
    return 0
