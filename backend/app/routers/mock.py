"""OET Full Mock Test orchestrator.

A "mock" chains the existing per-module test sessions into one strict, timed
sitting. It deliberately does NOT re-implement grading: each module's own player
still calls its own submit/score endpoint (reading/listening `/tests/{id}/submit`,
writing `/submit`, speaking `/score`), which records that module's normal
submission + skill signal. The player then reports the result here so the mock
can advance the student and, once everything is in, reveal all bands together.

Scores stay hidden until the whole mock is `complete` — matching real OET, where
results arrive later, per sub-test. Listening/Reading/Writing run as one
continuous timed sitting and land the mock at `awaiting_speaking`; Speaking (two
role plays, taken separately like the real exam, no hard timer -- paced by the
live conversation same as standalone speaking practice) then completes it.
"""
import random
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.supabase import get_supabase
from app.core.threading import run_sync
from app.routers.auth import get_current_user, UserInfo

router = APIRouter(prefix="/mock", tags=["mock"])

# Fixed sitting order for phase 1. Speaking is appended in phase 2.
SECTION_ORDER: List[str] = ["listening", "reading", "writing"]

# Per-section hard cap (seconds) = the strict deadline the client counts down to.
# Listening is really paced by its ~40-min audio; the cap is a generous backstop.
# Reading = 60 min (Part A 15 + Parts B&C 45). Writing = 45 min (5 read + 40 write).
SECTION_CAP_SECONDS = {"listening": 45 * 60, "reading": 60 * 60, "writing": 45 * 60}

# Which frozen pick a section reads its content id from.
CONTENT_KEY = {
    "listening": "listening_test_id",
    "reading": "reading_test_id",
    "writing": "writing_scenario_id",
}

