"""The `pb` entry point dispatches and reports its own incompleteness."""

import pytest

from portfolio_bot.cli import PLANNED_COMMANDS, main


def test_no_arguments_prints_help_and_succeeds(capsys):
    assert main([]) == 0
    assert capsys.readouterr().out.strip()


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
