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

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.core.supabase import get_supabase
from app.core.threading import run_sync
from app.core.rate_limit import SlidingWindowRateLimiter
from app.routers.auth import get_current_user, UserInfo, _client_ip
from app.routers.admin import require_admin
from app.services.plan_gating import has_mock_test_access, get_plan_from_profile
from app.routers.sessions import _usage_payload, get_month_start_utc

router = APIRouter(prefix="/mock", tags=["mock"])

# Anonymous free-trial mock starts (see /tools/oet-mock-test-free) -- caps how
# many distinct anonymous accounts one IP can spin up fresh mocks for per day.
# The real cap is one lifetime attempt per anonymous user_id (checked in
# start_mock itself); this is defense-in-depth against a script farming many
# anonymous accounts from one machine.
_free_mock_start_limiter = SlidingWindowRateLimiter(3, 86400, name="mock:free_start")

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


# ── mock test packs (admin-curated, numbered "Mock Test 1/2/3...") ─────
# Phase 1/2 assembled content randomly per attempt (see git history). That
# meant slow "assembling your paper..." start-up and no way to guarantee two
# attempts never draw the same content. Packs are pre-built instead: an admin
# clicks Generate, content is picked once and frozen into a `mock_tests` row,
# and a student's /mock/start just points at one (see start_mock below).

def _pick_unused(pool: List[int], used: set, count: int) -> Optional[List[int]]:
    """Sample `count` ids from `pool` that aren't already in `used`. None if
    fewer than `count` fresh ones remain -- the caller turns that into a
    'need more X content' error rather than silently repeating a pack."""
    fresh = [i for i in pool if i not in used]
    if len(fresh) < count:
        return None
    return random.sample(fresh, count)


def _used_pack_content_ids(supabase) -> Dict[str, set]:
    """Every content id already claimed by an existing pack (active or not --
    once a pack has shipped, its content stays 'spent' so a later pack can't
    duplicate it), grouped by pool so generation can subtract them out."""
    rows = supabase.table("mock_tests").select(
        "listening_test_id, reading_test_id, writing_scenario_id, "
        "speaking_scenario_id_1, speaking_scenario_id_2"
    ).execute().data
    return {
        "listening": {r["listening_test_id"] for r in rows if r.get("listening_test_id")},
        "reading": {r["reading_test_id"] for r in rows if r.get("reading_test_id")},
        "writing": {r["writing_scenario_id"] for r in rows if r.get("writing_scenario_id")},
        "speaking": (
            {r["speaking_scenario_id_1"] for r in rows if r.get("speaking_scenario_id_1")}
            | {r["speaking_scenario_id_2"] for r in rows if r.get("speaking_scenario_id_2")}
        ),
    }


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


def has_mock_section_access(supabase, user_id: str, module: str, content_id: int) -> bool:
    """True if `user_id` has a live mock (the free-trial anonymous flow's one
    lifetime attempt, or any paid attempt) whose current section/module is
    `module` and whose frozen content id matches `content_id`. Lets an
    anonymous free-trial user submit exactly their own mock's section without
    opening reading/listening's plan-gated endpoints generally -- see
    reading.py's _require_reading_plan / listening.py's _require_listening_plan."""
    res = (
        supabase.table("mock_test_sessions").select("*")
        .eq("user_id", user_id).in_("status", OPEN_STATUSES)
        .order("created_at", desc=True).limit(1).execute()
    )
    if not res.data:
        return False
    session = res.data[0]
    if module == "speaking":
        return session["status"] == "awaiting_speaking" and content_id in (
            session.get("speaking_scenario_id_1"), session.get("speaking_scenario_id_2")
        )
    return session["status"] == "in_progress" and session.get("current_section") == module and session.get(CONTENT_KEY.get(module)) == content_id


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