# Statuses where the student is still mid-mock (resume instead of starting a new one).
OPEN_STATUSES = ["in_progress", "awaiting_speaking"]
# What /mock/current will surface -- OPEN_STATUSES plus a just-finished mock, so
# the controller can route straight to the unlocked report after Speaking ends.
# A completed mock never blocks /mock/start (that check is scoped to
# status=='in_progress' only), so this doesn't trap the student either.
VISIBLE_STATUSES = OPEN_STATUSES + ["complete"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── content pools (an active test/scenario that actually has active children) ──

def _active_reading_test_ids(supabase) -> List[int]:
    tests = supabase.table("reading_tests").select("id").eq("is_active", True).execute().data
    ids = [t["id"] for t in tests]
    if not ids:
        return []
    passages = supabase.table("reading_passages").select("test_id").in_("test_id", ids).eq("is_active", True).execute().data
    have = {p["test_id"] for p in passages}
    return [i for i in ids if i in have]


def _active_listening_test_ids(supabase) -> List[int]:
    tests = supabase.table("listening_tests").select("id").eq("is_active", True).execute().data
    ids = [t["id"] for t in tests]
    if not ids:
        return []
    sections = supabase.table("listening_sections").select("test_id").in_("test_id", ids).eq("is_active", True).execute().data
    have = {s["test_id"] for s in sections}
    return [i for i in ids if i in have]


def _active_writing_scenario_ids(supabase) -> List[int]:
    rows = supabase.table("scenarios").select("id").eq("module", "writing").eq("is_active", True).execute().data
    return [r["id"] for r in rows]


def _active_speaking_scenario_ids(supabase) -> List[int]:
    rows = supabase.table("scenarios").select("id").eq("module", "speaking").eq("is_active", True).execute().data
    return [r["id"] for r in rows]


# ── session shaping ───────────────────────────────────────────────────

def _client_payload(session: Dict[str, Any]) -> Dict[str, Any]:
    """What the frontend controller needs to route the student: which section is
    live, the content id to load for it, and the strict deadline to count down to."""
    section = session.get("current_section")
    content_id = None
    deadline = None
    if section:
        content_id = session.get(CONTENT_KEY[section])
        started = (session.get("section_started_at") or {}).get(section)
        if started:
            deadline = (datetime.fromisoformat(started) + timedelta(seconds=SECTION_CAP_SECONDS[section])).isoformat()
    return {
        "id": session["id"],
        "status": session["status"],
        "current_section": section,
        "content_id": content_id,
        "deadline": deadline,
        "order": SECTION_ORDER,
        "completed": list((session.get("results") or {}).keys()),
    }


async def _ensure_section_started(supabase, session: Dict[str, Any]) -> Dict[str, Any]:
    """Stamp the current section's start time the first time it's opened, so the
    strict countdown is anchored server-side — a page refresh can't reset it."""
    section = session.get("current_section")
    if not section:
        return session
    started_map = dict(session.get("section_started_at") or {})
    if section not in started_map:
        started_map[section] = _now_iso()
        await run_sync(
            supabase.table("mock_test_sessions").update(
                {"section_started_at": started_map, "updated_at": _now_iso()}
            ).eq("id", session["id"]).execute
        )
        session["section_started_at"] = started_map
    return session


async def _load_owned(supabase, mock_id: str, user_id: str) -> Dict[str, Any]:
    res = await run_sync(
        supabase.table("mock_test_sessions").select("*")
        .eq("id", mock_id).eq("user_id", user_id).execute
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Mock test not found")
    return res.data[0]


# ── endpoints ─────────────────────────────────────────────────────────

@router.get("/current")
async def current_mock(current_user: UserInfo = Depends(get_current_user)):
    """The student's live mock, if any. `active: false` means none is running —
    the frontend then shows the 'Start Full Mock Test' landing. Also surfaces a
    just-completed mock (once) so the controller can route straight to the
    unlocked report."""
    supabase = get_supabase()
    res = await run_sync(
        supabase.table("mock_test_sessions").select("*")
        .eq("user_id", current_user.id).in_("status", VISIBLE_STATUSES)
        .order("created_at", desc=True).limit(1).execute
    )
    if not res.data:
        return {"active": False}
    session = await _ensure_section_started(supabase, res.data[0])
    return {"active": True, **_client_payload(session)}


@router.post("/start")
async def start_mock(current_user: UserInfo = Depends(get_current_user)):
    """Resume an open mock, or auto-assemble a fresh one: one random active
    Listening test + Reading test + Writing scenario, frozen for this attempt."""
    supabase = get_supabase()

    # Resume only a written test that's still in progress. A mock parked at
    # awaiting_speaking (LRW done, Speaking pending) must NOT block starting a new
    # one — otherwise, until Speaking ships, the first mock would trap the student.
    existing = await run_sync(
        supabase.table("mock_test_sessions").select("*")
        .eq("user_id", current_user.id).eq("status", "in_progress")
        .order("created_at", desc=True).limit(1).execute
    )
    if existing.data:
        session = await _ensure_section_started(supabase, existing.data[0])
        return _client_payload(session)

    listening_ids = _active_listening_test_ids(supabase)
    reading_ids = _active_reading_test_ids(supabase)
    writing_ids = _active_writing_scenario_ids(supabase)
    speaking_ids = _active_speaking_scenario_ids(supabase)
    missing = [
        name for name, ids, need in
        [("Listening", listening_ids, 1), ("Reading", reading_ids, 1),
         ("Writing", writing_ids, 1), ("Speaking", speaking_ids, 2)]
        if len(ids) < need
    ]
    if missing:
        raise HTTPException(
            status_code=409,
            detail=f"Not enough content to build a full mock yet (missing: {', '.join(missing)}).",
        )

    # Two DISTINCT speaking scenarios -- real OET gives two different role-play
    # cards, frozen up front like the other picks (scores stay hidden regardless
    # of when content is chosen).
    speaking_1, speaking_2 = random.sample(speaking_ids, 2)
    row = await run_sync(
        supabase.table("mock_test_sessions").insert({
            "user_id": current_user.id,
            "listening_test_id": random.choice(listening_ids),
            "reading_test_id": random.choice(reading_ids),
            "writing_scenario_id": random.choice(writing_ids),
            "speaking_scenario_id_1": speaking_1,
            "speaking_scenario_id_2": speaking_2,
            "current_section": SECTION_ORDER[0],
            "status": "in_progress",
        }).execute
    )
    session = await _ensure_section_started(supabase, row.data[0])
    return _client_payload(session)


class SectionDoneRequest(BaseModel):
    section: str
    # The module's own result summary (band, correct/total, grade...). Stored as-is
    # and revealed only once the whole mock is complete — never shown mid-mock.
    result: Optional[Dict[str, Any]] = None


@router.post("/{mock_id}/section-done")
async def section_done(
    mock_id: str,
    request: SectionDoneRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """A section's player calls this right after it submits to its own module.
    Advances the mock to the next section; after Writing the mock parks at
    `awaiting_speaking` (LRW captured, results still locked)."""
    supabase = get_supabase()
    session = await _load_owned(supabase, mock_id, current_user.id)

    if session["status"] != "in_progress":
        raise HTTPException(status_code=409, detail="This mock is no longer in the answering phase.")
    if request.section != session.get("current_section"):
        raise HTTPException(
            status_code=409,
            detail=f"Out of order — the current section is {session.get('current_section')}.",
        )

    results = dict(session.get("results") or {})
    results[request.section] = request.result or {"done": True}

    idx = SECTION_ORDER.index(request.section)
    next_section = SECTION_ORDER[idx + 1] if idx + 1 < len(SECTION_ORDER) else None

    update: Dict[str, Any] = {"results": results, "updated_at": _now_iso()}
    if next_section:
        update["current_section"] = next_section
    else:
        # LRW finished. Phase 1 terminal state: Speaking still pending, results locked.
        update["current_section"] = None
        update["status"] = "awaiting_speaking"

    await run_sync(
        supabase.table("mock_test_sessions").update(update).eq("id", mock_id).execute
    )
    return {"next_section": next_section, "status": update.get("status", "in_progress")}


# ── SPEAKING: two role plays, taken separately (real OET gives two different
# role-play cards; no hard timer here either, same as standalone speaking
# practice -- the live conversation paces itself, the student ends it) ───────

def _next_speaking(session: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    """(roleplay_number, scenario_id) for whichever role play hasn't been
    recorded yet, or None once both are in. Derived from `results` alone --
    no extra "current roleplay" column needed."""
    results = session.get("results") or {}
    if "speaking_1" not in results:
        sid = session.get("speaking_scenario_id_1")
        return (1, sid) if sid else None
    if "speaking_2" not in results:
        sid = session.get("speaking_scenario_id_2")
        return (2, sid) if sid else None
    return None


def _combine_speaking(r1: Dict[str, Any], r2: Dict[str, Any]) -> Dict[str, Any]:
    """Real OET judges both role plays together per-criterion; that needs a
    holistic re-score across both transcripts. Averaging the two independent
    overall_band scores is the honest-enough stand-in for now.
    ponytail: upgrade to a combined AI re-score if exam-parity precision matters."""
    band_1 = float(r1.get("overall_band") or 0)
    band_2 = float(r2.get("overall_band") or 0)
    return {"roleplay_1": r1, "roleplay_2": r2, "overall_band": round((band_1 + band_2) / 2, 1)}


@router.get("/{mock_id}/speaking/next")
async def speaking_next(
    mock_id: str,
    current_user: UserInfo = Depends(get_current_user),
):
    """Which role play the speaking player should load: 1 (first load) or 2
    (after role play 1 is recorded). 409 once the mock isn't in the speaking
    phase (still doing LRW, or both role plays already done)."""
    supabase = get_supabase()
    session = await _load_owned(supabase, mock_id, current_user.id)
    if session["status"] != "awaiting_speaking":
        raise HTTPException(status_code=409, detail="Speaking isn't available yet, or this mock is already complete.")
    nxt = _next_speaking(session)
    if not nxt:
        raise HTTPException(status_code=409, detail="Both role plays are already recorded.")
    roleplay, scenario_id = nxt
    return {"roleplay": roleplay, "scenario_id": scenario_id}


class SpeakingRoleplayDoneRequest(BaseModel):
    # The module's own result summary -- just {"overall_band": ...}. Stored as-is
    # and revealed only once the whole mock is complete, same as section-done.
    result: Optional[Dict[str, Any]] = None


@router.post("/{mock_id}/speaking/{roleplay}/done")
async def speaking_roleplay_done(
    mock_id: str,
    roleplay: int,
    request: SpeakingRoleplayDoneRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """Record one role play's result. After role play 1: returns the next role
    play to load. After role play 2: combines both, unlocks the mock
    (`complete`), and the report is ready at GET /{mock_id}/result."""
    if roleplay not in (1, 2):
        raise HTTPException(status_code=400, detail="roleplay must be 1 or 2")

    supabase = get_supabase()
    session = await _load_owned(supabase, mock_id, current_user.id)
    if session["status"] != "awaiting_speaking":
        raise HTTPException(status_code=409, detail="This mock isn't in the speaking phase.")

    nxt = _next_speaking(session)
    if not nxt or nxt[0] != roleplay:
        expected = nxt[0] if nxt else "none — both are already recorded"
        raise HTTPException(status_code=409, detail=f"Out of order — expected role play {expected}.")

    results = dict(session.get("results") or {})
    results[f"speaking_{roleplay}"] = request.result or {}

    if roleplay == 1:
        await run_sync(
            supabase.table("mock_test_sessions").update(
                {"results": results, "updated_at": _now_iso()}
            ).eq("id", mock_id).execute
        )
        return {"next_roleplay": 2, "next_scenario_id": session.get("speaking_scenario_id_2"), "status": "awaiting_speaking"}

    results["speaking"] = _combine_speaking(results.get("speaking_1") or {}, results.get("speaking_2") or {})
    await run_sync(
        supabase.table("mock_test_sessions").update(
            {"results": results, "status": "complete", "updated_at": _now_iso()}
        ).eq("id", mock_id).execute
    )
    return {"next_roleplay": None, "status": "complete"}


@router.get("/{mock_id}/result")
async def mock_result(
    mock_id: str,
    current_user: UserInfo = Depends(get_current_user),
):
    """The final report — but locked until the mock is `complete`. Phase 1 never
    reaches complete (that needs the Speaking mock), so this returns `locked: true`
    with the sections captured so far, driving the 'finish Speaking to unlock' screen."""
    supabase = get_supabase()
    session = await _load_owned(supabase, mock_id, current_user.id)

    if session["status"] != "complete":
        return {
            "locked": True,
            "status": session["status"],
            "completed": list((session.get("results") or {}).keys()),
        }
    return {"locked": False, "status": "complete", "results": session.get("results") or {}}
