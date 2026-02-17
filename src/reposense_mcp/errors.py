from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RepoSenseError(Exception):
    code: str
    message: str
    hint: str | None = None
    details: dict | None = None