"""
Centralized logging configuration.

Provides setup_logging() to initialize the logging system and get_logger()
for consistent logger creation across modules. Uses loguru for structured,
human-readable log output.
"""

import logging
import sys
from typing import Optional

from loguru import logger

_logging_initialized = False


class _InterceptHandler(logging.Handler):
    """Route stdlib logging (uvicorn, sqlalchemy, etc.) through loguru."""

    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        logger.opt(depth=6, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(level: Optional[str] = None, format_str: Optional[str] = None) -> None:
    global _logging_initialized

    if _logging_initialized:
        return

    from src.core.config import get_config
    config = get_config()

    log_level = level or config.log_level
    log_format = format_str or config.log_format

    logger.remove()
    logger.add(sys.stdout, level=log_level.upper(), format=log_format)

    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)

    _logging_initialized = True


def get_logger(name: str):
    return logger.bind(name=name)
