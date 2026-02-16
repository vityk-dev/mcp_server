from __future__ import annotations

import logging
import sys
import time
import uuid
from typing import Any, Dict

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

    Important:
    - Do NOT nuke existing handlers (pytest caplog adds its own handler).
    - Remove only our stdout StreamHandler(s) to avoid duplicates on reload/tests.
    """
    level_name = (settings.log_level or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Keep non-stdout handlers (e.g., pytest caplog) intact.
    # Remove only StreamHandlers that write to sys.stdout, then re-add ours once.
    kept: list[logging.Handler] = []
    for h in root.handlers:
        if isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) is sys.stdout:
            continue
        kept.append(h)
    root.handlers = kept

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