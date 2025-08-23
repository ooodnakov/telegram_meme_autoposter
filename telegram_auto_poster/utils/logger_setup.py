"""Helpers for configuring logging with :mod:`loguru`."""

import logging
import sys
import os


from loguru import logger


class PropagateHandler(logging.Handler):
    """Redirect :mod:`loguru` log records to the standard ``logging`` module."""

    def emit(self, record: logging.LogRecord) -> None:
        """Forward a Loguru record to ``logging``.

        Args:
            record: Log record produced by :mod:`loguru`.
        """
        logging.getLogger(record.name).handle(record)


def custom_format(record) -> str:
    """Return formatted log message for loguru.

    Args:
        record (dict): Loguru record dictionary.

    Returns:
        str: Formatted log line with relative path and metadata.
    """
    # Make path relative
    path = str(record["file"].path.replace(os.getcwd(), ""))[1:]
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>"
        f"{path}"
        "</cyan>:<cyan>{line}</cyan> <cyan>{function}</cyan> - <level>{message}</level>\n"
    )


def setup_logger() -> logger.__class__:
    """Configure a :mod:`loguru` logger that also propagates to ``logging``.

    The returned logger prints colourful timestamped messages to stderr and
    forwards each message to the standard logging system so that third-party
    libraries using ``logging`` still produce output.

    Returns:
        loguru.Logger: Configured logger instance.
    """

    logger.remove()
    logger.add(sys.stderr, format=custom_format, colorize=True)
    logger.add(PropagateHandler(), format="{message}")

    return logger
