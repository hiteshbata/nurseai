"""Per-provider circuit breaker for AI calls. Same Redis-with-local-fallback
shape as SlidingWindowRateLimiter (app/core/rate_limit.py) -- correct across
multiple workers when REDIS_URL is set, best-effort per-process otherwise."""
import time

from app.core.redis_client import get_redis

FAILURE_THRESHOLD = 5
COOLDOWN_SECONDS = 60

PROVIDERS = ("gemini", "openai", "openrouter")

_local_fails: dict[str, int] = {}
_local_opened_at: dict[str, float] = {}


def _opened_at(provider: str) -> float | None:
    client = get_redis()
    if client is not None:
        value = client.get(f"cb:{provider}:opened_at")
        return float(value) if value is not None else None
    return _local_opened_at.get(provider)


def state(provider: str) -> str:
    """closed = healthy. open = skip, still cooling down. half_open = cooldown
    elapsed, let the next request through as a probe."""
    opened_at = _opened_at(provider)
    if opened_at is None:
        return "closed"
    if time.time() - opened_at >= COOLDOWN_SECONDS:
        return "half_open"
    return "open"


def allow_request(provider: str) -> bool:
    return state(provider) != "open"


def record_success(provider: str) -> None:
    client = get_redis()
    if client is not None:
        client.delete(f"cb:{provider}:fails", f"cb:{provider}:opened_at")
    else:
        _local_fails.pop(provider, None)
        _local_opened_at.pop(provider, None)


def record_failure(provider: str) -> None:
    client = get_redis()
    if client is not None:
        fails = client.incr(f"cb:{provider}:fails")
        if fails >= FAILURE_THRESHOLD:
            client.set(f"cb:{provider}:opened_at", time.time())
    else:
        fails = _local_fails.get(provider, 0) + 1
        _local_fails[provider] = fails
        if fails >= FAILURE_THRESHOLD:
            _local_opened_at[provider] = time.time()


def snapshot() -> dict[str, str]:
    """Circuit state per known provider, for /health."""
    return {p: state(p) for p in PROVIDERS}