@router.get("/tests")
async def list_mock_tests(current_user: UserInfo = Depends(get_current_user)):
    """Active Mock Test packs to choose from, flagged with whether this
    student has already completed each one (picker offers Retake vs Start)."""
    supabase = get_supabase()
    packs = (await run_sync(
        supabase.table("mock_tests").select("id, label").eq("is_active", True).order("id").execute
    )).data
    if not packs:
        return []
    completed_rows = (await run_sync(
        supabase.table("mock_test_sessions").select("mock_test_id")
        .eq("user_id", current_user.id).eq("status", "complete")
        .not_.is_("mock_test_id", "null").execute
    )).data
    completed_ids = {r["mock_test_id"] for r in completed_rows}
    return [{"id": p["id"], "label": p["label"], "completed": p["id"] in completed_ids} for p in packs]


class StartMockRequest(BaseModel):
    mock_test_id: int


@router.post("/start")
async def start_mock(req: StartMockRequest, request: Request, current_user: UserInfo = Depends(get_current_user)):
    """Resume an open mock, or start a fresh attempt on the given pre-built
    Mock Test pack -- content was frozen once at generation time (see
    POST /mock/admin/generate), not re-randomized per attempt."""
    supabase = get_supabase()

    profile = await run_sync(
        supabase.table("user_profiles").select("plan, plan_expires_at").eq("user_id", current_user.id).execute
    )
    plan = get_plan_from_profile(profile.data[0] if profile.data else {})
    # Anonymous (see /tools/oet-mock-test-free) and free-plan students both skip
    # the Elite-only gate here -- eligibility for a free trial is enforced below
    # instead (one lifetime attempt, an IP rate limit for anonymous), not by plan.
    # Basic/Pro get neither: Mock Test stays an Elite-or-free-trial feature.
    if not has_mock_test_access(plan) and not current_user.is_anonymous and plan != "free":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Mock Test requires the Elite plan",
                "upgrade_required": True,
                "current_plan": plan,
            },
        )

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

    if current_user.is_anonymous or plan == "free":
        # One lifetime free attempt per anonymous or free-plan account, regardless
        # of its status -- a completed or awaiting-speaking mock still counts as used.
        prior = await run_sync(
            supabase.table("mock_test_sessions").select("id").eq("user_id", current_user.id).limit(1).execute
        )
        if prior.data:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "You've already used your free mock test. Upgrade to Elite for unlimited mock tests.",
                    "upgrade_required": True,
                    "current_plan": plan,
                },
            )
        if current_user.is_anonymous and _free_mock_start_limiter.is_rate_limited(_client_ip(request)):
            raise HTTPException(status_code=429, detail="Too many free mock test attempts from this network — please try again later.")

    pack = await run_sync(
        supabase.table("mock_tests").select("*").eq("id", req.mock_test_id).eq("is_active", True).execute
    )
    if not pack.data:
        raise HTTPException(status_code=404, detail="This mock test pack isn't available.")
    p = pack.data[0]

    row = await run_sync(
        supabase.table("mock_test_sessions").insert({
            "user_id": current_user.id,
            "mock_test_id": p["id"],
            "listening_test_id": p["listening_test_id"],
            "reading_test_id": p["reading_test_id"],
            "writing_scenario_id": p["writing_scenario_id"],
            "speaking_scenario_id_1": p["speaking_scenario_id_1"],
            "speaking_scenario_id_2": p["speaking_scenario_id_2"],
            "current_section": SECTION_ORDER[0],
            "status": "in_progress",
        }).execute
    )
    session = await _ensure_section_started(supabase, row.data[0])
    return _client_payload(session)


# ── ADMIN: build + manage packs ─────────────────────────────────────────

@router.post("/admin/generate")
async def admin_generate_mock_test(current_user: UserInfo = Depends(require_admin)):
    """Build the next numbered pack from active content not already claimed
    by an earlier pack. 409 (naming which pool ran dry) instead of silently
    repeating content -- add more of that content type and generate again."""
    supabase = get_supabase()
    used = _used_pack_content_ids(supabase)

    picks: Dict[str, List[int]] = {}
    missing: List[str] = []
    for name, pool, key, need in [
        ("Listening", _active_listening_test_ids(supabase), "listening", 1),
        ("Reading", _active_reading_test_ids(supabase), "reading", 1),
        ("Writing", _active_writing_scenario_ids(supabase), "writing", 1),
        ("Speaking", _active_speaking_scenario_ids(supabase), "speaking", 2),
    ]:
        picked = _pick_unused(pool, used[key], need)
        if picked is None:
            missing.append(name)
        else:
            picks[key] = picked
    if missing:
        raise HTTPException(
            status_code=409,
            detail=f"Not enough unused content left to build a new pack (need more: {', '.join(missing)}).",
        )

    count = (await run_sync(supabase.table("mock_tests").select("id", count="exact").execute)).count or 0
    row = await run_sync(
        supabase.table("mock_tests").insert({
            "label": f"Mock Test {count + 1}",
            "listening_test_id": picks["listening"][0],
            "reading_test_id": picks["reading"][0],
            "writing_scenario_id": picks["writing"][0],
            "speaking_scenario_id_1": picks["speaking"][0],
            "speaking_scenario_id_2": picks["speaking"][1],
        }).execute
    )
    return row.data[0]


