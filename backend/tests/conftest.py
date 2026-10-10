"""Test fixtures shared by the whole backend suite.

Two kinds of database are on offer, because the tests want different things.

`empty_database` is a database with nothing in it, created and dropped per test. Migration
tests need it: their subject is what happens when migrations are applied, so they cannot
start from a database where the tables already exist.

`migrated_database` is built once for the entire run, with every migration applied, and
`db` hands out a connection to it wrapped in a transaction that is always rolled back.
Everything from phase 2 on wants that one. The database is built once instead of per test,
and each test still starts from a clean one because nothing it writes is ever committed.

Nothing here ever touches the developer's real database. The URL from settings is used only
to reach the server; every fixture then creates a randomly named database of its own
alongside it. CI has no such database to borrow in the first place, which is the constraint
that settles the question.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from portfolio_bot.db.migrate import run_migrations
from portfolio_bot.settings import get_settings


def pytest_addoption(parser):
    parser.addoption(
        "--run-model",
        action="store_true",
        help="Run tests marked `model`, which download and run the real embedding model.",
    )


def pytest_collection_modifyitems(config, items):
    """Skip `model` tests unless asked for, so the default suite never downloads a model."""
    if config.getoption("--run-model"):
        return
    skip = pytest.mark.skip(reason="needs the real embedding model; run with --run-model")
    for item in items:
        if "model" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def isolated_settings(request, monkeypatch):
    """Give every test the required settings, independent of the developer's .env.

    Environment variables take precedence over the .env file, so setting them here makes
    the suite produce the same result on a machine with a filled-in .env and on a clean
    clone with none. The cache is cleared on both sides so no test inherits another
    test's settings object.

    Tests marked `database` are the exception: they need a DATABASE_URL that points at a
    Postgres that actually exists, so they keep the developer's real one. They still get
    the cache cleared, and they never touch that database directly; they use it only to
    reach the server and create a throwaway database of their own.
    """
    if request.node.get_closest_marker("database") is None:
        monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
    monkeypatch.setenv("MODEL_API_KEY", "test-key")

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def restore_logging():
    """Put the root logger back the way it was after every test.

    `main()` configures logging, which installs a handler on whatever sys.stderr is at the
    time. Under pytest that is the current test's capture stream, closed once the test
    ends, so without this every later test that logs writes into a closed file.
    """
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


@contextmanager
def _throwaway_database() -> Iterator[str]:
    """Create a randomly named database, yield its URL, and drop it afterwards.

    The developer's DATABASE_URL is read only to reach the server and is never connected to.
    This opens the `postgres` maintenance database alongside it instead.

    Settings are read directly rather than through the isolated_settings fixture above,
    because pytest builds session-scoped fixtures before function-scoped ones and will not
    let a session-scoped fixture depend on a function-scoped one. The cache is cleared right
    after so no cached settings object outlives this call.
    """
    database_url = get_settings().database_url
    get_settings.cache_clear()

    parts = conninfo_to_dict(database_url)
    maintenance_url = make_conninfo(**{**parts, "dbname": "postgres"})

    try:
        with psycopg.connect(maintenance_url, autocommit=True, connect_timeout=3):
            pass
    except psycopg.OperationalError as error:
        pytest.skip(f"Postgres is not reachable, run 'make db-up' first. ({error})")

    name = f"pb_test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(maintenance_url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))

    try:
        yield make_conninfo(**{**parts, "dbname": name})
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as conn:
            # Anything still connected would make DROP DATABASE fail, and a pool that was
            # not closed is the usual culprit.
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (name,),
            )
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))


@pytest.fixture
def empty_database(request) -> Iterator[str]:
    """A database with no tables at all, for one test."""
    if request.node.get_closest_marker("database") is None:
        raise RuntimeError("empty_database requires the 'database' marker")

    with _throwaway_database() as database_url:
        yield database_url


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[str]:
    """One database with every migration applied, built once for the whole run.

    Tests do not name this directly. They ask for `db`, which builds on it.
    """
    with _throwaway_database() as database_url:
        run_migrations(database_url)
        yield database_url


@pytest.fixture
def db(request, migrated_database) -> Iterator[psycopg.Connection[dict[str, Any]]]:
    """A connection to the migrated database, inside a transaction that always rolls back.

    The test writes whatever it likes and reads it back normally. Nothing is committed, so
    the database is clean again for the next test whether this one passed or failed. That
    unconditional rollback is the point: a plain connection commits on success, which means
    a passing test would be the one that leaves rows behind.

    Rows come back keyed by column name, matching what the pool hands production code, so a
    test reads the way the code it tests does.
    """
    if request.node.get_closest_marker("database") is None:
        raise RuntimeError("db requires the 'database' marker")

    with (
        psycopg.connect(migrated_database, row_factory=dict_row) as conn,
        conn.transaction(force_rollback=True),
    ):
        yield conn
