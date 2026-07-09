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
