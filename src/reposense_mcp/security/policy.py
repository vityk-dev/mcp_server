from __future__ import annotations

from dataclasses import dataclass
import fnmatch


DEFAULT_DENY_PATTERNS = [
    ".env",
    "*.pem",
    "*.key",
    "id_rsa",
    "id_ed25519",
    ".npmrc",
    ".pypirc",
]


@dataclass(frozen=True)
class RepoPolicy:
    max_file_bytes: int = 200_000
    deny_patterns: tuple[str, ...] = tuple(DEFAULT_DENY_PATTERNS)

    def is_denied(self, path: str) -> bool:
        p = path.lstrip("/")
        return any(fnmatch.fnmatch(p, pat) for pat in self.deny_patterns)
