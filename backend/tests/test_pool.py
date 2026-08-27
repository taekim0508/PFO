"""Tests for the connection pool.

Everything here runs against a real throwaway database with the schema applied. The pool's
whole job is managing real connections, so a mocked one would assert my beliefs about
psycopg rather than test anything.

The exception is the unreachable-database test, which needs no server precisely because it
is checking what happens when there is not one.
"""

from __future__ import annotations

import pytest
from psycopg_pool import PoolTimeout

from portfolio_bot.db.migrate import run_migrations
from portfolio_bot.db.pool import (
    close_pool,
    connection,
    create_pool,
    get_pool,
    transaction,
)
from portfolio_bot.settings import get_settings

INSERT_DOCUMENT = "INSERT INTO documents (source_path, title, content_hash) VALUES (%s, 'T', 'h')"


@pytest.fixture
def pooled_database(empty_database, monkeypatch):
    """Point the process-wide pool at a throwaway database that has the schema applied.

    The pool reads its URL from settings, so redirecting it means setting the environment
    and clearing the settings cache. Both sides close the pool: on the way in so no test
    inherits one built against another database, on the way out so connections are not left
    open against a database that is about to be dropped.
    """
    run_migrations(empty_database)

    close_pool()
    monkeypatch.setenv("DATABASE_URL", empty_database)
    get_settings.cache_clear()

    yield empty_database

    close_pool()
    get_settings.cache_clear()


def document_count(database_url: str) -> int:
    """Count documents on a connection of its own, outside whatever the test is doing."""
    import psycopg

    with psycopg.connect(database_url) as conn:
        (count,) = conn.execute("SELECT count(*) FROM documents").fetchone()
    return int(count)


@pytest.mark.database
def test_a_query_returns_rows_keyed_by_column_name(pooled_database):
    with connection() as conn:
        row = conn.execute("SELECT 1 AS id, 'some text' AS text").fetchone()

    # A tuple would have made this row[0] and row[1], which silently follows the select list
    # if anyone ever reorders it.
    assert row == {"id": 1, "text": "some text"}


@pytest.mark.database
def test_the_pool_is_built_once(pooled_database):
    assert get_pool() is get_pool()


@pytest.mark.database
def test_closing_the_pool_is_not_a_one_way_door(pooled_database):
    first = get_pool()
    close_pool()

    second = get_pool()

    assert second is not first
    with connection() as conn:
        assert conn.execute("SELECT 1 AS n").fetchone() == {"n": 1}


@pytest.mark.database
def test_a_connection_is_returned_to_the_pool(pooled_database, monkeypatch):
    # One connection and a short timeout, so a connection that is never given back cannot
    # hide behind a pool with nine spares.
    monkeypatch.setenv("DB_POOL_MIN_SIZE", "1")
    monkeypatch.setenv("DB_POOL_MAX_SIZE", "1")
    monkeypatch.setenv("DB_POOL_TIMEOUT", "3")
    get_settings.cache_clear()
    close_pool()

    with connection() as conn:
        conn.execute("SELECT 1")

    # Blocks for three seconds and then fails if the first block kept the connection.
    with connection() as conn:
        assert conn.execute("SELECT 2 AS n").fetchone() == {"n": 2}


@pytest.mark.database
def test_a_nested_connection_reuses_the_outer_one(pooled_database):
    with connection() as outer, connection() as inner:
        assert inner is outer


@pytest.mark.database
def test_a_read_inside_a_transaction_sees_that_transaction_s_writes(pooled_database):
    # The practical reason nesting reuses the connection. On a second connection this read
    # would return zero, because the insert has not been committed yet.
    with transaction() as conn:
        conn.execute(INSERT_DOCUMENT, ("content/a.md",))

        with connection() as same:
            (row,) = same.execute("SELECT count(*) AS n FROM documents").fetchall()

    assert row == {"n": 1}


@pytest.mark.database
def test_a_transaction_commits_on_a_clean_exit(pooled_database):
    with transaction() as conn:
        conn.execute(INSERT_DOCUMENT, ("content/a.md",))

    assert document_count(pooled_database) == 1


@pytest.mark.database
def test_a_transaction_rolls_back_when_the_body_raises(pooled_database):
    with pytest.raises(RuntimeError, match="deliberate"), transaction() as conn:
        conn.execute(INSERT_DOCUMENT, ("content/a.md",))
        raise RuntimeError("deliberate")

    assert document_count(pooled_database) == 0


@pytest.mark.database
def test_a_nested_transaction_rolls_back_to_a_savepoint(pooled_database):
    # The behavior connection() alone cannot give: the inner block fails and is undone on
    # its own, and the surrounding work still commits.
    with transaction() as conn:
        conn.execute(INSERT_DOCUMENT, ("content/outer.md",))

        with pytest.raises(RuntimeError, match="deliberate"), transaction() as inner:
            inner.execute(INSERT_DOCUMENT, ("content/inner.md",))
            raise RuntimeError("deliberate")

    with connection() as conn:
        rows = conn.execute("SELECT source_path FROM documents").fetchall()

    assert [row["source_path"] for row in rows] == ["content/outer.md"]


@pytest.mark.database
def test_the_pool_sizes_come_from_settings(pooled_database, monkeypatch):
    monkeypatch.setenv("DB_POOL_MIN_SIZE", "2")
    monkeypatch.setenv("DB_POOL_MAX_SIZE", "3")
    get_settings.cache_clear()
    close_pool()

    pool = get_pool()

    assert (pool.min_size, pool.max_size) == (2, 3)


def test_an_unreachable_database_fails_when_the_pool_is_built(monkeypatch):
    # No database marker: this needs Postgres to be absent, not present. Port 1 refuses
    # immediately, and the short timeout keeps the retry loop from stretching the suite.
    monkeypatch.setenv("DB_POOL_TIMEOUT", "2")
    get_settings.cache_clear()

    with pytest.raises(PoolTimeout):
        create_pool("postgresql://nobody:nobody@127.0.0.1:1/nothing")
