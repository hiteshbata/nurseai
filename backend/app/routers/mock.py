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
import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.core.supabase import get_supabase
from app.core.threading import run_sync
from app.core.rate_limit import SlidingWindowRateLimiter
from app.routers.auth import get_current_user, UserInfo, _client_ip
from app.routers.admin import require_admin, require_owner
from app.services.plan_gating import has_effective_module_access, get_plan_from_profile
from app.services.institution_access import get_effective_speaking_limit
from app.routers.sessions import _usage_payload, get_month_start_utc
from app.services.assessment_versioning import (
    publish_mock_version, latest_version_id, get_version_row,
    list_version_rows, get_version_row_for_parent,
    display_names_by_user_id, publisher_display,
)
from app.services.assessment_validation import validate_mock_test

router = APIRouter(prefix="/mock", tags=["mock"])
logger = logging.getLogger(__name__)

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


# ── staleness guard (a pack/session's frozen content ids may have since been
# unpublished by an admin -- Mock Test is a dynamic-reference design, see
# reading.py's/listening.py's/writing.py's own is_active checks on every
# content fetch, so this only closes the ORCHESTRATION-layer gap: without it,
# a stale pack still LISTS and STARTS, and a stale session still ADVANCES,
# right up until the section player's own fetch 404s on the student mid-mock) ─

CONTENT_TABLE = {"listening": "listening_tests", "reading": "reading_tests", "writing": "scenarios", "speaking": "scenarios"}


def _content_is_active(supabase, module: str, content_id: Optional[int], version_id: Optional[int] = None) -> bool:
    """Gate right before handing a student into one section, so a section that
    went stale since the mock was built/started fails clearly instead of the
    section player hitting a bare 404 partway through.

    version_id (RC4.1): if this session already has an immutable Reading/
    Listening version pinned for the section it's advancing into, that
    version's content is self-contained and frozen -- it no longer depends
    on the live table's is_active, so admin unpublishing/editing the live
    test after the student started must not block them mid-mock. Legacy
    sessions (version_id is None) keep the original live-table check."""
    if content_id is None:
        return False
    if version_id is not None:
        return True
    row = supabase.table(CONTENT_TABLE[module]).select("id").eq("id", content_id).eq("is_active", True).execute()
    return bool(row.data)


def _active_content_id_sets(supabase) -> Dict[str, set]:
    """Every currently-active id per content table, fetched once so checking a
    whole pack's 5 frozen picks is 3 queries total instead of 5 per pack."""
    return {
        "listening_tests": {r["id"] for r in supabase.table("listening_tests").select("id").eq("is_active", True).execute().data},
        "reading_tests": {r["id"] for r in supabase.table("reading_tests").select("id").eq("is_active", True).execute().data},
        "scenarios": {r["id"] for r in supabase.table("scenarios").select("id").eq("is_active", True).execute().data},
    }


def _pack_is_servable(row: Dict[str, Any], active: Dict[str, set]) -> bool:
    """False if any of a pack's (or session's) 5 frozen content ids is missing
    or has gone inactive since it was frozen."""
    return (
        row.get("listening_test_id") in active["listening_tests"]
        and row.get("reading_test_id") in active["reading_tests"]
        and row.get("writing_scenario_id") in active["scenarios"]
        and row.get("speaking_scenario_id_1") in active["scenarios"]
        and row.get("speaking_scenario_id_2") in active["scenarios"]
    )


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


_VERSION_KEY = {"reading": "reading_test_version_id", "listening": "listening_test_version_id"}


