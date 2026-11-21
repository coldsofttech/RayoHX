"""Internal logging pieces: the logger namespace, the download id tag and the redaction filter.

Engine modules use ``get_logger`` and ``set_download_id``. Applications turn logging on through
``rayohx.logs.configure_logging`` instead.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

ROOT_LOGGER_NAME = "rayohx"
LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(download_id)s] %(name)s: %(message)s"
HANDLER_MARK = "_rayohx_handler"

_download_id: ContextVar[str] = ContextVar("rayohx_download_id", default="-")


def set_download_id(download_id: str) -> None:
    """Tag the log records of the current thread or task with ``download_id``."""
    _download_id.set(download_id)


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger under the ``rayohx`` namespace."""
    if not name or name == ROOT_LOGGER_NAME:
        return logging.getLogger(ROOT_LOGGER_NAME)
    if name.startswith(f"{ROOT_LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")


def _redact_arg(value: Any) -> Any:
    from rayohx._redaction import redact_text

    return redact_text(value) if isinstance(value, str) else value


class RedactionFilter(logging.Filter):
    """Adds the download id and strips secrets from the message and its arguments."""

    def filter(self, record: logging.LogRecord) -> bool:
        from rayohx._redaction import redact_text

        record.download_id = _download_id.get()
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_redact_arg(arg) for arg in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: _redact_arg(arg) for key, arg in record.args.items()}
        if record.exc_info and record.exc_info[1] is not None:
            # Format the traceback now so the stored text can be cleaned too.
            record.exc_text = redact_text(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        return True
