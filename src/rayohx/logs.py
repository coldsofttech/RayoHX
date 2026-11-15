"""Logging for applications, on top of the standard ``logging`` module.

The library only creates loggers under ``rayohx``. It never configures the root logger, and it
writes to stderr (never stdout). ``configure_logging`` is for applications such as the command line.
Every record passes through a filter that removes secrets.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from rayohx._logs import HANDLER_MARK, LOG_FORMAT, RedactionFilter, get_logger

if TYPE_CHECKING:
    from pathlib import Path


def configure_logging(
    level: int | str = logging.INFO,
    *,
    console: bool = True,
    log_file: Path | str | None = None,
) -> logging.Logger:
    """Send ``rayohx`` log records to stderr and, optionally, to a file.

    Calling it again replaces the handlers it added before, so it is safe to repeat.
    """
    logger = get_logger()
    for handler in list(logger.handlers):
        if getattr(handler, HANDLER_MARK, False):
            logger.removeHandler(handler)
            handler.close()

    logger.setLevel(level)
    handlers: list[logging.Handler] = []
    if console:
        import sys

        handlers.append(logging.StreamHandler(sys.stderr))
    if log_file is not None:
        from pathlib import Path

        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(path, encoding="utf-8"))
    for handler in handlers:
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        handler.addFilter(RedactionFilter())
        setattr(handler, HANDLER_MARK, True)
        logger.addHandler(handler)
    return logger
