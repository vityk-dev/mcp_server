from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import httpx

from reposense_mcp.github.config import GitHubOAuthConfig
from reposense_mcp.github.token_store import TokenData, TokenStore


@dataclass(frozen=True)
class DeviceCode:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class GitHubDeviceAuth:
    def __init__(self, cfg: GitHubOAuthConfig, store: Optional[TokenStore] = None):
        self.cfg = cfg
        self.store = store or TokenStore()

    async def start(self) -> DeviceCode:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                self.cfg.device_code_url,
                data={"client_id": self.cfg.client_id},
                headers={"Accept": "application/json"},
            )
            r.raise_for_status()
            j = r.json()

        return DeviceCode(
            device_code=j["device_code"],
            user_code=j["user_code"],
            verification_uri=j["verification_uri"],
            expires_in=int(j["expires_in"]),
            interval=int(j.get("interval", 5)),
        )

    async def poll_once(self, device_code: str) -> Tuple[str, Dict[str, Any]]:
        """
        Returns (status, payload)
        status: "pending" | "slow_down" | "denied" | "expired" | "error" | "authorized"
        """
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                self.cfg.token_url,
                data={
                    "client_id": self.cfg.client_id,
                    "client_secret": self.cfg.client_secret,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
                headers={"Accept": "application/json"},
            )
            r.raise_for_status()
            j = r.json()

        if "access_token" in j:
            token = TokenData(
                access_token=j["access_token"],
                token_type=j.get("token_type", "bearer"),
                expires_in=j.get("expires_in"),
                refresh_token=j.get("refresh_token"),
                refresh_token_expires_in=j.get("refresh_token_expires_in"),
                scope=j.get("scope"),
            )
            self.store.save(token)
            return "authorized", {"token_saved": True, "expires_in": token.expires_in}

        # Error cases per GitHub docs
        err = j.get("error")
        if err == "authorization_pending":
            return "pending", {}
        if err == "slow_down":
            return "slow_down", {}
        if err == "access_denied":
            return "denied", {}
        if err in ("expired_token", "bad_verification_code"):
            return "expired", {"error": err}

        return "error", {"error": err or "unknown", "error_description": j.get("error_description")}

    def status(self) -> Dict[str, Any]:
        token = self.store.load()
        return {"authorized": bool(token), "token": (token.__dict__ if token else None)}

    def logout(self) -> Dict[str, Any]:
        self.store.clear()
        return {"ok": True}