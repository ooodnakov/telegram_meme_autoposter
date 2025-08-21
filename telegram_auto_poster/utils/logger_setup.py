"""Helpers for configuring logging with :mod:`loguru`."""

import logging
import os
import sys

from loguru import logger


class PropagateHandler(logging.Handler):
    """Redirect :mod:`loguru` log records to the standard ``logging`` module."""

    def emit(self, record: logging.LogRecord) -> None:
        """Forward a Loguru record to ``logging``.

        Args:
            record: Log record produced by :mod:`loguru`.
        """
        logging.getLogger(record.name).handle(record)


def setup_logger() -> logger.__class__:
    """Configure a :mod:`loguru` logger that also propagates to ``logging``.

    The returned logger prints colourful timestamped messages to stderr and
    forwards each message to the standard logging system so that third-party
    libraries using ``logging`` still produce output.

    Returns:
        loguru.Logger: Configured logger instance.
    """

    logging_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{file.path}</cyan>:<cyan>{line}</cyan> <cyan>{function}</cyan> - <level>{message}</level>"
    )

    logger.remove()
    if os.getenv("JSON_LOGS"):
        logger.add(sys.stderr, serialize=True)
    else:
        logger.add(sys.stderr, format=logging_format)
    logger.add(PropagateHandler(), format="{message}")

    return logger


def get_logger(
    chat_id: int | None = None,
    user_id: int | None = None,
    object_name: str | None = None,
    operation: str | None = None,
):
    """Return a logger bound with standard contextual fields."""

    return logger.bind(
        chat_id=chat_id, user_id=user_id, object_name=object_name, operation=operation
    )
