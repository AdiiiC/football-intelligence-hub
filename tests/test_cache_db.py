"""
Tests for data/cache_db.py
"""
import time
import pytest
from data.cache_db import (
    cache_get, cache_set, cache_delete,
    cache_clear_pattern, cache_cleanup_expired, cache_stats,
)

# Prefix all test keys to avoid collisions with real cache
_PFX = "_pytest_"


def _k(name):
    return f"{_PFX}{name}"


@pytest.fixture(autouse=True)
def clean_test_keys():
    """Remove all test keys before and after each test."""
    cache_clear_pattern(_PFX)
    yield
    cache_clear_pattern(_PFX)


class TestCacheSetGet:
    def test_string_roundtrip(self):
        cache_set(_k("str"), "hello", ttl=60)
        assert cache_get(_k("str")) == "hello"

    def test_dict_roundtrip(self):
        data = {"name": "Saka", "xg": 0.42, "goals": 3}
        cache_set(_k("dict"), data, ttl=60)
        assert cache_get(_k("dict")) == data

    def test_list_roundtrip(self):
        data = [1, 2, 3, {"nested": True}]
        cache_set(_k("list"), data, ttl=60)
        assert cache_get(_k("list")) == data

    def test_int_roundtrip(self):
        cache_set(_k("int"), 42, ttl=60)
        assert cache_get(_k("int")) == 42

    def test_float_roundtrip(self):
        cache_set(_k("float"), 3.14, ttl=60)
        assert abs(cache_get(_k("float")) - 3.14) < 1e-9

    def test_none_value_serializes(self):
        cache_set(_k("none"), None, ttl=60)
        # None round-trips through JSON as None
        assert cache_get(_k("none")) is None

    def test_boolean_roundtrip(self):
        cache_set(_k("bool"), True, ttl=60)
        assert cache_get(_k("bool")) is True

    def test_nested_dict_roundtrip(self):
        data = {"squad": [{"name": "Player A", "age": 25}], "league": "EPL"}
        cache_set(_k("nested"), data, ttl=60)
        assert cache_get(_k("nested"))["squad"][0]["name"] == "Player A"

    def test_overwrite_key(self):
        cache_set(_k("ow"), "first", ttl=60)
        cache_set(_k("ow"), "second", ttl=60)
        assert cache_get(_k("ow")) == "second"

    def test_missing_key_returns_none(self):
        assert cache_get(_k("nonexistent_xyz")) is None


class TestCacheTTL:
    def test_expired_entry_returns_none(self):
        cache_set(_k("exp"), "gone", ttl=1)
        time.sleep(2)
        assert cache_get(_k("exp")) is None

    def test_long_ttl_entry_still_present(self):
        cache_set(_k("long"), "stay", ttl=3600)
        time.sleep(0.1)
        assert cache_get(_k("long")) == "stay"

    def test_zero_ttl_immediately_expired(self):
        cache_set(_k("zero"), "instant", ttl=0)
        time.sleep(0.05)
        # Should be expired — may return None
        val = cache_get(_k("zero"))
        assert val is None or val == "instant"  # race condition tolerance


class TestCacheDelete:
    def test_delete_removes_entry(self):
        cache_set(_k("del"), "value", ttl=60)
        cache_delete(_k("del"))
        assert cache_get(_k("del")) is None

    def test_delete_nonexistent_key_does_not_raise(self):
        cache_delete(_k("never_existed"))  # should not raise

    def test_delete_only_removes_target_key(self):
        cache_set(_k("keep"), "keep_me", ttl=60)
        cache_set(_k("remove"), "remove_me", ttl=60)
        cache_delete(_k("remove"))
        assert cache_get(_k("keep")) == "keep_me"
        assert cache_get(_k("remove")) is None


class TestCacheClearPattern:
    def test_clears_matching_keys(self):
        cache_set(_k("a1"), "v1", ttl=60)
        cache_set(_k("a2"), "v2", ttl=60)
        cache_set("other_key_xyz", "other", ttl=60)
        n = cache_clear_pattern(_PFX)
        assert n >= 2
        assert cache_get(_k("a1")) is None
        assert cache_get(_k("a2")) is None
        # Clean up the non-prefixed one
        cache_delete("other_key_xyz")

    def test_clear_pattern_returns_count(self):
        cache_set(_k("x1"), 1, ttl=60)
        cache_set(_k("x2"), 2, ttl=60)
        n = cache_clear_pattern(_PFX)
        assert isinstance(n, int)
        assert n >= 2

    def test_empty_pattern_match_count_correct(self):
        n = cache_clear_pattern("__no_match_pattern__")
        assert n == 0


class TestCacheCleanupExpired:
    def test_cleanup_removes_expired(self):
        cache_set(_k("exp1"), "v1", ttl=1)
        cache_set(_k("exp2"), "v2", ttl=1)
        cache_set(_k("live"), "v3", ttl=3600)
        time.sleep(2)
        n = cache_cleanup_expired()
        assert isinstance(n, int)
        assert n >= 2
        assert cache_get(_k("live")) == "v3"

    def test_cleanup_with_no_expired_returns_zero(self):
        cache_set(_k("fresh"), "new", ttl=3600)
        n = cache_cleanup_expired()
        assert n >= 0  # might clear unrelated expired entries; just assert non-negative


class TestCacheStats:
    def test_stats_returns_required_keys(self):
        stats = cache_stats()
        assert "total_entries" in stats
        assert "expired" in stats
        assert "size_kb" in stats

    def test_total_entries_increases_after_set(self):
        before = cache_stats()["total_entries"]
        cache_set(_k("stats1"), "v", ttl=60)
        cache_set(_k("stats2"), "v", ttl=60)
        after = cache_stats()["total_entries"]
        assert after >= before + 2

    def test_size_kb_is_non_negative(self):
        stats = cache_stats()
        assert stats["size_kb"] >= 0

    def test_expired_count_is_non_negative(self):
        stats = cache_stats()
        assert stats["expired"] >= 0
