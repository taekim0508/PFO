"""`pb ask` prints the answer, the passages it cited, and how long it took."""

import psycopg
import pytest
from psycopg.rows import dict_row

from portfolio_bot.cli import build_parser, command_ask, main
from portfolio_bot.db.migrate import run_migrations
from portfolio_bot.generation.ask import NO_CONTEXT_ANSWER
from portfolio_bot.generation.client import FakeModelClient, ModelUnavailableError, TextDelta
from portfolio_bot.ingest.embedder import FakeEmbedder
from portfolio_bot.ingest.pipeline import ingest
from portfolio_bot.settings import get_settings

DOCUMENT = (
    "---\ntitle: Education\n---\n\n## Degrees and dates\n\n"
    "I graduated from Vanderbilt University in May 2026.\n"
)


def ask_cli(argv, client):
    args = build_parser().parse_args(["ask", *argv])
    return command_ask(get_settings(), args, embedder=FakeEmbedder(), client=client)


def test_rejects_a_blank_question(capsys):
    assert ask_cli(["   "], FakeModelClient()) == 2
    assert "empty" in capsys.readouterr().err


def test_rejects_an_unknown_strategy():
    assert main(["ask", "q", "--strategy", "telepathy"]) == 2


@pytest.fixture
def corpus(empty_database, monkeypatch, tmp_path):
    """One ingested document in a migrated database the CLI reaches through settings."""
    run_migrations(empty_database)
    (tmp_path / "education.md").write_text(DOCUMENT)
    with psycopg.connect(empty_database, row_factory=dict_row) as conn:
        ingest(conn, tmp_path, FakeEmbedder(), chunk_size=1000, chunk_overlap=0)
    monkeypatch.setenv("DATABASE_URL", empty_database)
    get_settings.cache_clear()
    return empty_database


@pytest.mark.database
def test_answers_and_marks_the_cited_passage(corpus, capsys):
    # Lexical finds the chunk by its words, and has no floor, so the fake model is asked.
    client = FakeModelClient(["Tae graduated from Vanderbilt in May 2026 [1]."])

    assert ask_cli(["When did he graduate from Vanderbilt?", "--strategy", "lexical"], client) == 0

    out = capsys.readouterr().out
    assert out.startswith("Tae graduated from Vanderbilt in May 2026 [1].\n")
    assert "Sources (lexical):" in out
    assert "[1] cited  Education > Degrees and dates" in out
    assert "finish stop" in out


@pytest.mark.database
def test_stream_prints_the_same_answer(corpus, capsys):
    client = FakeModelClient(["Tae graduated in May 2026 [1]."])

    assert ask_cli(["Vanderbilt graduation?", "--strategy", "lexical", "--stream"], client) == 0

    assert capsys.readouterr().out.startswith("Tae graduated in May 2026 [1].\n")


@pytest.mark.database
def test_an_unrelated_question_gets_the_fixed_reply_without_the_model(corpus, capsys):
    # The fake embedder's vectors are unrelated to each other, so dense similarity sits far
    # below the floor.
    client = FakeModelClient()

    assert ask_cli(["What is the capital of France?"], client) == 0

    out = capsys.readouterr().out
    assert out.startswith(NO_CONTEXT_ANSWER)
    assert "the model was not asked" in out
    assert client.calls == []


@pytest.mark.database
def test_a_model_failure_exits_1(corpus, capsys):
    class Broken(FakeModelClient):
        async def stream(self, messages, *, temperature=None, max_tokens=None):
            raise ModelUnavailableError("could not reach the model endpoint")
            yield TextDelta("")

    assert ask_cli(["Vanderbilt?", "--strategy", "lexical"], Broken()) == 1
    assert "make model-up" in capsys.readouterr().err


def test_reports_an_unreachable_database(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:1/test")
    monkeypatch.setenv("DB_POOL_TIMEOUT", "1")
    get_settings.cache_clear()

    assert ask_cli(["q"], FakeModelClient()) == 1
    assert "make db-up" in capsys.readouterr().err
