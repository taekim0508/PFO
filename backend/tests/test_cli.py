"""The `pb` entry point dispatches and reports its own incompleteness."""

import pytest

from portfolio_bot.cli import PLANNED_COMMANDS, build_parser, command_ingest, main
from portfolio_bot.db.migrate import run_migrations
from portfolio_bot.ingest.embedder import FakeEmbedder
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


def test_ingest_is_implemented_not_planned():
    assert "ingest" not in PLANNED_COMMANDS


def test_ingest_reports_a_missing_corpus_directory(tmp_path, capsys):
    assert main(["ingest", "--path", str(tmp_path / "nowhere")]) == 1
    assert "not found" in capsys.readouterr().err


def test_ingest_reports_an_unreachable_database(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:1/test")
    monkeypatch.setenv("DB_POOL_TIMEOUT", "1")
    get_settings.cache_clear()

    assert main(["ingest", "--path", str(tmp_path), "--dry-run"]) == 1
    assert "make db-up" in capsys.readouterr().err


@pytest.mark.database
def test_ingest_runs_end_to_end_and_reports_counts(empty_database, tmp_path, monkeypatch, capsys):
    run_migrations(empty_database)
    monkeypatch.setenv("DATABASE_URL", empty_database)
    get_settings.cache_clear()
    (tmp_path / "a.md").write_text("---\ntitle: A\n---\n\n## One\n\nText.\n")
    (tmp_path / "b.md").write_text("no front matter\n")

    args = build_parser().parse_args(["ingest", "--path", str(tmp_path)])
    code = command_ingest(get_settings(), args, embedder=FakeEmbedder())

    captured = capsys.readouterr()
    assert code == 1
    assert "processed a.md" in captured.out
    assert "documents: 1 processed, 0 unchanged, 0 deleted, 1 failed" in captured.out
    assert "chunks: 1 written, 1 embedded" in captured.out
    assert "failed b.md" in captured.err
