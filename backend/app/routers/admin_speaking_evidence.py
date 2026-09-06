"""Admin Speaking Evidence Inspector (Step 6).

Read-only QA surface: reconstructs a real speaking session's conversation
history from whatever the pipeline already persisted, then feeds it through
the existing, unmodified app.services.speaking_evidence.build_speaking_evidence()
so an admin can verify the Evidence Layer against real conversations before
it is ever wired into scoring. This module does not write anything, does not
call score_speaking(), and does not touch the Learning Brain -- it only reads
session_transcripts / submissions / scenarios and re-derives evidence on
demand (no new speaking_evidence table, no second source of truth).

Session identifiers are reused, not invented:
  - realtime session  == session_usage_id (session_transcripts and
    realtime_session_metrics both key off it; a reconnect adds another
    session_transcripts row for the same id, so rows are concatenated
    oldest-first, same as speaking_realtime.py's own _load_prior_history).
  - legacy session     == submissions.id (one row per /speaking/score call;
    the legacy chat pipeline never persists structured turns server-side,
    so submissions.answer's flattened "Nurse: ...\nPatient: ..." text is the
    only durable trace -- see speaking.py's score_speaking_session).
"""
import re
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.supabase import get_supabase
from app.routers.admin import require_admin
from app.routers.auth import UserInfo
from app.services.speaking_evidence import build_speaking_evidence_with_semantics
from app.services.evidence_reconciliation import check_integrity, reconcile_evidence
from app.services import session_semantic_state

router = APIRouter(prefix="/admin/speaking-evidence", tags=["admin"])

_LEGACY_TURN_RE = re.compile(r"^(Nurse|Patient): ", re.MULTILINE)


class Pipeline(str, Enum):
    realtime = "realtime"
    legacy = "legacy"


def _scenario_lookup(scenario_id: Optional[int]) -> Dict[str, Any]:
    """Best-effort scenario fetch -- returns {} (never raises) so a session
    whose scenario was since deleted still renders, just with scenario
    fields showing as "Not available" client-side instead of a 500."""
    if scenario_id is None:
        return {}
    row = (
        get_supabase().table("scenarios")
        .select("id, title, setting, interlocutor_card")
        .eq("id", scenario_id)
        .execute()
    )
    return row.data[0] if row.data else {}


def _reconstruct_legacy_history(answer: Optional[str]) -> Tuple[List[Dict[str, str]], Optional[str]]:
    """Splits submissions.answer's flattened "Nurse: X\nPatient: Y" text back
    into {"role","content"} turns. This is the inverse of the join in
    speaking.py's score_speaking_session -- lossy if content itself ever
    contains a line starting with "Nurse: "/"Patient: " (rare, not guarded
    against upstream either). Returns (history, note): note is set (and
    history is []) whenever the text doesn't match the expected shape, so
    the caller can surface "Not available" instead of fabricating turns."""
    if not answer:
        return [], "No transcript text stored for this submission."
    parts = _LEGACY_TURN_RE.split(answer)
    if len(parts) < 3 or parts[0].strip():
        return [], "Legacy transcript text did not match the expected 'Nurse: ... / Patient: ...' format."
    history = [
        {"role": "nurse" if parts[i] == "Nurse" else "patient", "content": parts[i + 1].strip()}
        for i in range(1, len(parts), 2)
    ]
    return history, None


