# src/reposense_mcp/cache.py
from __future__ import annotations

import heapq
import threading
import time
from collections import OrderedDict
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
    """Simple in-memory TTL + LRU cache.

    Notes:
    - Process-local only (fine for single-instance MCP server).
    - Thread-safe.
    - LRU eviction on max_items.
    - Expiration purge uses a min-heap; stale heap entries are ignored.
    """

    def __init__(self, ttl_seconds: float = 30.0, max_items: int = 2048):
        self.ttl_seconds = float(ttl_seconds)
        self.max_items = int(max_items)

        self._lock = threading.Lock()
        # key -> (expires_at, value) ordered by recency
        self._items: "OrderedDict[str, Tuple[float, Any]]" = OrderedDict()
        # heap entries: (expires_at, key)
        self._exp_heap: list[tuple[float, str]] = []

        self._stats = CacheStats()

    def _now(self) -> float:
        # IMPORTANT: tests monkeypatch time.time in this module
        return time.time()

    def _purge_expired_locked(self, now: float) -> None:
        while self._exp_heap and self._exp_heap[0][0] <= now:
            exp, key = heapq.heappop(self._exp_heap)
            cur = self._items.get(key)
            if cur is None:
                continue
            cur_exp, _ = cur
            # purge only if heap entry matches current expiry
            if cur_exp == exp and cur_exp <= now:
                self._items.pop(key, None)
                self._stats.evictions += 1

    def get(self, key: str) -> Optional[Any]:
        now = self._now()
        with self._lock:
            self._purge_expired_locked(now)

            item = self._items.get(key)
            if item is None:
                self._stats.misses += 1
                return None

            exp, value = item
            if exp <= now:
                self._items.pop(key, None)
                self._stats.misses += 1
                self._stats.evictions += 1
                return None

            # LRU bump
            self._items.move_to_end(key, last=True)
            self._stats.hits += 1
            return value

    def set(self, key: str, value: Any, ttl_seconds: Optional[float] = None) -> None:
        now = self._now()
        ttl = self.ttl_seconds if ttl_seconds is None else float(ttl_seconds)
        exp = now + max(0.0, ttl)

        with self._lock:
            self._purge_expired_locked(now)

            if key in self._items:
                self._items.pop(key, None)

            self._items[key] = (exp, value)
            self._items.move_to_end(key, last=True)
            heapq.heappush(self._exp_heap, (exp, key))
            self._stats.sets += 1

            # LRU eviction
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)
                self._stats.evictions += 1
                # heap cleanup is lazy (stale entries ignored)

    def delete(self, key: str) -> bool:
        with self._lock:
            existed = key in self._items
            if existed:
                self._items.pop(key, None)
            return existed

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._exp_heap.clear()
            self._stats = CacheStats()

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
    return "|".join(p.replace("|", "%7C") for p in parts if p is not None)


_default_cache: TTLCache | None = None
_default_lock = threading.Lock()


def default_cache(ttl_seconds: float = 30.0, max_items: int = 2048) -> TTLCache:
    """Process-wide singleton cache.

    IMPORTANT (tests + expected semantics):
    - first call wins; later calls return the same instance
    """
    global _default_cache
    with _default_lock:
        if _default_cache is None:
            _default_cache = TTLCache(ttl_seconds=ttl_seconds, max_items=max_items)
        return _default_cache