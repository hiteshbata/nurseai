"""Global daily AI spend cap. Same Redis-with-local-fallback shape as
SlidingWindowRateLimiter (app/core/rate_limit.py) and the per-provider
circuit_breaker -- correct across multiple workers when REDIS_URL is set,
best-effort per-process otherwise.

Blocks new AI calls with a 503 once MAX_DAILY_AI_SPEND_USD is hit for the
current UTC day, so a bug or an attack can't run up unbounded provider cost.
Resets naturally at UTC midnight since the accumulator key is date-scoped
(no cron needed). The cap can be raised/lowered at runtime by an owner via
PUT /admin/spend-cap (app/routers/admin.py) without a redeploy.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from app.core.config import settings
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)

# ponytail: local fallback dicts grow one key per UTC day and are never
# pruned -- negligible (one float per day) for a process that recycles on
# every deploy, so not worth the code to garbage-collect.
_local_spend: dict[str, float] = {}
_local_alerted: dict[str, bool] = {}
_local_cap_override: Optional[float] = None

_SPEND_TTL_SECONDS = 2 * 24 * 60 * 60  # survives a UTC-midnight rollover with margin


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_cap() -> float:
    client = get_redis()
    if client is not None:
        value = client.get("ai_spend:cap_override")
        return float(value) if value is not None else settings.MAX_DAILY_AI_SPEND_USD
    return _local_cap_override if _local_cap_override is not None else settings.MAX_DAILY_AI_SPEND_USD


def set_cap_override(value: Optional[float]) -> None:
    """value=None restores the MAX_DAILY_AI_SPEND_USD env default."""
    global _local_cap_override
    client = get_redis()
    if client is not None:
        if value is None:
            client.delete("ai_spend:cap_override")
        else:
            client.set("ai_spend:cap_override", value)
        return
    _local_cap_override = value


def get_daily_total() -> float:
    client = get_redis()
    key = f"ai_spend:{_today()}"
    if client is not None:
        value = client.get(key)
        return float(value) if value is not None else 0.0
    return _local_spend.get(key, 0.0)


def record_spend(cost_usd: float) -> None:
    if not cost_usd:
        return
    key = f"ai_spend:{_today()}"
    try:
        client = get_redis()
        if client is not None:
            pipe = client.pipeline()
            pipe.incrbyfloat(key, cost_usd)
            pipe.expire(key, _SPEND_TTL_SECONDS)
            pipe.execute()
        else:
            _local_spend[key] = _local_spend.get(key, 0.0) + cost_usd
    except Exception as e:
        logger.warning("[SPEND_CIRCUIT_BREAKER] record_spend failed: %s", str(e)[:300])


def is_tripped() -> bool:
    return get_daily_total() >= get_cap()


def _alert_once(total: float, cap: float) -> None:
    """Sentry alert on the transition into tripped, not on every subsequent
    blocked call -- an open breaker gets hit repeatedly and shouldn't spam."""
    key = f"ai_spend_alerted:{_today()}"
    client = get_redis()
    if client is not None:
        if not client.set(key, "1", nx=True, ex=_SPEND_TTL_SECONDS):
            return
    else:
        if _local_alerted.get(key):
            return
        _local_alerted[key] = True

    logger.error("[AI_SPEND_CAP_TRIPPED] total_usd=%.2f cap_usd=%.2f", total, cap)
    if settings.SENTRY_DSN:
        import sentry_sdk
        sentry_sdk.capture_message(
            f"AI daily spend cap tripped: ${total:.2f} >= ${cap:.2f}", level="error"
        )


def raise_if_tripped() -> None:
    """Call at the top of every function that's about to spend money on an
    AI provider (LLM/STT/TTS/realtime). Raises 503 instead of placing the
    call."""
    total = get_daily_total()
    cap = get_cap()
    if total < cap:
        return
    _alert_once(total, cap)
    raise HTTPException(
        status_code=503,
        detail={
            "error": "Daily AI spend cap reached — please try again later.",
            "spend_cap_exceeded": True,
        },
    )
