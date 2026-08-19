"""Logging configured once, for every module in the project.

Named logging_config rather than logging so that an import inside this package is never
ambiguous with the standard library module.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from portfolio_bot.settings import Settings, get_settings

# Attribute names the standard library puts on every record. Anything on a record that is
# not in this set was passed by the call site through `extra=`, and belongs in the output.
_STANDARD_RECORD_FIELDS = frozenset(
    logging.LogRecord(
        name="", level=0, pathname="", lineno=0, msg="", args=None, exc_info=None
    ).__dict__.keys()
) | {"message", "asctime", "taskName"}

CONSOLE_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


class JsonFormatter(logging.Formatter):
    """One JSON object per line, which is what log aggregators expect in production."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_FIELDS:
                payload[key] = value

        return json.dumps(payload, default=str)


def configure_logging(settings: Settings | None = None) -> None:
    """Attach exactly one handler to the root logger, formatted per settings.

    Idempotent. Existing handlers are removed rather than added to, so calling this twice
    (pytest, uvicorn's reloader) cannot stack up duplicates and print everything twice.
    """
    settings = settings if settings is not None else get_settings()

    formatter: logging.Formatter = (
        JsonFormatter() if settings.log_format == "json" else logging.Formatter(CONSOLE_FORMAT)
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())


def get_logger(name: str) -> logging.Logger:
    """Every module gets its logger from here, so none of them configure anything."""
    return logging.getLogger(name)
