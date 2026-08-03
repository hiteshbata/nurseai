"""
Best-effort cost accumulation onto the session_usage ledger row (see
supabase-realtime-provider-migration.sql). Every increment here is
non-critical: a failure must never surface to the student or block the
request it's attached to, only get logged.

Increment is done atomically via the increment_session_cost Postgres
function (20260802020000_atomic_session_cost_increment.sql) rather than a
read-modify-write, so concurrent writes to the same session_id can't clobber
each other's delta.
"""
import logging
from typing import Any, Optional

from app.core.supabase import get_supabase
from app.core.threading import run_sync
from app.core import cost_circuit_breaker

logger = logging.getLogger(__name__)

_COST_COLUMNS = {"realtime_cost_usd", "azure_cost_usd", "scoring_cost_usd", "tts_cost_usd"}


_COLUMN_TO_RPC_ARG = {
    "realtime_cost_usd": "p_realtime_delta",
    "azure_cost_usd": "p_azure_delta",
    "scoring_cost_usd": "p_scoring_delta",
    "tts_cost_usd": "p_tts_delta",
}


def _increment_session_cost_sync(session_id: int, provider: str | None, **deltas: float) -> None:
    supabase = get_supabase()
    unknown = set(deltas) - _COST_COLUMNS
    if unknown:
        raise ValueError(f"Unknown cost column(s): {unknown}")

    params = {"p_session_id": session_id, "p_provider": provider}
    params.update({_COLUMN_TO_RPC_ARG[col]: delta for col, delta in deltas.items()})

    supabase.rpc("increment_session_cost", params).execute()


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

    cost_circuit_breaker.record_spend(cost_usd)
