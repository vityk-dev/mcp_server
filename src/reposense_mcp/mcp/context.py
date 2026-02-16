from __future__ import annotations

import contextvars
import uuid

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


def set_request_id(rid: str) -> None:
    _request_id.set(rid)


def get_request_id() -> str:
    rid = _request_id.get()
    return rid or uuid.uuid4().hex