def _load_realtime_session(session_usage_id: int) -> Dict[str, Any]:
    rows = (
        get_supabase().table("session_transcripts")
        .select("user_id, scenario_id, transcript, created_at")
        .eq("session_usage_id", session_usage_id)
        .order("created_at")
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Realtime session not found")

    history: List[Dict[str, str]] = []
    for row in rows:
        for turn in row.get("transcript") or []:
            history.append({"role": turn.get("role", ""), "content": turn.get("text", "")})

    metrics_rows = (
        get_supabase().table("realtime_session_metrics")
        .select("duration_seconds")
        .eq("session_usage_id", session_usage_id)
        .execute()
        .data
    )
    durations = [m["duration_seconds"] for m in metrics_rows if m.get("duration_seconds") is not None]

    return {
        "user_id": rows[0].get("user_id"),
        "scenario_id": rows[0].get("scenario_id"),
        "created_at": rows[0].get("created_at"),
        "duration_seconds": round(sum(durations), 2) if durations else None,
        "history": history,
        "reconstruction_note": None,
        "session_usage_id": session_usage_id,
    }


def _load_legacy_session(submission_id: int) -> Dict[str, Any]:
    rows = (
        get_supabase().table("submissions")
        .select("user_id, scenario_id, answer, created_at, session_usage_id")
        .eq("id", submission_id)
        .eq("module", "speaking")
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Legacy session not found")

    row = rows[0]
    history, note = _reconstruct_legacy_history(row.get("answer"))
    return {
        "user_id": row.get("user_id"),
        "scenario_id": row.get("scenario_id"),
        "created_at": row.get("created_at"),
        "duration_seconds": None,
        "history": history,
        "reconstruction_note": note,
        # Step 14: NULL for any submission scored before this link existed
        # (or a non-speaking-module scoring edge case) -- callers must treat
        # that the same as "no persisted state", never guess a session.
        "session_usage_id": row.get("session_usage_id"),
    }


@router.get("/sessions")
def list_speaking_sessions(
    pipeline: Optional[Pipeline] = Query(None),
    user_id: Optional[str] = Query(None),
    scenario_id: Optional[int] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: UserInfo = Depends(require_admin),
):
    """Recent sessions to pick from, split by pipeline since neither table
    shares an id space. session_transcripts rows are per-connection (a
    reconnect adds a row), so they're deduped down to one entry per
    session_usage_id here, newest first."""
    result: Dict[str, List[Dict[str, Any]]] = {"realtime": [], "legacy": []}

    if pipeline in (None, Pipeline.realtime):
        query = get_supabase().table("session_transcripts").select(
            "session_usage_id, user_id, scenario_id, created_at"
        )
        if user_id:
            query = query.eq("user_id", user_id)
        if scenario_id is not None:
            query = query.eq("scenario_id", scenario_id)
        rows = query.order("created_at", desc=True).limit(limit * 3).execute().data or []
        seen = set()
        for row in rows:
            sid = row["session_usage_id"]
            if sid in seen:
                continue
            seen.add(sid)
            result["realtime"].append({
                "id": sid, "user_id": row.get("user_id"),
                "scenario_id": row.get("scenario_id"), "created_at": row.get("created_at"),
            })
            if len(result["realtime"]) >= limit:
                break

    if pipeline in (None, Pipeline.legacy):
        query = get_supabase().table("submissions").select(
            "id, user_id, scenario_id, created_at"
        ).eq("module", "speaking")
        if user_id:
            query = query.eq("user_id", user_id)
        if scenario_id is not None:
            query = query.eq("scenario_id", scenario_id)
        rows = query.order("created_at", desc=True).limit(limit).execute().data or []
        result["legacy"] = [
            {"id": r["id"], "user_id": r.get("user_id"), "scenario_id": r.get("scenario_id"),
             "created_at": r.get("created_at")}
            for r in rows
        ]

    return result


@router.get("/{pipeline}/{session_id}/evidence")
async def get_speaking_evidence(
    pipeline: Pipeline,
    session_id: int,
    current_user: UserInfo = Depends(require_admin),
):
    """session -> scenario + transcript -> build_speaking_evidence_with_semantics()
    -> structured evidence (deterministic + Step 7 semantic layer), computed
    on demand. Same call for both pipelines -- only how `history` gets
    reconstructed differs. Now async (was sync) since the semantic layer can
    make a handful of model calls -- acceptable for this admin-only,
    on-demand inspector, not a hot path.

    Step 13: for the realtime pipeline, session_id IS session_usage_id (see
    module docstring), so whatever Step 13 persisted for this session is
    loaded and passed as `prior` -- hidden_info_hints then only re-verifies
    candidate turns it hasn't already checked (Step 12B), so inspecting a
    fully-persisted completed session makes zero model calls instead of
    re-verifying the whole transcript on every page load.

    Step 14: the legacy pipeline now gets the same treatment when possible --
    submissions.session_usage_id links a legacy submission back to the
    session_usage row its /speaking/chat turns and /speaking/score call
    shared, and Step 13's get_patient_response already persists semantic
    state under that same id regardless of pipeline. A legacy submission
    scored before this link existed (or otherwise unlinked) has
    session_usage_id = NULL -- that is never guessed, it just falls back to
    the pre-Step-14 behavior of recomputing from scratch."""
    session = (
        _load_realtime_session(session_id) if pipeline == Pipeline.realtime
        else _load_legacy_session(session_id)
    )
    scenario = _scenario_lookup(session["scenario_id"])
    linked_session_usage_id = session["session_usage_id"]
    prior = (
        await session_semantic_state.load_semantic_state(linked_session_usage_id)
        if linked_session_usage_id is not None else None
    )
    evidence = await build_speaking_evidence_with_semantics(
        scenario.get("interlocutor_card"), session["history"], user_id=getattr(current_user, "id", "") or "",
        prior=prior,
    )
    unified = reconcile_evidence(evidence)

    return {
        "session": {
            "id": session_id,
            "pipeline": pipeline.value,
            "user_id": session["user_id"],
            "scenario_id": session["scenario_id"],
            "created_at": session["created_at"],
            "duration_seconds": session["duration_seconds"],
            "reconstruction_note": session["reconstruction_note"],
        },
        "scenario": {
            "id": scenario.get("id"),
            "title": scenario.get("title"),
            "setting": scenario.get("setting"),
            "interlocutor_card": scenario.get("interlocutor_card"),
        } if scenario else None,
        "transcript": session["history"],
        "evidence": evidence.model_dump(),
        "unified": unified.model_dump(),
        # Task 11/12: catches internally impossible evidence combinations
        # (e.g. semantic verified a reveal but final_status stayed hidden) --
        # empty in the overwhelmingly common case, never a claim the evidence
        # is otherwise correct.
        "integrity_violations": [v.model_dump() for v in check_integrity(unified)],
    }
