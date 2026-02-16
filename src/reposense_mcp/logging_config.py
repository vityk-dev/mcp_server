from __future__ import annotations

import logging
import os
import sys
import time
import uuid
from typing import Any, Callable, Dict

import structlog

from reposense_mcp.config import settings


def _add_timestamp(_: Any, __: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    # epoch milliseconds (compact + easy to index)
    event_dict["ts_ms"] = int(time.time() * 1000)
    return event_dict


def _add_level(_: Any, __: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    # structlog adds level later, but we normalize naming
    if "level" not in event_dict and "log_level" in event_dict:
        event_dict["level"] = event_dict.pop("log_level")
    return event_dict


def configure_logging() -> None:
    """
    Configure stdlib logging + structlog for JSON logs.
    Safe to call multiple times (idempotent enough for dev reload).
    """
    level_name = (settings.log_level or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    # Keep stdlib logs readable but minimal; structlog will emit JSON
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            _add_timestamp,
            _add_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "reposense_mcp") -> structlog.BoundLogger:
    return structlog.get_logger(name)


def new_request_id() -> str:
    return uuid.uuid4().hex