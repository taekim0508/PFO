"""The `pb` command line entry point.

Every subcommand is a placeholder. Each one names the roadmap item that will implement
it, so running `pb` is an honest description of how much of the pipeline exists.
"""

from __future__ import annotations

import argparse

from portfolio_bot import __version__

# Subcommand name -> (description, roadmap item that implements it).
PLANNED_COMMANDS: dict[str, tuple[str, str]] = {
    "ingest": ("Chunk, embed, and index everything in content/", "2.5"),
    "search": ("Retrieve ranked chunks for a query", "3.5"),
    "ask": ("Answer a question from retrieved context", "4.5"),
    "eval": ("Measure retrieval quality against the eval set", "3.6"),
}


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser, including one subparser per planned command."""
    parser = argparse.ArgumentParser(
        prog="pb",
        description="Command line interface to the portfolio bot pipeline.",
    )
    parser.add_argument("--version", action="version", version=f"pb {__version__}")

    subparsers = parser.add_subparsers(dest="command", metavar="command")
    for name, (description, item) in PLANNED_COMMANDS.items():
        subparsers.add_parser(name, help=f"{description} (roadmap {item})")

    return parser


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

    description, item = PLANNED_COMMANDS[args.command]
    print(f"pb {args.command}: not implemented yet.")
    print(f"  {description}")
    print(f"  Lands in roadmap item {item}.")
    return 0
