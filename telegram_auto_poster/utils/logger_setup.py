import sys
import logging
from loguru import logger


class PropagateHandler(logging.Handler):
    def emit(self, record):
        logging.getLogger(record.name).handle(record)


def setup_logger():
    logging_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{file.path}</cyan>:<cyan>{line}</cyan> <cyan>{function}</cyan> - <level>{message}</level>"
    )

    logger.remove()
    logger.add(sys.stderr, format=logging_format)
    logger.add(PropagateHandler(), format="{message}")

    return logger
