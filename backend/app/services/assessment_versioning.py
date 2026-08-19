"""RC4.1 -- Assessment Immutability & Versioning.

Shared resolver/snapshot-builder + version allocator for Reading, Listening
and Mock Test. One place both the admin "publish" action and (for reading/
listening) the student serving/grading path pull from, so a published
version is always exactly what was live at the moment it was cut -- never
re-derived from (and never silently drifting with) today's live tables.

Explicitly NOT versioned here (per the approved architecture): standalone
practice content (test_id/section_id null), Writing/Speaking scenarios
(embedded as a point-in-time snapshot inside a Mock Test Version for audit,
never re-served from it -- Writing/Speaking keep serving live), and
explanation/evidence (a lazy post-submit cache, not a grading input).
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.core.supabase import get_supabase

logger = logging.getLogger(__name__)

_PART_ORDER = {"A": 0, "B": 1, "C": 2}

_MAX_VERSION_RETRIES = 5


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── version allocation (concurrency-safe) ─────────────────────────────
# Two admins (or a double-click) publishing at once must not mint the same
# version number twice. The (content_id, version) unique constraint from the
# migration is the actual safety net; this loop is the retry-on-conflict
# behavior around it -- same "duplicate key" pattern draft_publisher.py
# already uses for title races, not a new mechanism.

def _allocate_version(
    supabase, table: str, id_col: str, content_id: Any, snapshot: Dict[str, Any], published_by: Optional[str],
) -> Dict[str, Any]:
    for attempt in range(_MAX_VERSION_RETRIES):
        existing = (
            supabase.table(table).select("version")
            .eq(id_col, content_id).order("version", desc=True).limit(1).execute()
        ).data
        next_version = (existing[0]["version"] + 1) if existing else 1
        snapshot["version"] = next_version
        snapshot["published_at"] = _now_iso()
        try:
            row = supabase.table(table).insert({
                id_col: content_id,
                "version": next_version,
                "snapshot": snapshot,
                "published_by": published_by,
            }).execute().data[0]
            return row
        except Exception as e:
            if "duplicate key" in str(e).lower() and attempt < _MAX_VERSION_RETRIES - 1:
                continue
            raise
    raise HTTPException(status_code=503, detail="Could not allocate a version number -- too many concurrent publishes. Try again.")


def latest_version_id(supabase, table: str, id_col: str, content_id: Any) -> Optional[int]:
    """The id of the newest version row for this content id, or None if it
    has never been published through the versioned flow -- callers fall back
    to the legacy live-table path in that case."""
    if content_id is None:
        return None
    rows = (
        supabase.table(table).select("id")
        .eq(id_col, content_id).order("version", desc=True).limit(1).execute()
    ).data
    return rows[0]["id"] if rows else None


def get_version_row(supabase, table: str, version_id: int) -> Dict[str, Any]:
    rows = supabase.table(table).select("*").eq("id", version_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Version not found")
    return rows[0]


# ── version history (RC4.3.1) ─────────────────────────────────────────
# Read-only listing/lookup on top of the RC4.1 version tables -- no new
# tables, no new write path. Shared across Reading/Listening/Mock so the
# three routers' /versions endpoints don't each hand-roll the same query.

def list_version_rows(supabase, table: str, id_col: str, content_id: Any) -> List[Dict[str, Any]]:
    """Every version row for one content id, newest first. Metadata-only
    projection is the caller's job (list endpoints shouldn't ship the full
    snapshot); this returns full rows so a detail endpoint can also use it
    if ever needed."""
    return (
        supabase.table(table).select("*")
        .eq(id_col, content_id).order("version", desc=True).execute()
    ).data


def get_version_row_for_parent(supabase, table: str, id_col: str, parent_id: Any, version_id: int) -> Dict[str, Any]:
    """Same as get_version_row, but also requires the version to belong to
    the given parent id -- so GET .../tests/{test_id}/versions/{version_id}
    can never return a version that actually belongs to a different test."""
    rows = supabase.table(table).select("*").eq("id", version_id).eq(id_col, parent_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Version not found")
    return rows[0]


# ── publisher identity (RC4.3.2.1) ─────────────────────────────────────
# `published_by` on a version row is a raw auth.users UUID -- not something
# an admin should have to read. Resolved via the public.users mirror table
# (kept in sync by auth.py's get_current_user on every authenticated
# request -- see supabase/migrations/20260718000800_users_mirror.sql), the
# exact same lookup admin.py's _emails_by_user_id already uses for User 360,
# rather than a second identity mechanism. No auth.users access, no new
# columns, no RLS change: public.users already carries only id/email/name.

def display_names_by_user_id(supabase, user_ids: set) -> Dict[str, str]:
    """Bulk id -> human-readable identity (name, falling back to email).
    Ids with no mirror row (deleted account, or never made an authenticated
    request since the mirror was introduced) are simply absent from the
    result -- callers supply their own "unknown" fallback for those."""
    ids = [i for i in {i for i in user_ids if i}]
    if not ids:
        return {}
    rows = supabase.table("users").select("id, email, name").in_("id", ids).execute().data
    return {r["id"]: name for r in rows if (name := (r.get("name") or r.get("email") or ""))}


def publisher_display(display_by_id: Dict[str, str], published_by: Optional[str]) -> Optional[str]:
    """None when there's no publisher recorded at all (e.g. a version cut by
    a system backfill); "Unknown staff member" when a UUID is recorded but
    the mirror has no row for it; the resolved name/email otherwise."""
    if not published_by:
        return None
    return display_by_id.get(published_by) or "Unknown staff member"


# ── READING ────────────────────────────────────────────────────────────

def build_reading_snapshot(supabase, test_id: int) -> Dict[str, Any]:
    """Resolve the fully-resolved Reading assessment as it stands RIGHT NOW.
    Only active passages/questions are frozen -- a passage an admin already
    hid before publishing was never meant to reach students. `title` is
    included on each passage beyond the architecture doc's minimum shape
    (which lists only passage_id/part/difficulty/body) because the student
    player displays it; omitting it would silently break passage headers."""
    t = supabase.table("reading_tests").select("id, title").eq("id", test_id).execute()
    if not t.data:
        raise HTTPException(status_code=404, detail="Test not found")

    passages = supabase.table("reading_passages").select(
        "id, title, part, difficulty, body"
    ).eq("test_id", test_id).eq("is_active", True).execute().data
    pids = [p["id"] for p in passages]
    questions = supabase.table("questions").select(
        "id, passage_id, type, content, options, correct_answer"
    ).in_("passage_id", pids).execute().data if pids else []

    return {
        "test_id": test_id,
        "title": t.data[0]["title"],
        "passages": [{
            "passage_id": p["id"], "title": p["title"], "part": p["part"],
            "difficulty": p["difficulty"], "body": p["body"],
        } for p in passages],
        "questions": [{
            "question_id": q["id"], "passage_id": q["passage_id"],
            "type": "short_answer" if q.get("type") == "short_answer" else "mcq",
            "content": q["content"],
            "options": json.loads(q["options"]) if q.get("options") else [],
            "correct_answer": q.get("correct_answer"),
        } for q in questions],
    }


def publish_reading_version(supabase, test_id: int, published_by: Optional[str]) -> Dict[str, Any]:
    snapshot = build_reading_snapshot(supabase, test_id)
    return _allocate_version(supabase, "reading_test_versions", "reading_test_id", test_id, snapshot, published_by)


def reading_snapshot_student_payload(version_row: Dict[str, Any]) -> Dict[str, Any]:
    """Shape a version's frozen snapshot into the exact contract
    reading.py's _load_test_payload already returns to the student player
    (correct_answer withheld) -- so the player doesn't need to know whether
    it's looking at a version or the legacy live path."""
    snap = version_row["snapshot"]
    q_by_passage: Dict[int, List[dict]] = {}
    for q in snap["questions"]:
        q_by_passage.setdefault(q["passage_id"], []).append(q)
    passages = sorted(snap["passages"], key=lambda p: (_PART_ORDER.get(p["part"], 9), p["passage_id"]))
    return {
        "id": snap["test_id"],
        "title": snap["title"],
        "passages": [{
            "id": p["passage_id"], "title": p.get("title", ""), "part": p["part"], "body": p["body"],
            "questions": [{
                "id": q["question_id"], "content": q["content"],
                "type": q["type"], "options": q.get("options") or [],
            } for q in sorted(q_by_passage.get(p["passage_id"], []), key=lambda x: x["question_id"])],
        } for p in passages],
    }


