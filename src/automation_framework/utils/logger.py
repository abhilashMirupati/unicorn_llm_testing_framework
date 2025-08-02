"""
Logger Utility
--------------

Provides a single function `get_logger` that configures and returns
a logger for the given module.  The logger writes to stdout and
includes timestamps, log levels and module names.  Log level can be
controlled via the environment variable `LOG_LEVEL`.
"""

import logging
import os
from functools import lru_cache


@lru_cache(maxsize=None)
def get_logger(name: str) -> logging.Logger:
    """Return a configured logger with the specified name."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s – %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
    return logger


__all__ = ["get_logger"]