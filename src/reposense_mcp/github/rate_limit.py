from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


def _int(v: str | None) -> int | None:
    if v is None:
        return None
    try:
        return int(v.strip())
    except Exception:
        return None


def _lower_get(headers: Mapping[str, str], key: str) -> str | None:
    # httpx headers are case-insensitive, but keep it robust for generic mappings
    try:
        v = headers.get(key)  # type: ignore[attr-defined]
        if v is not None:
            return str(v)
    except Exception:
        pass

    k = key.lower()
    for kk, vv in headers.items():
        if str(kk).lower() == k:
            return str(vv)
    return None


@dataclass(frozen=True)
class RateLimitSnapshot:
    limit: int | None = None
    remaining: int | None = None
    used: int | None = None
    reset_epoch_s: int | None = None
    resource: str | None = None

    # Secondary / generic throttling
    retry_after_s: int | None = None

    # Context
    status_code: int | None = None
    url: str | None = None
    action: str | None = None

    observed_at_ts: float | None = None

    def seconds_until_reset(self) -> int | None:
        if self.reset_epoch_s is None:
            return None
        try:
            return max(0, int(self.reset_epoch_s - int(time.time())))
        except Exception:
            return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "limit": self.limit,
            "remaining": self.remaining,
            "used": self.used,
            "reset_epoch_s": self.reset_epoch_s,
            "resource": self.resource,
            "retry_after_s": self.retry_after_s,
            "status_code": self.status_code,
            "seconds_until_reset": self.seconds_until_reset(),
            "url": self.url,
            "action": self.action,
            "observed_at_ts": self.observed_at_ts,
        }


def parse_rate_limit_headers(
    headers: Mapping[str, str],
    *,
    status_code: int | None = None,
    url: str | None = None,
    action: str | None = None,
) -> RateLimitSnapshot | None:
    """
    Parse GitHub REST API rate limit headers:
      - X-RateLimit-Limit
      - X-RateLimit-Remaining
      - X-RateLimit-Used
      - X-RateLimit-Reset (epoch seconds)
      - X-RateLimit-Resource

    Additionally:
      - Retry-After (seconds)
    """
    limit = _int(_lower_get(headers, "X-RateLimit-Limit"))
    remaining = _int(_lower_get(headers, "X-RateLimit-Remaining"))
    used = _int(_lower_get(headers, "X-RateLimit-Used"))
    reset = _int(_lower_get(headers, "X-RateLimit-Reset"))
    resource = _lower_get(headers, "X-RateLimit-Resource")
    retry_after = _int(_lower_get(headers, "Retry-After"))

    if (
        limit is None
        and remaining is None
        and used is None
        and reset is None
        and resource is None
        and retry_after is None
    ):
        return None

    return RateLimitSnapshot(
        limit=limit,
        remaining=remaining,
        used=used,
        reset_epoch_s=reset,
        resource=(resource.strip() if resource else None),
        retry_after_s=retry_after,
        status_code=status_code,
        url=url,
        action=action,
        observed_at_ts=time.time(),
    )


class RateLimitTracker:
    """
    Process-local rate limit tracker.
    Keyed by (token_fingerprint, resource|unknown).

    Thread-safe. Can be shared by multiple GitHubClient instances.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[tuple[str, str], RateLimitSnapshot] = {}

    def update(
        self,
        *,
        token_fingerprint: str,
        headers: Mapping[str, str],
        status_code: int | None = None,
        url: str | None = None,
        action: str | None = None,
    ) -> RateLimitSnapshot | None:
        snap = parse_rate_limit_headers(headers, status_code=status_code, url=url, action=action)
        if not snap:
            return None

        resource = snap.resource or "unknown"
        key = (token_fingerprint or "unknown", resource)

        with self._lock:
            self._data[key] = snap

        return snap

    def status(self, *, token_fingerprint: str) -> dict[str, Any]:
        tfp = token_fingerprint or "unknown"

        resources: dict[str, Any] = {}
        latest: RateLimitSnapshot | None = None

        with self._lock:
            for (k_tfp, resource), snap in self._data.items():
                if k_tfp not in (tfp, "unknown"):
                    continue

                resources[f"{k_tfp}:{resource}"] = snap.as_dict()

                if k_tfp == tfp:
                    if latest is None or (snap.observed_at_ts or 0.0) > (
                        latest.observed_at_ts or 0.0
                    ):
                        latest = snap

            if latest is None:
                for (k_tfp, _resource), snap in self._data.items():
                    if k_tfp != "unknown":
                        continue
                    if latest is None or (snap.observed_at_ts or 0.0) > (
                        latest.observed_at_ts or 0.0
                    ):
                        latest = snap

        return {
            "token_fingerprint": tfp,
            "cached": (latest.as_dict() if latest else None),
            "resources": resources,
        }

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


_default_tracker: RateLimitTracker | None = None
_default_lock = threading.Lock()


def default_rate_limit_tracker() -> RateLimitTracker:
    global _default_tracker
    with _default_lock:
        if _default_tracker is None:
            _default_tracker = RateLimitTracker()
        return _default_tracker
