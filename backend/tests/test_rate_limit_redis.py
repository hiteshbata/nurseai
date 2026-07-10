"""
M1: rate limiter / role cache must be correct across multiple app
instances/workers, not just single-process.

SlidingWindowRateLimiter and auth._role_recently_upserted/_mark_role_upserted
now go through app.core.redis_client.get_redis() and use Redis sorted
sets / TTL keys when REDIS_URL is set, instead of a per-process dict.

This uses a minimal in-memory fake of the redis-py client (same style as
the FakeSupabase used in test_auth_role_preservation.py) so the Redis-path
logic is exercised without a real Redis server.

Run with:
    python -m unittest backend/tests/test_rate_limit_redis.py -v
"""
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import rate_limit as rate_limit_module  # noqa: E402
from app.core import redis_client as redis_client_module  # noqa: E402
from app.routers import auth as auth_module  # noqa: E402


class FakePipeline:
    def __init__(self, client):
        self._client = client
        self._ops = []

    def zremrangebyscore(self, key, lo, hi):
        self._ops.append(("zremrangebyscore", key, lo, hi))
        return self

    def zcard(self, key):
        self._ops.append(("zcard", key))
        return self

    def zadd(self, key, mapping):
        self._ops.append(("zadd", key, mapping))
        return self

    def expire(self, key, seconds):
        self._ops.append(("expire", key, seconds))
        return self

    def execute(self):
        results = []
        for op in self._ops:
            name = op[0]
            if name == "zremrangebyscore":
                _, key, lo, hi = op
                z = self._client._zsets.setdefault(key, {})
                for member in [m for m, score in z.items() if lo <= score <= hi]:
                    del z[member]
                results.append(None)
            elif name == "zcard":
                _, key = op
                results.append(len(self._client._zsets.get(key, {})))
            elif name == "zadd":
                _, key, mapping = op
                self._client._zsets.setdefault(key, {}).update(mapping)
                results.append(None)
            elif name == "expire":
                results.append(None)
        self._ops = []
        return results


class FakeRedis:
    """Minimal in-memory stand-in for the redis-py commands this codebase uses."""

    def __init__(self):
        self._zsets: dict[str, dict[str, float]] = {}
        self._strings: dict[str, tuple[str, float | None]] = {}  # key -> (value, expires_at)

    def pipeline(self):
        return FakePipeline(self)

    def _expire_string_if_needed(self, key):
        entry = self._strings.get(key)
        if entry is not None and entry[1] is not None and entry[1] < time.time():
            del self._strings[key]

    def get(self, key):
        self._expire_string_if_needed(key)
        entry = self._strings.get(key)
        return entry[0] if entry else None

    def set(self, key, value, ex=None):
        expires_at = time.time() + ex if ex else None
        self._strings[key] = (str(value), expires_at)

    def exists(self, key):
        self._expire_string_if_needed(key)
        return 1 if key in self._strings else 0

    def delete(self, key):
        self._strings.pop(key, None)
        self._zsets.pop(key, None)


class SlidingWindowRateLimiterRedisTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeRedis()
        self._original_get_redis = redis_client_module.get_redis
        redis_client_module.get_redis = lambda: self.fake
        rate_limit_module.get_redis = redis_client_module.get_redis

    def tearDown(self):
        redis_client_module.get_redis = self._original_get_redis
        rate_limit_module.get_redis = self._original_get_redis

    def test_blocks_after_max_calls(self):
        limiter = rate_limit_module.SlidingWindowRateLimiter(3, 60, name="test:limiter")
        for _ in range(3):
            self.assertFalse(limiter.is_rate_limited("user-1"))
        self.assertTrue(limiter.is_rate_limited("user-1"))

    def test_keys_are_independent_per_user(self):
        limiter = rate_limit_module.SlidingWindowRateLimiter(1, 60, name="test:limiter2")
        self.assertFalse(limiter.is_rate_limited("user-a"))
        self.assertFalse(limiter.is_rate_limited("user-b"))
        self.assertTrue(limiter.is_rate_limited("user-a"))

    def test_shared_across_two_limiter_instances_same_name(self):
        """Simulates two app processes (e.g. two Render instances) sharing
        one Redis -- a second limiter instance with the same name must see
        the first instance's calls."""
        limiter_a = rate_limit_module.SlidingWindowRateLimiter(2, 60, name="shared")
        limiter_b = rate_limit_module.SlidingWindowRateLimiter(2, 60, name="shared")
        self.assertFalse(limiter_a.is_rate_limited("user-1"))
        self.assertFalse(limiter_b.is_rate_limited("user-1"))
        self.assertTrue(limiter_a.is_rate_limited("user-1"))


class RoleCacheRedisTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeRedis()
        self._original_get_redis = redis_client_module.get_redis
        redis_client_module.get_redis = lambda: self.fake
        auth_module.get_redis = redis_client_module.get_redis

    def tearDown(self):
        redis_client_module.get_redis = self._original_get_redis
        auth_module.get_redis = self._original_get_redis

    def test_marks_and_recognizes_recent_upsert(self):
        self.assertFalse(auth_module._role_recently_upserted("user-1"))
        auth_module._mark_role_upserted("user-1")
        self.assertTrue(auth_module._role_recently_upserted("user-1"))

    def test_shared_across_two_processes(self):
        """A second process (fresh in-memory dict, same Redis) must see the
        first process's upsert -- this is the exact bug M1 flags."""
        auth_module._mark_role_upserted("admin-1")
        # Simulate a second process: its local dict fallback is empty, but
        # since Redis is configured it must not re-upsert.
        auth_module._user_role_cache.clear()
        self.assertTrue(auth_module._role_recently_upserted("admin-1"))


if __name__ == "__main__":
    unittest.main()
