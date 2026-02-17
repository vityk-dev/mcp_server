# src/reposense_mcp/github/rate_limit.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional
import time


def _int(v: str | None) -> Optional[int]:
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    try:
        return int(v)
    except Exception:
        return None


@dataclass
class RateLimitSnapshot:
    """
    Represents GitHub rate limit state inferred from HTTP response headers.

    GitHub headers (may vary by endpoint):
      - X-RateLimit-Limit
      - X-RateLimit-Remaining
      - X-RateLimit-Used
      - X-RateLimit-Reset (epoch seconds)
      - X-RateLimit-Resource (core/search/graphql/etc)
      - Retry-After (seconds)  [usually on 429, sometimes on secondary limit]
    """
    observed_at_ts: float

    limit: int | None = None
    remaining: int | None = None
    used: int | None = None
    reset_epoch_s: int | None = None
    resource: str | None = None
    retry_after_s: int | None = None

    # extra visibility
    status_code: int | None = None
    url: str | None = None
    action: str | None = None

    # derived
    def seconds_until_reset(self) -> int | None:
        if self.reset_epoch_s is None:
            return None
        now = int(time.time())
        return max(0, int(self.reset_epoch_s) - now)

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["seconds_until_reset"] = self.seconds_until_reset()
        return d


def parse_rate_limit_headers(
    headers: Any,
    *,
    status_code: int | None = None,
    url: str | None = None,
    action: str | None = None,
) -> RateLimitSnapshot | None:
    """
    Parse rate limit headers from httpx.Response.headers (case-insensitive mapping).
    Returns None if no RL-related headers are present.
    """
    # httpx.Headers supports .get with case-insensitive keys.
    limit = _int(headers.get("x-ratelimit-limit"))
    remaining = _int(headers.get("x-ratelimit-remaining"))
    used = _int(headers.get("x-ratelimit-used"))
    reset = _int(headers.get("x-ratelimit-reset"))
    resource = headers.get("x-ratelimit-resource")
    retry_after = _int(headers.get("retry-after"))

    # If GitHub didn't send any RL hints, skip.
    if limit is None and remaining is None and used is None and reset is None and retry_after is None and not resource:
        return None

    return RateLimitSnapshot(
        observed_at_ts=time.time(),
        limit=limit,
        remaining=remaining,
        used=used,
        reset_epoch_s=reset,
        resource=(resource.strip() if isinstance(resource, str) else resource),
        retry_after_s=retry_after,
        status_code=status_code,
        url=url,
        action=action,
    )