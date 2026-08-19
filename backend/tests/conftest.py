"""Test fixtures shared by the whole backend suite."""

import pytest

from portfolio_bot.settings import get_settings


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    """Give every test the required settings, independent of the developer's .env.

    Environment variables take precedence over the .env file, so setting them here makes
    the suite produce the same result on a machine with a filled-in .env and on a clean
    clone with none. The cache is cleared on both sides so no test inherits another
    test's settings object.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
    monkeypatch.setenv("MODEL_API_KEY", "test-key")

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
