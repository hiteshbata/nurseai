"""
Best-effort cost accumulation onto the session_usage ledger row (see
supabase-realtime-provider-migration.sql). Every increment here is
non-critical: a failure must never surface to the student or block the
request it's attached to, only get logged.

This does a read-modify-write rather than an atomic SQL increment because
the project's Supabase client doesn't expose raw `column = column + x`
updates without a database function. That's an acceptable trade-off for a
cost *estimate* ledger (see app.services.realtime.pricing module docstring)
where a rare lost increment under concurrent writes to the same session
only skews the total by a fraction of a cent -- it must not be used for
anything billing-authoritative.
"""
import logging
from typing import Any, Optional

from app.core.supabase import get_supabase
from app.core.threading import run_sync

logger = logging.getLogger(__name__)

_COST_COLUMNS = {"realtime_cost_usd", "azure_cost_usd", "scoring_cost_usd", "tts_cost_usd"}


def _increment_session_cost_sync(session_id: int, provider: str | None, **deltas: float) -> None:
    supabase = get_supabase()
    unknown = set(deltas) - _COST_COLUMNS
    if unknown:
        raise ValueError(f"Unknown cost column(s): {unknown}")

    row = (
        supabase.table("session_usage")
        .select(",".join(_COST_COLUMNS))
        .eq("id", session_id)
        .limit(1)
        .execute()
    )
    if not row.data:
        return

    current = row.data[0]
    update = {col: round((current.get(col) or 0) + delta, 6) for col, delta in deltas.items()}
    if provider is not None:
        update["provider"] = provider

    supabase.table("session_usage").update(update).eq("id", session_id).execute()


async def increment_session_cost(session_id: int | None, provider: str | None = None, **deltas: float) -> None:
    if session_id is None or not deltas:
        return
    try:
        await run_sync(_increment_session_cost_sync, session_id, provider, **deltas)
    except Exception as e:
        logger.warning("[COST_TRACKING_FAILED] session_id=%s detail=%s", session_id, str(e)[:300])


def _log_ai_usage_sync(row: dict) -> None:
    get_supabase().table("ai_usage_events").insert(row).execute()


async def log_ai_usage(
    call_type: str,
    provider: str,
    cost_usd: float,
    *,
    user_id: Optional[str] = None,
    session_id: Optional[int] = None,
    model: Optional[str] = None,
    is_estimate: bool = False,
    detail: Optional[dict[str, Any]] = None,
) -> None:
    """One row per STT/LLM/TTS/realtime call, independent of session_usage
    (which only exists for speaking sessions) -- this is the durable log
    that per-user/per-plan margin reporting reads from. Best-effort like
    increment_session_cost above: never let a logging failure surface to
    the caller or block the request it's attached to."""
    try:
        await run_sync(_log_ai_usage_sync, {
            "user_id": user_id,
            "session_id": session_id,
            "call_type": call_type,
            "provider": provider,
            "model": model,
            "cost_usd": cost_usd,
            "is_estimate": is_estimate,
            "detail": detail,
        })
    except Exception as e:
        logger.warning("[AI_USAGE_LOG_FAILED] call_type=%s provider=%s detail=%s", call_type, provider, str(e)[:300])
