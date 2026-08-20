"""The `pb` entry point dispatches and reports its own incompleteness."""

import pytest

from portfolio_bot.cli import PLANNED_COMMANDS, main
from portfolio_bot.settings import get_settings


def test_no_arguments_prints_help_and_succeeds(capsys):
    assert main([]) == 0
    assert capsys.readouterr().out.strip()


def test_migrate_is_implemented_not_planned():
    # It moved out of PLANNED_COMMANDS when the runner landed. If it reappears there, the
    # command is claiming to be unimplemented while doing real work.
    assert "migrate" not in PLANNED_COMMANDS


def test_migrate_is_offered_in_help(capsys):
    main([])
    assert "migrate" in capsys.readouterr().out


def test_migrate_reports_an_unreachable_database(monkeypatch, capsys):
    # Port 1 is never a Postgres, so the connection is refused immediately.
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:1/test")
    get_settings.cache_clear()

    assert main(["migrate"]) == 1
    assert "make db-up" in capsys.readouterr().err


@pytest.mark.parametrize("command", sorted(PLANNED_COMMANDS))
def test_planned_command_reports_not_implemented(command, capsys):
    assert main([command]) == 0

    out = capsys.readouterr().out
    assert command in out
    assert "not implemented" in out


def test_unknown_command_returns_two():
    assert main(["nonsense"]) == 2


def test_help_flag_succeeds():
    assert main(["--help"]) == 0


def test_version_flag_succeeds():
    assert main(["--version"]) == 0
