"""Logging is configured once, in the format settings ask for."""

import json
import logging

import pytest

from portfolio_bot.logging_config import JsonFormatter, configure_logging, get_logger
from portfolio_bot.settings import Settings


@pytest.fixture(autouse=True)
def restore_root_logger():
    """Put the root logger back, since configure_logging deliberately mutates it."""
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level

    yield

    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in original_handlers:
        root.addHandler(handler)
    root.setLevel(original_level)


def make_settings(**overrides):
    defaults = {
        "database_url": "postgresql://test:test@localhost:5432/test",
        "model_api_key": "test-key",
    }
    return Settings(_env_file=None, **(defaults | overrides))


def make_record(level=logging.INFO, message="hello", exc_info=None, **extra):
    record = logging.LogRecord(
        name="portfolio_bot.example",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=None,
        exc_info=exc_info,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_configuring_twice_leaves_one_handler():
    configure_logging(make_settings())
    configure_logging(make_settings())

    assert len(logging.getLogger().handlers) == 1


def test_level_comes_from_settings():
    configure_logging(make_settings(log_level="WARNING"))

    assert logging.getLogger().level == logging.WARNING


def test_lowercase_level_is_accepted():
    configure_logging(make_settings(log_level="debug"))

    assert logging.getLogger().level == logging.DEBUG


def test_json_formatter_emits_the_expected_keys():
    payload = json.loads(JsonFormatter().format(make_record()))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "portfolio_bot.example"
    assert payload["message"] == "hello"
    assert payload["timestamp"].endswith("+00:00")


def test_json_formatter_includes_extra_fields():
    payload = json.loads(JsonFormatter().format(make_record(chunk_id=17, strategy="hybrid")))

    assert payload["chunk_id"] == 17
    assert payload["strategy"] == "hybrid"


def test_json_formatter_includes_the_traceback():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = make_record(level=logging.ERROR, message="failed", exc_info=sys.exc_info())

    payload = json.loads(JsonFormatter().format(record))

    assert "ValueError: boom" in payload["exception"]
    assert "Traceback" in payload["exception"]


def test_console_format_contains_level_and_message(capsys):
    configure_logging(make_settings(log_format="console", log_level="INFO"))

    get_logger("portfolio_bot.example").info("a readable line")

    err = capsys.readouterr().err
    assert "INFO" in err
    assert "a readable line" in err


def test_json_format_writes_one_parseable_object_per_line(capsys):
    configure_logging(make_settings(log_format="json", log_level="INFO"))

    get_logger("portfolio_bot.example").info("structured line")

    payload = json.loads(capsys.readouterr().err.strip())
    assert payload["message"] == "structured line"
