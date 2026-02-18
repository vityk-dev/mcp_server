# src/reposense_mcp/mcp/context.py
from __future__ import annotations

import contextvars
import uuid

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


def set_request_id(rid: str) -> None:
    _request_id.set(rid)


def clear_request_id() -> None:
    _request_id.set(None)


def get_request_id() -> str | None:
    """Return current rid if set, otherwise None (do NOT generate here)."""
    return _request_id.get()


def ensure_request_id() -> str:
    """Return rid; generate + store one if missing."""
    rid = _request_id.get()
    if rid:
        return rid
    rid = uuid.uuid4().hex
    _request_id.set(rid)
    return rid
