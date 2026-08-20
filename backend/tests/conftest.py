"""Test fixtures shared by the whole backend suite."""

import pytest

from portfolio_bot.settings import get_settings


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
