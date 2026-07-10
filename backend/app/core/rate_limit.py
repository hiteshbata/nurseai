import time
import uuid
from collections import deque

from app.core.redis_client import get_redis


class SlidingWindowRateLimiter:
    """Sliding-window limiter keyed by an arbitrary string (e.g. user_id).

    Backed by a Redis sorted set (per name+key) when REDIS_URL is configured,
    so the limit holds across multiple app instances/workers. Falls back to
    an in-process dict when Redis isn't configured -- correct for local dev,
    NOT safe once more than one instance/worker is running.
    """

    def __init__(self, max_calls: int, window_seconds: int, name: str):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.name = name  # namespaces the Redis key; must be unique per limiter
        self._call_log: dict[str, deque] = {}

    def is_rate_limited(self, key: str) -> bool:
        client = get_redis()
        if client is not None:
            return self._is_rate_limited_redis(client, key)
        return self._is_rate_limited_local(key)

    def _is_rate_limited_redis(self, client, key: str) -> bool:
        redis_key = f"ratelimit:{self.name}:{key}"
        now = time.time()
        window_start = now - self.window_seconds
        pipe = client.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        _, count = pipe.execute()
        if count >= self.max_calls:
            return True
        pipe = client.pipeline()
        pipe.zadd(redis_key, {f"{now}:{uuid.uuid4()}": now})
        pipe.expire(redis_key, self.window_seconds)
        pipe.execute()
        return False

    def _is_rate_limited_local(self, key: str) -> bool:
        now = time.monotonic()
        window_start = now - self.window_seconds
        calls = self._call_log.setdefault(key, deque())
        while calls and calls[0] < window_start:
            calls.popleft()
        if len(calls) >= self.max_calls:
            return True
        calls.append(now)
        return False
