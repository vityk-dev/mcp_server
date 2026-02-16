# src/reposense_mcp/cache.py
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    sets: int = 0
    evictions: int = 0

    def as_dict(self) -> Dict[str, int]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "sets": self.sets,
            "evictions": self.evictions,
        }


class TTLCache:
    """
    Simple in-memory TTL cache.

    Notes:
    - Process-local only (fine for single-instance MCP server).
    - Thread-safe.
    - Stores any JSON-serializable objects (and generally any python objects).
    """

    def __init__(self, ttl_seconds: float = 30.0, max_items: int = 2048):
        self.ttl_seconds = float(ttl_seconds)
        self.max_items = int(max_items)
        self._lock = threading.Lock()
        self._items: Dict[str, Tuple[float, Any]] = {}  # key -> (expires_at, value)
        self._stats = CacheStats()

    def _now(self) -> float:
        return time.time()

    def _purge_expired_locked(self, now: float) -> None:
        expired = [k for k, (exp, _) in self._items.items() if exp <= now]
        for k in expired:
            self._items.pop(k, None)
        if expired:
            self._stats.evictions += len(expired)

    def get(self, key: str) -> Optional[Any]:
        now = self._now()
        with self._lock:
            self._purge_expired_locked(now)
            item = self._items.get(key)
            if not item:
                self._stats.misses += 1
                return None

            exp, value = item
            if exp <= now:
                self._items.pop(key, None)
                self._stats.misses += 1
                self._stats.evictions += 1
                return None

            self._stats.hits += 1
            return value

    def set(self, key: str, value: Any, ttl_seconds: Optional[float] = None) -> None:
        now = self._now()
        ttl = self.ttl_seconds if ttl_seconds is None else float(ttl_seconds)
        exp = now + max(0.0, ttl)

        with self._lock:
            self._purge_expired_locked(now)

            # crude size control: evict arbitrary oldest-ish by expiration time
            if len(self._items) >= self.max_items:
                # evict 10% or at least 1
                n_evict = max(1, self.max_items // 10)
                victims = sorted(self._items.items(), key=lambda kv: kv[1][0])[:n_evict]
                for k, _ in victims:
                    self._items.pop(k, None)
                self._stats.evictions += len(victims)

            self._items[key] = (exp, value)
            self._stats.sets += 1

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def stats(self) -> Dict[str, Any]:
        now = self._now()
        with self._lock:
            self._purge_expired_locked(now)
            return {
                "ttl_seconds": self.ttl_seconds,
                "max_items": self.max_items,
                "size": len(self._items),
                "counters": self._stats.as_dict(),
            }


def make_key(*parts: str) -> str:
    # Keep keys stable + human debuggable.
    return "|".join(p.replace("|", "%7C") for p in parts if p is not None)


# simple singleton used across the process
_default_cache: TTLCache | None = None
_default_lock = threading.Lock()


def default_cache(ttl_seconds: float = 30.0, max_items: int = 2048) -> TTLCache:
    global _default_cache
    with _default_lock:
        if _default_cache is None:
            _default_cache = TTLCache(ttl_seconds=ttl_seconds, max_items=max_items)
        return _default_cache