@router.get("/admin/tests")
async def admin_list_mock_tests(current_user: UserInfo = Depends(require_admin)):
    """Every pack with resolved content titles, for the admin management page."""
    supabase = get_supabase()
    packs = (await run_sync(supabase.table("mock_tests").select("*").order("id").execute)).data
    if not packs:
        return []

    listening_ids = {p["listening_test_id"] for p in packs if p.get("listening_test_id")}
    reading_ids = {p["reading_test_id"] for p in packs if p.get("reading_test_id")}
    scenario_ids = {
        p[k] for p in packs for k in ("writing_scenario_id", "speaking_scenario_id_1", "speaking_scenario_id_2")
        if p.get(k)
    }

    async def _titles(table: str, ids: set) -> Dict[int, str]:
        if not ids:
            return {}
        rows = (await run_sync(supabase.table(table).select("id, title").in_("id", list(ids)).execute)).data
        return {r["id"]: r["title"] for r in rows}

    listening_titles = await _titles("listening_tests", listening_ids)
    reading_titles = await _titles("reading_tests", reading_ids)
    scenario_titles = await _titles("scenarios", scenario_ids)

    return [{
        **p,
        "listening_title": listening_titles.get(p.get("listening_test_id")),
        "reading_title": reading_titles.get(p.get("reading_test_id")),
        "writing_title": scenario_titles.get(p.get("writing_scenario_id")),
        "speaking_title_1": scenario_titles.get(p.get("speaking_scenario_id_1")),
        "speaking_title_2": scenario_titles.get(p.get("speaking_scenario_id_2")),
    } for p in packs]


class MockTestActiveRequest(BaseModel):
    is_active: bool


@router.post("/admin/tests/{mock_test_id}/active")
async def admin_set_mock_test_active(
    mock_test_id: int,
    req: MockTestActiveRequest,
    current_user: UserInfo = Depends(require_admin),
):
    """Show/hide a pack from the student picker. Its content stays counted as
    'used' either way -- see _used_pack_content_ids -- so re-activating can't
    reintroduce a pack that shares content with a newer one."""
    supabase = get_supabase()
    await run_sync(
        supabase.table("mock_tests").update({"is_active": req.is_active}).eq("id", mock_test_id).execute
    )
    return {"success": True}


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

    # Each role play is a normal speaking session under the hood (see
    # speaking_realtime.py) and draws from the same monthly speaking quota as
    # standalone practice. A free-plan student needs 2 sessions left for role
    # play 1, or 1 left for role play 2 -- checked here, before either role
    # play starts, so the upgrade prompt lands at the natural "Speaking is
    # next" screen instead of mid-conversation.
    profile = await run_sync(
        supabase.table("user_profiles").select(
            "plan, plan_expires_at, sessions_used_this_month, sessions_reset_date, auto_renew_enabled, bonus_sessions"
        ).eq("user_id", current_user.id).execute
    )
    plan = get_plan_from_profile(profile.data[0] if profile.data else {})
    if plan == "free":
        usage = _usage_payload(profile.data[0] if profile.data else {}, get_month_start_utc())
        needed = 2 if roleplay == 1 else 1
        if usage["sessions_remaining"] < needed:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": f"Mock Test Speaking needs {needed} more speaking session(s) than you have left this month.",
                    "upgrade_required": True,
                    "current_plan": plan,
                },
            )

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