def reading_snapshot_questions_by_id(version_row: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    """Same shape reading.py's grading path expects from a live `questions`
    select (id/content/correct_answer/type) -- grading against a version
    never touches the live table."""
    snap = version_row["snapshot"]
    return {
        q["question_id"]: {
            "id": q["question_id"], "content": q["content"],
            "correct_answer": q.get("correct_answer"), "type": q["type"],
        } for q in snap["questions"]
    }


# ── LISTENING ──────────────────────────────────────────────────────────

def build_listening_snapshot(supabase, test_id: int) -> Dict[str, Any]:
    """Freezes the RESOLVED audio_url string, never the audio bytes -- audio
    already lives at a stable UUID-named path in the public bucket and is
    never overwritten in place (replacing a section's audio uploads a new
    object and repoints audio_url), so the URL alone is enough to keep old
    versions playable forever without re-uploading anything."""
    t = supabase.table("listening_tests").select("id, title, part_audio, part_audio_times").eq("id", test_id).execute()
    if not t.data:
        raise HTTPException(status_code=404, detail="Test not found")

    sections = supabase.table("listening_sections").select(
        "id, title, part, difficulty, audio_url, transcript, body, section_seq, prep_seconds, audio_mode"
    ).eq("test_id", test_id).eq("is_active", True).execute().data
    sids = [s["id"] for s in sections]
    questions = supabase.table("questions").select(
        "id, section_id, type, content, options, correct_answer"
    ).in_("section_id", sids).execute().data if sids else []

    return {
        "test_id": test_id,
        "title": t.data[0]["title"],
        "part_audio": t.data[0].get("part_audio") or {},
        "part_audio_times": t.data[0].get("part_audio_times") or {},
        "sections": [{
            "section_id": s["id"], "title": s["title"], "part": s["part"], "difficulty": s["difficulty"],
            "audio_url": s.get("audio_url"), "transcript": s.get("transcript"), "body": s.get("body"),
            "section_seq": s.get("section_seq"), "prep_seconds": s.get("prep_seconds"), "audio_mode": s.get("audio_mode"),
        } for s in sections],
        "questions": [{
            "question_id": q["id"], "section_id": q["section_id"],
            "type": "short_answer" if q.get("type") == "short_answer" else "mcq",
            "content": q["content"],
            "options": json.loads(q["options"]) if q.get("options") else [],
            "correct_answer": q.get("correct_answer"),
        } for q in questions],
    }


def publish_listening_version(supabase, test_id: int, published_by: Optional[str]) -> Dict[str, Any]:
    snapshot = build_listening_snapshot(supabase, test_id)
    return _allocate_version(supabase, "listening_test_versions", "listening_test_id", test_id, snapshot, published_by)


def listening_snapshot_student_payload(version_row: Dict[str, Any]) -> Dict[str, Any]:
    snap = version_row["snapshot"]
    q_by_section: Dict[int, List[dict]] = {}
    for q in snap["questions"]:
        q_by_section.setdefault(q["section_id"], []).append(q)
    sections = sorted(snap["sections"], key=lambda s: (_PART_ORDER.get(s["part"], 9), s["section_id"]))
    return {
        "id": snap["test_id"],
        "title": snap["title"],
        "part_audio": snap.get("part_audio") or {},
        "sections": [{
            "id": s["section_id"], "title": s["title"], "part": s["part"],
            "audio_url": s.get("audio_url"), "body": s.get("body"),
            "questions": [{
                "id": q["question_id"], "content": q["content"],
                "type": q["type"], "options": q.get("options") or [],
            } for q in sorted(q_by_section.get(s["section_id"], []), key=lambda x: x["question_id"])],
        } for s in sections],
    }


def listening_snapshot_questions_by_id(version_row: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    snap = version_row["snapshot"]
    return {
        q["question_id"]: {
            "id": q["question_id"], "content": q["content"],
            "correct_answer": q.get("correct_answer"), "type": q["type"],
        } for q in snap["questions"]
    }


def listening_snapshot_transcripts(version_row: Dict[str, Any]) -> Dict[int, Any]:
    """section_id -> transcript, revealed to the student only after submit --
    mirrors what listening.py's submit_test already returns from the live
    section rows."""
    snap = version_row["snapshot"]
    return {s["section_id"]: s.get("transcript") for s in snap["sections"]}


# ── MOCK TEST ──────────────────────────────────────────────────────────

_WRITING_SCENARIO_FIELDS = "id, title, setting, nurse_card, scoring_criteria, key_points, difficulty, specialty"
_SPEAKING_SCENARIO_FIELDS = (
    "id, title, setting, nurse_card, interlocutor_card, scoring_criteria, "
    "difficulty, specialty, voice_config, patient_gender, patient_age"
)


def _writing_scenario_snapshot(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "scenario_id": row["id"], "title": row["title"], "setting": row.get("setting"),
        "nurse_card": row.get("nurse_card"), "scoring_criteria": row.get("scoring_criteria"),
        "key_points": row.get("key_points"), "difficulty": row.get("difficulty"), "specialty": row.get("specialty"),
    }


def _speaking_scenario_snapshot(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "scenario_id": row["id"], "title": row["title"], "setting": row.get("setting"),
        "nurse_card": row.get("nurse_card"), "interlocutor_card": row.get("interlocutor_card"),
        "scoring_criteria": row.get("scoring_criteria"), "difficulty": row.get("difficulty"),
        "specialty": row.get("specialty"), "voice_config": row.get("voice_config"),
        "patient_gender": row.get("patient_gender"), "patient_age": row.get("patient_age"),
    }


def build_mock_snapshot(supabase, mock_test_id: int) -> Dict[str, Any]:
    """Resolves the pack's picks: Reading/Listening by reference to their OWN
    latest immutable version (never by copying their content in), Writing/
    Speaking as embedded snapshots (no version table for them in RC4.1).
    Requires the pack's Reading and Listening tests to already have at least
    one published version -- publish those first (or run the RC4.1 backfill)
    if this 409s."""
    pack = supabase.table("mock_tests").select("*").eq("id", mock_test_id).execute()
    if not pack.data:
        raise HTTPException(status_code=404, detail="Mock Test pack not found")
    p = pack.data[0]

    reading_version_id = latest_version_id(supabase, "reading_test_versions", "reading_test_id", p.get("reading_test_id"))
    listening_version_id = latest_version_id(supabase, "listening_test_versions", "listening_test_id", p.get("listening_test_id"))
    if reading_version_id is None or listening_version_id is None:
        raise HTTPException(
            status_code=409,
            detail="This pack's Reading and/or Listening test has no published version yet -- "
            "publish (Make Live) each one first, then publish the Mock Test version.",
        )

    writing = supabase.table("scenarios").select(_WRITING_SCENARIO_FIELDS).eq("id", p.get("writing_scenario_id")).execute().data
    speaking_1 = supabase.table("scenarios").select(_SPEAKING_SCENARIO_FIELDS).eq("id", p.get("speaking_scenario_id_1")).execute().data
    speaking_2 = supabase.table("scenarios").select(_SPEAKING_SCENARIO_FIELDS).eq("id", p.get("speaking_scenario_id_2")).execute().data
    if not writing or not speaking_1 or not speaking_2:
        raise HTTPException(status_code=409, detail="This pack's Writing/Speaking content is missing or was deleted.")

    return {
        "mock_test_id": mock_test_id,
        "label": p.get("label"),
        "reading_test_version_id": reading_version_id,
        "listening_test_version_id": listening_version_id,
        "writing_scenario_snapshot": _writing_scenario_snapshot(writing[0]),
        "speaking_scenario_snapshot_1": _speaking_scenario_snapshot(speaking_1[0]),
        "speaking_scenario_snapshot_2": _speaking_scenario_snapshot(speaking_2[0]),
    }


def publish_mock_version(supabase, mock_test_id: int, published_by: Optional[str]) -> Dict[str, Any]:
    snapshot = build_mock_snapshot(supabase, mock_test_id)
    return _allocate_version(supabase, "mock_test_versions", "mock_test_id", mock_test_id, snapshot, published_by)


# ── VERSION 1 BACKFILL ────────────────────────────────────────────────
# Gives currently-live production assessments an immutable baseline instead
# of leaving them on the legacy path indefinitely. Version 1 = whatever is
# live AT ROLLOUT TIME -- it is not, and cannot be, a reconstruction of any
# earlier historical state. Idempotent: a test/pack that already has a
# version (1 or later) is left alone, so this is safe to run once, safe to
# retry, and can never mint a second Version 1. Reading/Listening run before
# Mock so a mock pack whose picks are still on the legacy path can also get
# its Version 1 in the same call.

def backfill_versions(supabase, published_by: Optional[str]) -> Dict[str, Any]:
    created = {"reading_tests": [], "listening_tests": [], "mock_tests": []}
    skipped = {"reading_tests": [], "listening_tests": [], "mock_tests": []}
    failed = {"reading_tests": [], "listening_tests": [], "mock_tests": []}

    reading_tests = supabase.table("reading_tests").select("id").eq("is_active", True).execute().data
    for t in reading_tests:
        tid = t["id"]
        if latest_version_id(supabase, "reading_test_versions", "reading_test_id", tid) is not None:
            skipped["reading_tests"].append(tid)
            continue
        try:
            publish_reading_version(supabase, tid, published_by)
            created["reading_tests"].append(tid)
        except Exception as e:
            logger.warning("[rc41 backfill] reading_test %s failed: %s", tid, str(e)[:300])
            failed["reading_tests"].append(tid)

    listening_tests = supabase.table("listening_tests").select("id").eq("is_active", True).execute().data
    for t in listening_tests:
        tid = t["id"]
        if latest_version_id(supabase, "listening_test_versions", "listening_test_id", tid) is not None:
            skipped["listening_tests"].append(tid)
            continue
        try:
            publish_listening_version(supabase, tid, published_by)
            created["listening_tests"].append(tid)
        except Exception as e:
            logger.warning("[rc41 backfill] listening_test %s failed: %s", tid, str(e)[:300])
            failed["listening_tests"].append(tid)

    mock_tests = supabase.table("mock_tests").select("id").execute().data
    for m in mock_tests:
        mid = m["id"]
        if latest_version_id(supabase, "mock_test_versions", "mock_test_id", mid) is not None:
            skipped["mock_tests"].append(mid)
            continue
        try:
            publish_mock_version(supabase, mid, published_by)
            created["mock_tests"].append(mid)
        except Exception as e:
            logger.warning("[rc41 backfill] mock_test %s failed: %s", mid, str(e)[:300])
            failed["mock_tests"].append(mid)

    return {"created": created, "skipped": skipped, "failed": failed}
