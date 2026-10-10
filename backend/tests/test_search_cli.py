"""`pb search` validates its input and prints ranked chunks readably."""

import psycopg
import pytest
from psycopg.rows import dict_row

from portfolio_bot.cli import PLANNED_COMMANDS, build_parser, command_search, main
from portfolio_bot.db.migrate import run_migrations
from portfolio_bot.ingest.chunker import chunk_document
from portfolio_bot.ingest.embedder import FakeEmbedder
from portfolio_bot.ingest.loader import read_document
from portfolio_bot.ingest.pipeline import embedding_text, ingest
from portfolio_bot.settings import get_settings

DOCUMENT = "---\ntitle: Abroadly\n---\n\n## Search\n\nI built the search index.\n"


def search(settings, argv, embedder=None):
    args = build_parser().parse_args(["search", *argv])
    return command_search(settings, args, embedder=embedder or FakeEmbedder())


def test_search_is_implemented_not_planned(capsys):
    assert "search" not in PLANNED_COMMANDS
    main([])
    assert "search" in capsys.readouterr().out


@pytest.mark.parametrize("k", ["0", "-1", "two"])
def test_rejects_a_k_that_is_not_a_positive_integer(k):
    assert main(["search", "query", "--k", k]) == 2


def test_rejects_an_unknown_strategy():
    assert main(["search", "query", "--strategy", "telepathy"]) == 2


def test_rejects_a_blank_query(capsys):
    assert search(get_settings(), ["   "]) == 2
    assert "empty" in capsys.readouterr().err


def test_reports_an_unreachable_database(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:1/test")
    monkeypatch.setenv("DB_POOL_TIMEOUT", "1")
    get_settings.cache_clear()

    assert search(get_settings(), ["query"]) == 1
    assert "make db-up" in capsys.readouterr().err


@pytest.fixture
def search_database(empty_database, monkeypatch):
    """A migrated database the CLI reaches through settings, the way it does for real.

    Not the `db` fixture: the CLI opens its own pooled connection, which would not see rows
    written inside that fixture's uncommitted transaction.
    """
    run_migrations(empty_database)
    monkeypatch.setenv("DATABASE_URL", empty_database)
    get_settings.cache_clear()
    return empty_database


@pytest.mark.database
def test_says_so_when_nothing_is_indexed(search_database, capsys):
    assert search(get_settings(), ["query"]) == 0
    assert "pb ingest" in capsys.readouterr().out


@pytest.mark.database
def test_finds_and_prints_an_ingested_chunk(search_database, tmp_path, capsys):
    settings = get_settings()
    (tmp_path / "abroadly.md").write_text(DOCUMENT)
    with psycopg.connect(search_database, row_factory=dict_row) as conn:
        ingest(conn, tmp_path, FakeEmbedder(), chunk_size=1000, chunk_overlap=0)

    # The fake embeds a query exactly as it embeds a chunk, so querying with the text the
    # chunk was embedded from lands on the same vector: rank 1, similarity 1.
    document = read_document(tmp_path, tmp_path / "abroadly.md")
    [chunk] = chunk_document(document.text, document.body_start, 1000, 0)
    query = embedding_text(document.title, chunk)

    assert search(settings, [query, "--k", "3"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("dense, k=3: ")
    assert lines[2].split() == ["1", "1.000", "Abroadly", ">", "Search"]
    assert lines[3].strip() == "I built the search index."


@pytest.mark.database
def test_searches_by_keyword_with_the_lexical_strategy(search_database, tmp_path, capsys):
    (tmp_path / "abroadly.md").write_text(DOCUMENT)
    with psycopg.connect(search_database, row_factory=dict_row) as conn:
        ingest(conn, tmp_path, FakeEmbedder(), chunk_size=1000, chunk_overlap=0)

    assert search(get_settings(), ["Who built the index?", "--strategy", "lexical"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == 'lexical, k=5: "Who built the index?"'
    assert lines[2].split()[0] == "1"
    assert lines[2].split()[2:] == ["Abroadly", ">", "Search"]
    assert lines[3].strip() == "I built the search index."
