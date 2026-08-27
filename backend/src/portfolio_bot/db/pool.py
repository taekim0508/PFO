"""The one place in the application that opens a database connection.

Opening a Postgres connection is not cheap: a TCP handshake, authentication, and a backend
process forked on the server, tens of milliseconds before a single query runs. A pool opens
a few at startup and lends them out, so that cost is paid once for the life of the process
rather than once per question asked of the chatbot.

The pool is also the single place a connection is configured. The row factory set here is
what makes every query in the project return rows keyed by column name, and later settings
like a statement timeout belong here for the same reason: configured once, impossible to
forget at a call site.

The migration runner deliberately does not use this. A pool amortizes setup across many
short concurrent requests; a migration run is one sequential job that has to work before
the application is wired up at all.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from portfolio_bot.logging_config import get_logger
from portfolio_bot.settings import get_settings

logger = get_logger(__name__)

# Rows arrive as {"id": 1, "text": "..."} rather than (1, "..."). Positional access is fine
# for two columns and becomes a liability once retrieval selects eight and joins: reordering
# the select list silently reassigns every variable, and nothing raises.
PooledConnection = psycopg.Connection[dict[str, Any]]

# Built once per process, behind a lock. functools.lru_cache would have been the obvious
# mirror of get_settings, but it can run the wrapped function twice when two threads call it
# at the same moment, and losing that race leaves a second pool holding real connections
# with nothing left holding a reference to close it. Uvicorn serves requests from a thread
# pool, so this is a live condition rather than a hypothetical one.
_pool: ConnectionPool[PooledConnection] | None = None
_pool_lock = threading.Lock()

# The connection currently lent to this thread or async task, if any. This is what makes
# connection() and transaction() nest: an inner call reuses the connection the outer call
# borrowed instead of taking a second one from the pool. Without it a nested transaction
# would open a separate transaction on a separate connection, which could not see the outer
# transaction's uncommitted writes and would not roll back with it.
_current: ContextVar[PooledConnection | None] = ContextVar("current_connection", default=None)


def create_pool(database_url: str) -> ConnectionPool[PooledConnection]:
    """Build and open a pool against `database_url`.

    Separate from get_pool so tests can point a pool at a throwaway database without going
    through settings. Sizes and timeout still come from settings, since those are tuning
    values and hard rule 8 keeps tuning values in one module.

    The pool is constructed closed and then opened with wait=True, so an unreachable server
    or a wrong password fails here rather than inside whichever query happens to run first.
    """
    settings = get_settings()

    pool: ConnectionPool[PooledConnection] = ConnectionPool(
        conninfo=database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        timeout=settings.db_pool_timeout,
        kwargs={"row_factory": dict_row},
        open=False,
    )
    try:
        pool.open(wait=True, timeout=settings.db_pool_timeout)
    except Exception:
        # open() leaves worker threads running even when it fails to reach the server, and
        # the caller has no reference to close because the constructor never returned.
        pool.close()
        raise

    logger.info(
        "database pool opened",
        extra={"min_size": settings.db_pool_min_size, "max_size": settings.db_pool_max_size},
    )
    return pool


def get_pool() -> ConnectionPool[PooledConnection]:
    """Return the process-wide pool, building it on first use."""
    global _pool

    if _pool is None:
        with _pool_lock:
            # Checked again inside the lock: another thread may have built it while this one
            # waited, and the check outside the lock is what keeps the common case cheap.
            if _pool is None:
                _pool = create_pool(get_settings().database_url)
    return _pool


def close_pool() -> None:
    """Close the process-wide pool and forget it.

    Called from the API's shutdown hook and from test teardown. A later get_pool builds a
    fresh one, so this is not a one-way door.
    """
    global _pool

    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None
            logger.info("database pool closed")


@contextmanager
def connection() -> Iterator[PooledConnection]:
    """Lend a pooled connection for the duration of the block.

    psycopg_pool already commits the block's work on a clean exit and rolls it back on an
    exception, so this adds no behavior of its own beyond nesting. It exists so that nothing
    above this module imports psycopg_pool, which is what keeps replacing the pool a change
    to one file.

    Nested inside another connection() or transaction(), it hands back the connection
    already in use rather than borrowing a second one. Two connections would be two separate
    transactions, and the inner one could not see what the outer one had written.
    """
    existing = _current.get()
    if existing is not None:
        yield existing
        return

    with get_pool().connection() as conn:
        token = _current.set(conn)
        try:
            yield conn
        finally:
            _current.reset(token)


@contextmanager
def transaction() -> Iterator[PooledConnection]:
    """Lend a pooled connection with the block wrapped in an explicit transaction.

    The difference from connection() is nesting. psycopg turns an inner transaction() into a
    SAVEPOINT rather than a second BEGIN, so an inner block can fail and be undone on its own
    while the surrounding work stands. Ingestion is the caller that wants this: ten files in
    one run, and one malformed file should cost that file rather than the whole run.
    """
    with connection() as conn, conn.transaction():
        yield conn
