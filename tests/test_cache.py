# tests/test_cache.py
from __future__ import annotations

import types

import pytest

import reposense_mcp.cache as cache_mod


class FakeClock:
    def __init__(self, start: float = 1_000.0):
        self.t = start

    def time(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock(monkeypatch) -> FakeClock:
    c = FakeClock()
    # Patch the module-level time dependency used by TTLCache
    monkeypatch.setattr(cache_mod.time, "time", c.time)
    return c


def test_make_key_escapes_pipes_and_joins():
    k = cache_mod.make_key("github", "read_file", "a|b", "c", "d|e")
    assert k == "github|read_file|a%7Cb|c|d%7Ce"


def test_ttlcache_set_get_hit_miss_stats(clock: FakeClock):
    c = cache_mod.TTLCache(ttl_seconds=10.0, max_items=10)

    assert c.get("missing") is None
    s = c.stats()
    assert s["counters"]["misses"] == 1
    assert s["counters"]["hits"] == 0

    c.set("k1", {"x": 1})
    assert c.get("k1") == {"x": 1}

    s = c.stats()
    assert s["counters"]["sets"] == 1
    assert s["counters"]["hits"] == 1
    assert s["size"] == 1


def test_ttlcache_expiry_eviction(clock: FakeClock):
    c = cache_mod.TTLCache(ttl_seconds=5.0, max_items=10)

    c.set("k1", "v1")
    assert c.get("k1") == "v1"

    clock.advance(4.9)
    assert c.get("k1") == "v1"

    clock.advance(0.2)  # now expired
    assert c.get("k1") is None

    s = c.stats()
    # one miss from expired fetch + one eviction accounted
    assert s["counters"]["evictions"] >= 1
    assert s["size"] == 0


def test_ttlcache_set_with_override_ttl(clock: FakeClock):
    c = cache_mod.TTLCache(ttl_seconds=100.0, max_items=10)

    c.set("k1", "v1", ttl_seconds=1.0)
    assert c.get("k1") == "v1"

    clock.advance(1.01)
    assert c.get("k1") is None


def test_ttlcache_clear_resets_size(clock: FakeClock):
    c = cache_mod.TTLCache(ttl_seconds=10.0, max_items=10)
    c.set("k1", 1)
    c.set("k2", 2)
    assert c.stats()["size"] == 2

    c.clear()
    assert c.stats()["size"] == 0


def test_ttlcache_max_items_eviction_policy(clock: FakeClock):
    # max_items=5 => when inserting the 6th, it evicts max(1, 5//10)=1 victim
    c = cache_mod.TTLCache(ttl_seconds=100.0, max_items=5)

    # Stagger expirations (they all share same ttl, but insertion time differs)
    for i in range(5):
        c.set(f"k{i}", i)
        clock.advance(1.0)

    assert c.stats()["size"] == 5

    # Adding one more triggers eviction of the smallest exp (oldest-ish)
    c.set("k5", 5)
    s = c.stats()
    assert s["size"] == 5
    assert s["counters"]["evictions"] >= 1

    # The oldest key is most likely evicted ("k0"), but we don't overfit.
    # Just ensure at least one of the original keys is missing.
    missing = sum(1 for i in range(5) if c.get(f"k{i}") is None)
    assert missing >= 1
    assert c.get("k5") == 5


def test_default_cache_is_singleton(monkeypatch):
    # Reset module singleton safely for this test
    monkeypatch.setattr(cache_mod, "_default_cache", None)

    c1 = cache_mod.default_cache(ttl_seconds=1.0, max_items=10)
    c2 = cache_mod.default_cache(ttl_seconds=999.0, max_items=999)
    assert c1 is c2
    # the first call "wins"
    assert c2.ttl_seconds == 1.0
    assert c2.max_items == 10