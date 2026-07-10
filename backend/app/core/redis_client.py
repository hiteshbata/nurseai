from typing import Optional

import redis

from app.core.config import settings

_client: Optional["redis.Redis"] = None
_client_built = False


def get_redis() -> Optional["redis.Redis"]:
    """Shared Redis client, or None if REDIS_URL isn't configured.

    Callers (rate limiter, role cache) fall back to a per-process dict when
    this returns None -- correct for single-instance local dev, wrong for
    any deployment running more than one instance/worker.
    """
    global _client, _client_built
    if not _client_built:
        _client = redis.from_url(settings.REDIS_URL, decode_responses=True) if settings.REDIS_URL else None
        _client_built = True
    return _client
