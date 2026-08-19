"""Settings are loaded from the environment, validated, and read exactly once."""

import pytest
from pydantic import ValidationError

from portfolio_bot.settings import Settings, get_settings


def test_database_url_is_required(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError) as caught:
        # _env_file=None so this asserts the requirement, not the contents of whatever
        # .env happens to exist on the machine running the suite.
        Settings(_env_file=None)

    assert "database_url" in str(caught.value)


def test_model_api_key_is_required(monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)

    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None)

    assert "model_api_key" in str(caught.value)


def test_values_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://someone@elsewhere:5432/other")
    monkeypatch.setenv("TOP_K", "11")
    monkeypatch.setenv("LOG_FORMAT", "json")

    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql://someone@elsewhere:5432/other"
    assert settings.top_k == 11
    assert settings.log_format == "json"


def test_env_file_is_read(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://fromfile@localhost:5432/fromfile\n"
        "MODEL_API_KEY=from-file\n"
        "CHUNK_SIZE=42\n"
    )

    settings = Settings(_env_file=env_file)

    assert settings.database_url == "postgresql://fromfile@localhost:5432/fromfile"
    assert settings.chunk_size == 42


def test_unknown_names_in_the_env_file_are_ignored(tmp_path, monkeypatch):
    # .env carries POSTGRES_* values that only docker-compose reads. Environment
    # variables outrank the file, so they are cleared to let the file be the source.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://a@localhost:5432/a\n"
        "MODEL_API_KEY=k\n"
        "POSTGRES_USER=portfolio_bot\n"
    )

    settings = Settings(_env_file=env_file)

    assert settings.database_url == "postgresql://a@localhost:5432/a"


def test_log_format_rejects_anything_but_console_or_json(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "xml")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("chunk_size", 1000),
        ("chunk_overlap", 150),
        ("top_k", 5),
        ("rrf_k", 60),
        ("embedding_model_name", "BAAI/bge-small-en-v1.5"),
        ("embedding_model_revision", "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"),
        ("model_name", "qwen3.5:9b"),
        ("model_base_url", "http://localhost:11434/v1"),
        ("log_level", "INFO"),
        ("log_format", "console"),
    ],
)
def test_documented_defaults(field, expected):
    """A silent change to a tuning constant should fail here rather than in a benchmark."""
    assert getattr(Settings(_env_file=None), field) == expected


def test_settings_are_read_once_and_later_changes_are_ignored(monkeypatch):
    monkeypatch.setenv("TOP_K", "7")
    first = get_settings()

    monkeypatch.setenv("TOP_K", "99")
    second = get_settings()

    assert first.top_k == 7
    assert second.top_k == 7
