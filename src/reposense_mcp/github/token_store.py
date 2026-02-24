# src/reposense_mcp/github/token_store.py
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TokenData:
    access_token: str
    token_type: str = "bearer"
    expires_in: int | None = None
    refresh_token: str | None = None
    refresh_token_expires_in: int | None = None
    scope: str | None = None


class TokenStore:
    def __init__(self, path: Path | None = None):
        env_path = (
            os.getenv("REPOSENSE_TOKENSTORE_PATH", "").strip()
            or os.getenv("REPOSENSE_TOKEN_PATH", "").strip()
            or None
        )

        if path is not None:
            self.path = path
        elif env_path is not None:
            self.path = Path(env_path)
        else:
            self.path = Path.home() / ".reposense_mcp" / "github_token.json"

    def load(self) -> TokenData | None:
        if not self.path.exists():
            return None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not data.get("access_token"):
            return None
        return TokenData(**data)

    def save(self, token: TokenData) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(token.__dict__, indent=2), encoding="utf-8")
        tmp.replace(self.path)

        try:
            os.chmod(self.path, 0o600)
        except PermissionError:
            pass

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
