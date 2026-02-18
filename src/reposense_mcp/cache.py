# src/reposense_mcp/cache.py
from __future__ import annotations

import heapq
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    sets: int = 0

    # Legacy total evictions (kept for backward compatibility)
    evictions: int = 0

    # More detailed breakdown
    expired: int = 0
    capacity_evictions: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "sets": self.sets,
            "evictions": self.evictions,
            "expired": self.expired,
            "capacity_evictions": self.capacity_evictions,
        }


class TTLCache:
    """Simple in-memory TTL + LRU cache.

    Production notes:
    - Process-local only (fine for single-instance MCP server).
    - Thread-safe.
    - O(1) average get/set; expiration purge uses a min-heap.
    - Size control uses LRU eviction.
    """

    def __init__(self, ttl_seconds: float = 30.0, max_items: int = 2048):
        self.ttl_seconds = float(ttl_seconds)
        self.max_items = int(max_items)

        self._lock = threading.Lock()
        # key -> (expires_at_monotonic, value). Ordered by recency (LRU).
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        # Min-heap of (expires_at_monotonic, key) for efficient expiry purge.
        self._exp_heap: list[tuple[float, str]] = []

        self._stats = CacheStats()

    def _now(self) -> float:
        # monotonic is safe vs system clock changes
        return time.monotonic()

    def _maybe_compact_heap_locked(self) -> None:
        """Rebuild the expiry heap if it accumulates too many stale entries."""
        # Heuristic: if heap is much larger than live items, rebuild it.
        if len(self._exp_heap) > (len(self._items) * 4 + 128):
            self._exp_heap = [(exp, k) for k, (exp, _) in self._items.items()]
            heapq.heapify(self._exp_heap)

    def _purge_expired_locked(self, now: float) -> None:
        # Pop from heap while expired; ignore stale heap entries.
        while self._exp_heap and self._exp_heap[0][0] <= now:
            exp, key = heapq.heappop(self._exp_heap)
            cur = self._items.get(key)
            if cur is None:
                continue
            cur_exp, _ = cur
            # Only purge if the heap entry matches current expiry.
            if cur_exp == exp and cur_exp <= now:
                self._items.pop(key, None)
                self._stats.expired += 1
                self._stats.evictions += 1

    def get(self, key: str) -> Any | None:
        now = self._now()
        with self._lock:
            self._purge_expired_locked(now)

            item = self._items.get(key)
            if item is None:
                self._stats.misses += 1
                return None

            exp, value = item
            if exp <= now:
                # Should be rare (heap purge would normally remove it), but be safe.
                self._items.pop(key, None)
                self._stats.misses += 1
                self._stats.expired += 1
                self._stats.evictions += 1
                return None

            # LRU bump
            self._items.move_to_end(key, last=True)
            self._stats.hits += 1
            return value

    def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        now = self._now()
        ttl = self.ttl_seconds if ttl_seconds is None else float(ttl_seconds)
        exp = now + max(0.0, ttl)

        with self._lock:
            self._purge_expired_locked(now)

            # Overwrite/move existing key to MRU.
            if key in self._items:
                self._items.pop(key, None)

            self._items[key] = (exp, value)
            self._items.move_to_end(key, last=True)
            heapq.heappush(self._exp_heap, (exp, key))
            self._stats.sets += 1

            # Size control: LRU eviction.
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)
                self._stats.capacity_evictions += 1
                self._stats.evictions += 1
                # Note: we do not remove from heap here; stale entries are ignored.

            # Prevent unbounded heap growth due to stale entries.
            self._maybe_compact_heap_locked()

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

    def stats(self) -> dict[str, Any]:
        now = self._now()
        with self._lock:
            self._purge_expired_locked(now)
            self._maybe_compact_heap_locked()
            return {
                "ttl_seconds": self.ttl_seconds,
                "max_items": self.max_items,
                "size": len(self._items),
                "counters": self._stats.as_dict(),
            }


def make_key(*parts: Any) -> str:
    # Keep keys stable + human debuggable.
    out: list[str] = []
    for p in parts:
        if p is None:
            continue
        s = str(p)
        out.append(s.replace("|", "%7C"))
    return "|".join(out)


# simple singleton used across the process
_default_cache: TTLCache | None = None
_default_lock = threading.Lock()


def default_cache(ttl_seconds: float = 30.0, max_items: int = 2048) -> TTLCache:
    """Process-wide cache instance (singleton).

    IMPORTANT: "first call wins".
    - This MUST stay stable during process lifetime so all components share the same cache.
    - If you want to change ttl/max_items, restart the process (or reset _default_cache in tests).
    """
    global _default_cache
    with _default_lock:
        if _default_cache is None:
            _default_cache = TTLCache(ttl_seconds=ttl_seconds, max_items=max_items)
        return _default_cache