def get_pinned_test_version_id(supabase, user_id: str, module: str, test_id: int) -> Optional[int]:
    """RC4.1: if `user_id` is mid-mock on exactly this module/test, and that
    session has an immutable version pinned for it (see start_mock), return
    that version's id -- reading.py/listening.py grade and serve against it
    instead of the live tables, so a mock leg's content can never drift from
    what section-done recorded. None for a standalone (non-mock) attempt, no
    open mock at all, or a legacy session that predates versioning -- the
    caller falls back to the latest published version (or the live path)."""
    version_col = _VERSION_KEY.get(module)
    if version_col is None:
        return None
    res = (
        supabase.table("mock_test_sessions").select("*")
        .eq("user_id", user_id).eq("status", "in_progress")
        .order("created_at", desc=True).limit(1).execute()
    )
    if not res.data:
        return None
    session = res.data[0]
    if session.get("current_section") != module or session.get(CONTENT_KEY[module]) != test_id:
        return None
    return session.get(version_col)


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
    student has already completed each one (picker offers Retake vs Start).
    Drops any pack whose frozen content has gone inactive since it was built
    -- see _pack_is_servable -- so the picker never offers one that would
    404 partway through."""
    supabase = get_supabase()
    packs = (await run_sync(
        supabase.table("mock_tests").select("*").eq("is_active", True).order("id").execute
    )).data
    if not packs:
        return []
    active = await run_sync(_active_content_id_sets, supabase)
    packs = [p for p in packs if _pack_is_servable(p, active)]
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
    has_mock_access = await run_sync(has_effective_module_access, supabase, current_user.id, plan, "mock_tests")
    if not has_mock_access and not current_user.is_anonymous and plan != "free":
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
        session = existing.data[0]
        active = await run_sync(_active_content_id_sets, supabase)
        if not _pack_is_servable(session, active):
            raise HTTPException(
                status_code=409,
                detail="This mock test can't continue — some of its content is no longer available. Contact support.",
            )
        session = await _ensure_section_started(supabase, session)
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

    active = await run_sync(_active_content_id_sets, supabase)
    if not _pack_is_servable(p, active):
        raise HTTPException(status_code=404, detail="This mock test pack isn't available.")

    # RC4.1: pin this attempt to the pack's newest immutable Mock Test Version,
    # if one exists (packs created via admin_generate_mock_test always have
    # one; a legacy pack from before RC4.1 -- or before the backfill runs --
    # won't, and the session simply starts with all three version columns
    # null, same as before this feature existed).
    mock_version_id = await run_sync(latest_version_id, supabase, "mock_test_versions", "mock_test_id", p["id"])
    version_stamps: Dict[str, Any] = {}
    if mock_version_id is not None:
        mock_version = await run_sync(get_version_row, supabase, "mock_test_versions", mock_version_id)
        version_stamps = {
            "mock_test_version_id": mock_version_id,
            "reading_test_version_id": mock_version["snapshot"]["reading_test_version_id"],
            "listening_test_version_id": mock_version["snapshot"]["listening_test_version_id"],
        }

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
            **version_stamps,
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
    pack = row.data[0]

    # RC4.1: a pack has no draft state (is_active defaults true, servable to
    # students the instant it's generated) -- so generation IS this pack's
    # first publish. Best-effort: picks were just drawn from active, already-
    # published-at-least-once content (see the pools above), so this should
    # always succeed; if it doesn't, the pack still works via the legacy
    # path and an admin can retry with POST /mock/admin/tests/{id}/publish.
    try:
        await run_sync(publish_mock_version, supabase, pack["id"], current_user.id)
    except Exception as e:
        logger.warning("[mock] Version 1 for pack %s failed at generation: %s", pack["id"], str(e)[:300])
    return pack


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

    # RC4.1: current version number per pack, so the admin list can show
    # "v2" etc. Highest `version` per mock_test_id; None for a pack that
    # hasn't gone through the versioned publish flow yet.
    version_rows = (await run_sync(
        supabase.table("mock_test_versions").select("mock_test_id, version")
        .in_("mock_test_id", [p["id"] for p in packs]).execute
    )).data
    current_version: Dict[int, int] = {}
    for v in version_rows:
        current_version[v["mock_test_id"]] = max(current_version.get(v["mock_test_id"], 0), v["version"])

    return [{
        **p,
        "listening_title": listening_titles.get(p.get("listening_test_id")),
        "reading_title": reading_titles.get(p.get("reading_test_id")),
        "writing_title": scenario_titles.get(p.get("writing_scenario_id")),
        "speaking_title_1": scenario_titles.get(p.get("speaking_scenario_id_1")),
        "speaking_title_2": scenario_titles.get(p.get("speaking_scenario_id_2")),
        "current_version": current_version.get(p["id"]),
    } for p in packs]


@router.get("/admin/tests/{mock_test_id}/preview")
async def admin_preview_mock_test(mock_test_id: int, _admin=Depends(require_admin)):
    """RC4.2: resolved pack content (same title lookups as admin_list_mock_tests,
    for one pack) plus `validation` -- the exact same result Owner publish
    would get (assessment_validation.validate_mock_test), so an admin can see
    what's blocking publish before reaching for the Owner-only button.

    Deliberately NOT built on assessment_versioning.build_mock_snapshot --
    that function 409s if the pack's Reading/Listening has no published
    version yet, which is exactly the state a preview needs to surface, not
    raise on. Admin-level (require_admin), matching Reading/Listening's own
    /preview gate -- publish itself stays owner-only."""
    supabase = get_supabase()
    pack = (await run_sync(supabase.table("mock_tests").select("*").eq("id", mock_test_id).execute)).data
    if not pack:
        raise HTTPException(status_code=404, detail="Mock Test pack not found")
    p = pack[0]

    async def _title(table: str, content_id: Optional[int]) -> Optional[str]:
        if not content_id:
            return None
        rows = (await run_sync(supabase.table(table).select("id, title").eq("id", content_id).execute)).data
        return rows[0]["title"] if rows else None

    validation = await run_sync(validate_mock_test, supabase, mock_test_id)
    return {
        **p,
        "listening_title": await _title("listening_tests", p.get("listening_test_id")),
        "reading_title": await _title("reading_tests", p.get("reading_test_id")),
        "writing_title": await _title("scenarios", p.get("writing_scenario_id")),
        "speaking_title_1": await _title("scenarios", p.get("speaking_scenario_id_1")),
        "speaking_title_2": await _title("scenarios", p.get("speaking_scenario_id_2")),
        "validation": validation,
    }


@router.get("/admin/tests/{mock_test_id}/versions")
async def list_mock_test_versions(mock_test_id: int, _admin=Depends(require_admin)):
    """RC4.3.1: lightweight history of every immutable Mock Test Version this
    pack has had -- newest first, no snapshot payload. is_current computed
    from the actual max version present, not array position.

    RC4.3.2.3: adds published_by_display -- one bulk lookup for the whole
    list, not per-row (see assessment_versioning.display_names_by_user_id)."""
    supabase = get_supabase()
    pack = await run_sync(supabase.table("mock_tests").select("id").eq("id", mock_test_id).execute)
    if not pack.data:
        raise HTTPException(status_code=404, detail="Mock Test pack not found")
    rows = await run_sync(list_version_rows, supabase, "mock_test_versions", "mock_test_id", mock_test_id)
    current = rows[0]["version"] if rows else None
    display_by_id = await run_sync(display_names_by_user_id, supabase, {r.get("published_by") for r in rows})
    return {"versions": [{
        "id": r["id"],
        "version": r["version"],
        "published_at": r.get("published_at"),
        "published_by": r.get("published_by"),
        "published_by_display": publisher_display(display_by_id, r.get("published_by")),
        "is_current": r["version"] == current,
    } for r in rows]}


@router.get("/admin/tests/{mock_test_id}/versions/{version_id}")
async def get_mock_test_version(mock_test_id: int, version_id: int, _admin=Depends(require_admin)):
    """RC4.3.1: the frozen snapshot for one Mock Test Version, read-only.
    404s if the pack doesn't exist, the version doesn't exist, or the
    version belongs to a different pack.

    RC4.3.2.3: adds published_by_display (RC4.3.2.1 helper, reused as-is)."""
    supabase = get_supabase()
    pack = await run_sync(supabase.table("mock_tests").select("id").eq("id", mock_test_id).execute)
    if not pack.data:
        raise HTTPException(status_code=404, detail="Mock Test pack not found")
    row = await run_sync(
        get_version_row_for_parent, supabase, "mock_test_versions", "mock_test_id", mock_test_id, version_id
    )
    published_by = row.get("published_by")
    display_by_id = await run_sync(display_names_by_user_id, supabase, {published_by})
    return {**row, "published_by_display": publisher_display(display_by_id, published_by)}


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


@router.post("/admin/tests/{mock_test_id}/publish")
async def admin_publish_mock_test_version(
    mock_test_id: int,
    current_user: UserInfo = Depends(require_owner),
):
    """RC4.1: cut a new immutable Mock Test Version for an existing pack,
    resolving Reading/Listening by reference to whichever version of each is
    currently newest, and Writing/Speaking as a fresh embedded snapshot of
    their current content. Use this after the pack's Reading or Listening
    test has been re-published (a newer version now exists) and you want new
    attempts on this pack to pick it up -- existing sessions already pinned
    to an earlier Mock Test Version are unaffected (see start_mock).

    RC4.1: owner-gated -- cutting an immutable production version is
    high-impact (see require_owner). Normal mock admin ops (generate,
    activate/deactivate) stay admin-level.

    RC4.2: hard-blocking validation gate composing Reading/Listening's own
    validators against this pack's picks, plus Mock-specific checks (all 5
    slots filled, referenced Reading/Listening already have a published
    version, Writing/Speaking active with required fields, the two Speaking
    scenarios distinct). A failing pack 409s with structured errors and
    never reaches publish_mock_version -- no version cut, no partial write.
    admin_generate_mock_test's own best-effort auto-publish is deliberately
    NOT routed through this gate (see that function's docstring)."""
    supabase = get_supabase()
    existing = await run_sync(supabase.table("mock_tests").select("id").eq("id", mock_test_id).execute)
    if not existing.data:
        raise HTTPException(status_code=404, detail="Mock Test pack not found")
    validation = await run_sync(validate_mock_test, supabase, mock_test_id)
    if not validation["valid"]:
        raise HTTPException(status_code=409, detail=validation)
    version_row = await run_sync(publish_mock_version, supabase, mock_test_id, current_user.id)
    return {"success": True, "version": version_row["version"], "id": version_row["id"]}


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

    idx = SECTION_ORDER.index(request.section)
    next_section = SECTION_ORDER[idx + 1] if idx + 1 < len(SECTION_ORDER) else None
    # Don't advance the student into a section whose content has gone stale
    # since the mock was built/started -- fail clearly here instead of the
    # next section player hitting a bare 404 right after this call. Skipped
    # for a section this session has an immutable version pinned for (RC4.1).
    next_version_id = session.get(_VERSION_KEY[next_section]) if next_section in _VERSION_KEY else None
    if next_section and not await run_sync(_content_is_active, supabase, next_section, session.get(CONTENT_KEY[next_section]), next_version_id):
        raise HTTPException(
            status_code=409,
            detail=f"The {next_section} section of this mock is no longer available. Contact support.",
        )

    results = dict(session.get("results") or {})
    results[request.section] = request.result or {"done": True}

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
    if not await run_sync(_content_is_active, supabase, "speaking", scenario_id):
        raise HTTPException(
            status_code=409,
            detail="This mock's Speaking role play is no longer available. Contact support.",
        )

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
        plan_limit = await run_sync(get_effective_speaking_limit, supabase, current_user.id, plan)
        usage = _usage_payload(profile.data[0] if profile.data else {}, get_month_start_utc(), plan_limit)
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
