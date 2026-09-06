"""Persisted Semantic Verification State (Step 13).

Persists the authoritative, expensive-to-compute fact -- app.services.
patient_state.SemanticHints -- so it survives realtime disconnect/reconnect,
session completion, and later admin inspection without re-running semantic
verification. Deliberately does NOT persist PatientState, SpeakingEvidence,
or UnifiedEvidence: those stay derived on demand from (scenario, transcript,
SemanticHints), see each module's own docstring.

Storage: public.session_semantic_state, one row per session_usage_id (both
PK and UPSERT conflict target -- retries/reconnects can't create duplicates).
RLS enabled with no policies (see the migration) -- service-role only, same
posture as session_transcripts, since this can reveal whether a scenario's
hidden information was disclosed.

Callers are responsible for deciding WHEN to load/save (see
speaking_realtime.py and ai_scoring.get_patient_response) and must never let
a failure here take down a live session -- both save_semantic_state and
load_semantic_state catch and log rather than raise.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.core.supabase import get_supabase
from app.core.threading import run_sync
from app.services.patient_state import SemanticHints

logger = logging.getLogger(__name__)

STATE_VERSION = 1
SEMANTIC_STATE_PURPOSE = "speaking_semantic_evidence"


def _to_storage(hints: SemanticHints) -> Dict[str, Any]:
    """JSON-safe dict. Only dict/frozenset shapes need conversion -- values
    (including the ints in candidate_turn_status/confirmed_reveal_turn)
    round-trip through JSON unchanged; only dict KEYS turn into strings, so
    those are the only fields _from_storage has to convert back."""
    return {
        "confirmed_hidden_reveals": sorted(hints.confirmed_hidden_reveals),
        "rejected_hidden_reveals": sorted(hints.rejected_hidden_reveals),
        "extra_nurse_events": {str(k): v for k, v in hints.extra_nurse_events.items()},
        "resolved_concerns": sorted(hints.resolved_concerns),
        "verification_status": dict(hints.verification_status),
        "candidate_turn_status": {
            item: {str(idx): status for idx, status in turns.items()}
            for item, turns in hints.candidate_turn_status.items()
        },
        "confirmed_reveal_turn": dict(hints.confirmed_reveal_turn),
    }


def _from_storage(data: Dict[str, Any]) -> SemanticHints:
    return SemanticHints(
        confirmed_hidden_reveals=frozenset(data.get("confirmed_hidden_reveals") or []),
        rejected_hidden_reveals=frozenset(data.get("rejected_hidden_reveals") or []),
        extra_nurse_events={int(k): v for k, v in (data.get("extra_nurse_events") or {}).items()},
        resolved_concerns=frozenset(data.get("resolved_concerns") or []),
        verification_status=dict(data.get("verification_status") or {}),
        candidate_turn_status={
            item: {int(idx): status for idx, status in turns.items()}
            for item, turns in (data.get("candidate_turn_status") or {}).items()
        },
        confirmed_reveal_turn=dict(data.get("confirmed_reveal_turn") or {}),
    )


def _save_sync(session_usage_id: int, user_id: str, hints: SemanticHints) -> None:
    get_supabase().table("session_semantic_state").upsert(
        {
            "session_usage_id": session_usage_id,
            "user_id": user_id,
            "purpose": SEMANTIC_STATE_PURPOSE,
            "state_version": STATE_VERSION,
            "semantic_state": _to_storage(hints),
        },
        on_conflict="session_usage_id",
    ).execute()


async def save_semantic_state(
    session_usage_id: Optional[int], user_id: str, hints: SemanticHints, prior: Optional[SemanticHints] = None,
) -> None:
    """Idempotent UPSERT. No-ops (no DB call at all) when session_usage_id is
    absent (warmup sessions) or `hints` is structurally identical to `prior`
    (SemanticHints is a plain dataclass, so `==` is real field equality) --
    the common case of a turn with no new candidate, cutting write volume
    without changing correctness. Never raises: a failed save must never
    take down a live speaking session (Step 7 of the task) -- the caller's
    in-memory state stays authoritative for the rest of this connection and
    the next state change (or the final teardown flush) retries."""
    if session_usage_id is None or (prior is not None and hints == prior):
        return
    try:
        await run_sync(_save_sync, session_usage_id, user_id, hints)
    except Exception as e:
        logger.warning("[SEMANTIC_STATE_SAVE_FAILED] session_id=%s %s", session_usage_id, str(e)[:300])


def _load_sync(session_usage_id: int) -> Optional[Dict[str, Any]]:
    result = (
        get_supabase().table("session_semantic_state")
        .select("state_version, semantic_state")
        .eq("session_usage_id", session_usage_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def load_semantic_state(session_usage_id: Optional[int]) -> SemanticHints:
    """Returns an empty SemanticHints (the safe, conservative default -- see
    SemanticHints's own docstring) whenever there's nothing to restore, the
    load fails, or the stored state_version isn't one this code understands.
    Never raises, never reinterprets an unknown version as valid data."""
    if session_usage_id is None:
        return SemanticHints()
    try:
        row = await run_sync(_load_sync, session_usage_id)
    except Exception as e:
        logger.warning("[SEMANTIC_STATE_LOAD_FAILED] session_id=%s %s", session_usage_id, str(e)[:300])
        return SemanticHints()
    if row is None:
        return SemanticHints()
    if row.get("state_version") != STATE_VERSION:
        logger.warning(
            "[SEMANTIC_STATE_VERSION_MISMATCH] session_id=%s found=%s expected=%s",
            session_usage_id, row.get("state_version"), STATE_VERSION,
        )
        return SemanticHints()
    return _from_storage(row.get("semantic_state") or {})
