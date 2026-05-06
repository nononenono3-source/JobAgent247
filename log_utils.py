from __future__ import annotations

import logging
import os
from pathlib import Path

from file_utils import safe_path
from typing import Any, Callable, TypeVar


F = TypeVar("F", bound=Callable[..., Any])

_LOGGER_NAME = "jobagent247"
_CONFIGURED = False


def setup_logging() -> logging.Logger:
    global _CONFIGURED

    logger = logging.getLogger(_LOGGER_NAME)
    if _CONFIGURED:
        return logger

    level_name = (os.getenv("LOG_LEVEL", "INFO") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    log_path = safe_path(os.getenv("PIPELINE_LOG_FILE", "pipeline.log"))
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    _CONFIGURED = True
    logger.debug("Structured logging configured.")
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    base = setup_logging()
    return base if not name else base.getChild(name)


def log_exception(logger: logging.Logger, message: str) -> None:
    logger.exception(message)
