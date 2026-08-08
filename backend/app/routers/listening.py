"""OET Listening module.

Mirrors reading.py 1:1, over audio instead of text. A "test" = one full OET
Listening paper (Part A -> B -> C) taken as one session; a "section" = one
extract within it (Reading's passage analog). Questions reuse the shared
`questions` table (module='listening', section_id FK, options JSON,
correct_answer = exact option text). Grading is the same shared path Reading
uses: grade_exact_match for Part B/C MCQ, grade_open_ended_answers for Part A
gap-fill notes (type='short_answer').

Audio lives in the public `listening-audio` bucket; the section stores its
public URL. The heavy IP (correct answers, transcript) is withheld from the
student payload until submit, so a public audio URL leaks nothing that matters.
The transcript is revealed only after submitting (so it can't be read mid-test).

Content pipeline (admin): create a test, add sections, attach audio (upload an
mp3 now; TTS generation lands in step 3), add questions, publish. Same
review-then-save + draft-then-publish gates as reading.py.
"""
import base64
import json
import logging
import os
import tempfile
import uuid
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from app.core.config import settings
from app.core.supabase import get_supabase
from app.core.threading import run_sync
from app.core.rate_limit import SlidingWindowRateLimiter
from app.routers.auth import get_current_user, get_user_supabase, UserInfo
from supabase import Client
from app.routers.admin import require_admin
from app.routers.mock import has_mock_section_access
from app.services.mcq_grading import grade_exact_match, combine_graded_results, resolve_latest_wrong_answers
from app.services.open_ended_grading import grade_open_ended_answers
from app.services.explanations import generate_mcq_explanation
from app.services.skill_graph import record_skill_observations, get_weakness
from app.services.coaching_messages import RECOMMENDATION_REASON, ACTIONABLE_IMPROVEMENT, CONFIDENCE_MESSAGE
from app.services.listening_audio import (
    generate_two_speaker_audio, cut_segment, deepgram_transcribe, timestamped_lines,
    TtsError, OPENAI_VOICES,
)
from app.services.ai_scoring import _call_ai
from app.services.plan_gating import has_listening_access, has_free_module_attempt, get_plan_from_profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/listening", tags=["listening"])

_submit_rate_limiter = SlidingWindowRateLimiter(30, 600, name="listening:submit")
_upload_rate_limiter = SlidingWindowRateLimiter(20, 600, name="listening:upload")
_tts_rate_limiter = SlidingWindowRateLimiter(10, 600, name="listening:tts")
_extract_rate_limiter = SlidingWindowRateLimiter(30, 600, name="listening:extract")
_explanation_rate_limiter = SlidingWindowRateLimiter(30, 600, name="listening:explanation")

AUDIO_BUCKET = "listening-audio"
MAX_AUDIO_BYTES = 25 * 1024 * 1024
# A full-test recording (all parts, ~40 min) is far bigger than one extract; it's
# only held in a backend temp file to be cut, never stored whole in the bucket.
MAX_FULL_AUDIO_BYTES = 100 * 1024 * 1024
MAX_PDF_BYTES = 10 * 1024 * 1024
AUDIO_CONTENT_TYPES = {
    "audio/mpeg": "mp3", "audio/mp3": "mp3",
    "audio/wav": "wav", "audio/x-wav": "wav",
    "audio/mp4": "m4a", "audio/x-m4a": "m4a",
}

_PART_ORDER = {"A": 0, "B": 1, "C": 2}


def _question_out(q: dict, *, include_answer: bool) -> dict:
    """One question shaped for a client payload. Student payloads withhold
    correct_answer (include_answer=False); admin/editor payloads include it."""
    out = {
        "id": q["id"],
        "content": q["content"],
        "type": "short_answer" if q.get("type") == "short_answer" else "mcq",
        "options": json.loads(q["options"]) if q.get("options") else [],
    }
    if include_answer:
        out["correct_answer"] = q.get("correct_answer")
    return out


# ── STUDENT: full-paper test session ─────────────────────────────────

def _require_listening_plan(supabase, current_user: UserInfo, test_id: Optional[int] = None) -> str:
    """Plan-gate listening access (Basic/Pro/Elite) -- shared by test view and
    submit. The list endpoint (titles only, no content) stays open as a teaser.

    Free plan gets one lifetime standalone attempt (see has_free_module_attempt)
    on top of that -- a taste of the module before the paywall.

    An anonymous or free-plan free-trial user (see /tools/oet-mock-test-free)
    is also let through when `test_id` is the exact Listening test their own
    active mock is currently on -- see has_mock_section_access in mock.py.
    Separate from the standalone free attempt above, so spending one never
    eats the other."""
    profile = supabase.table("user_profiles").select("plan, plan_expires_at").eq("user_id", current_user.id).execute()
    plan = get_plan_from_profile(profile.data[0] if profile.data else {})
    if has_listening_access(plan):
        return plan
    if plan == "free" and has_free_module_attempt(supabase, current_user.id, "listening"):
        return plan
    if (current_user.is_anonymous or plan == "free") and test_id is not None and has_mock_section_access(supabase, current_user.id, "listening", test_id):
        return plan
    raise HTTPException(
        status_code=403,
        detail={
            "error": "Listening practice requires a paid plan",
            "upgrade_required": True,
            "current_plan": plan,
        },
    )


def _load_test_payload(test_id: int, include_inactive: bool) -> Dict[str, Any]:
    """Full test for the session player: sections ordered Part A -> B -> C, each
    with its audio_url + questions, correct_answer AND transcript withheld.
    include_inactive=True is the admin preview path (ignores is_active on both the
    test and its sections); the student path keeps both filters on."""
    supabase = get_supabase()
    tq = supabase.table("listening_tests").select("id, title, part_audio").eq("id", test_id)
    if not include_inactive:
        tq = tq.eq("is_active", True)
    t = tq.execute()
    if not t.data:
        raise HTTPException(status_code=404, detail="Test not found")

    sq = supabase.table("listening_sections").select(
        "id, title, part, audio_url, body"
    ).eq("test_id", test_id)
    if not include_inactive:
        sq = sq.eq("is_active", True)
    sections = sq.execute().data
    sections.sort(key=lambda s: (_PART_ORDER.get(s["part"], 9), s["id"]))

    sids = [s["id"] for s in sections]
    qrows = supabase.table("questions").select(
        "id, content, options, type, section_id"
    ).in_("section_id", sids).execute().data if sids else []
    q_by_section: Dict[int, list] = {}
    for q in qrows:
        q_by_section.setdefault(q["section_id"], []).append(q)

    out_sections = [{
        "id": s["id"],
        "title": s["title"],
        "part": s["part"],
        "audio_url": s["audio_url"],
        "body": s.get("body"),  # Part A notes template; null for B/C
        "questions": [
            _question_out(q, include_answer=False)
            for q in sorted(q_by_section.get(s["id"], []), key=lambda x: x["id"])
        ],
    } for s in sections]
    return {
        "id": t.data[0]["id"],
        "title": t.data[0]["title"],
        "part_audio": t.data[0].get("part_audio") or {},
        "sections": out_sections,
    }


@router.get("/tests")
def list_tests(current_user: UserInfo = Depends(get_current_user)):
    """Active tests that have at least one active section -- the student's
    'full mock listening test' list."""
    supabase = get_supabase()
    tests = supabase.table("listening_tests").select("id, title").eq("is_active", True).order("id", desc=False).execute().data
    if not tests:
        return []
    test_ids = [t["id"] for t in tests]
    sections = supabase.table("listening_sections").select("test_id").in_("test_id", test_ids).eq("is_active", True).execute().data
    counts: Dict[int, int] = {}
    for s in sections:
        counts[s["test_id"]] = counts.get(s["test_id"], 0) + 1
    return [{"id": t["id"], "title": t["title"], "section_count": counts.get(t["id"], 0)} for t in tests if counts.get(t["id"], 0) > 0]


@router.get("/tests/completed-ids")
async def list_completed_test_ids(
    current_user: UserInfo = Depends(get_current_user),
    user_db: Client = Depends(get_user_supabase),
):
    """Distinct test_ids the student has already submitted, for the "Completed"
    badge on the test list. test_id lives in submissions.feedback (see
    submit_listening_test), not a column -- mirrors reading.py's endpoint."""
    subs = await run_sync(
        user_db.table("submissions").select("feedback")
        .eq("user_id", current_user.id).eq("module", "listening").execute
    )
    test_ids = set()
    for s in subs.data:
        try:
            fb = json.loads(s["feedback"]) if isinstance(s["feedback"], str) else (s["feedback"] or {})
        except (json.JSONDecodeError, TypeError):
            continue
        if fb.get("test_id") is not None:
            test_ids.add(fb["test_id"])
    return sorted(test_ids)


@router.get("/tests/recommend")
def recommend_test(
    current_user: UserInfo = Depends(get_current_user),
    user_db: Client = Depends(get_user_supabase),
):
    """Recommend a single test -- used by the dashboard's Next Best Action
    card. Must stay registered before /tests/{test_id} below, or that route
    swallows "recommend" as a test_id path param first."""
    return _recommend_listening_tests(current_user, user_db, limit=1)[0]


@router.get("/tests/{test_id}")
def get_test(test_id: int, current_user: UserInfo = Depends(get_current_user)):
    """Full test for the session player. correct_answer + transcript are NOT sent
    (can't be read before submitting). Only active tests/sections are visible."""
    _require_listening_plan(get_supabase(), current_user, test_id)
    return _load_test_payload(test_id, include_inactive=False)


def _recommend_listening_tests(current_user: UserInfo, user_db: Client, limit: int) -> list:
    """Shared ranking, same shape as reading._recommend_reading_tests: unattempted
    tests first (shuffled), then the user's lowest-scored attempted tests, weakest
    first. Reuses list_tests for the candidate pool rather than re-querying it."""
    import random

    all_tests = list_tests(current_user)
    if not all_tests:
        raise HTTPException(status_code=404, detail="No listening tests available")

    subs = user_db.table("submissions").select("feedback, score").eq(
        "user_id", current_user.id
    ).eq("module", "listening").execute()
    attempted_scores: Dict[int, list] = {}
    for s in subs.data:
        try:
            fb = json.loads(s["feedback"]) if isinstance(s["feedback"], str) else (s["feedback"] or {})
        except (json.JSONDecodeError, TypeError):
            continue
        test_id = fb.get("test_id")
        if test_id is not None:
            attempted_scores.setdefault(test_id, []).append(s.get("score", 0))

    tests_by_id = {t["id"]: t for t in all_tests}
    unattempted = [t for t in all_tests if t["id"] not in attempted_scores]
    random.shuffle(unattempted)
    weakest_first = sorted(attempted_scores.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))

    recs = []
    seen_ids = set()

    for t in unattempted:
        if len(recs) >= limit:
            break
        recs.append({"test_id": t["id"], "title": t["title"], "reason": "New - you haven't tried this test yet"})
        seen_ids.add(t["id"])

    for tid, scores in weakest_first:
        if len(recs) >= limit:
            break
        if tid in seen_ids:
            continue
        pick = tests_by_id.get(tid)
        if not pick:
            continue
        avg = sum(scores) / len(scores)
        recs.append({
            "test_id": pick["id"],
            "title": pick["title"],
            "reason": f"Needs practice - your average score for this test is {avg:.1f}/6",
        })
        seen_ids.add(tid)

    if not recs:
        for t in random.sample(all_tests, min(limit, len(all_tests))):
            recs.append({"test_id": t["id"], "title": t["title"], "reason": "Try this test"})

    return recs


async def _build_listening_insights(
    per_part: Dict[str, float],
    current_user: UserInfo,
    user_db: Client,
) -> Optional[dict]:
    """Rule-based V1 recommendation, same shape/pattern as
    reading._build_reading_insights (Sprint 2) and speaking._build_speaking_insights
    (Sprint 1, ADR-008), ported locally rather than shared.

    Listening has no listening:skill:* sub-tags (only part-level A/B/C), so
    insights key off part rather than a finer skill tag -- reusing what the
    skill graph already records (listening.py submit_test) instead of inventing
    a new tag namespace for this sprint.

    # TODO: LISTENING_PART_LABELS is just "Part A/B/C" -- swap in friendlier
    # learner-facing labels (e.g. what each part actually tests) once that
    # copy exists; out of scope for this sprint.

    Best-effort like record_skill_observations: the submission is already
    saved by the time this runs, so a weakness-history or recommendation
    query blipping must not turn an already-successful score into a 500."""
    if not per_part:
        return None
    try:
        strongest_tag, strongest_score = max(per_part.items(), key=lambda kv: kv[1])
        strongest_label = LISTENING_PART_LABELS.get(strongest_tag, strongest_tag)

        history = await get_weakness(user_db, current_user.id, "listening:", lambda s: LISTENING_PART_LABELS.get(s, s))
        if history:
            weakest = history[0]
            weakest_tag = weakest["skill"]
            weakest_label = weakest["label"]
            weakest_score = weakest["band"]
            basis = "history"
            template_args = {"label": weakest_label, "attempts": weakest["attempts"]}
        else:
            weakest_tag, weakest_score = min(per_part.items(), key=lambda kv: kv[1])
            weakest_label = LISTENING_PART_LABELS.get(weakest_tag, weakest_tag)
            basis = "session"
            template_args = {"label": weakest_label, "attempts": 1}

        next_best_action = None
        try:
            recs = _recommend_listening_tests(current_user, user_db, 1)
            if recs:
                next_best_action = recs[0]
        except HTTPException:
            pass  # no tests available -- insights still useful without a pick

        return {
            "strongest_skill": {"tag": strongest_tag, "label": strongest_label, "score": strongest_score},
            "weakest_skill": {"tag": weakest_tag, "label": weakest_label, "score": weakest_score},
            "recommendation_reason": RECOMMENDATION_REASON[basis].format(**template_args),
            "actionable_improvement": ACTIONABLE_IMPROVEMENT[basis].format(**template_args),
            "confidence_message": CONFIDENCE_MESSAGE[basis].format(**template_args),
            "next_best_action": next_best_action,
            "based_on": basis,
        }
    except Exception as e:
        logger.warning("[LISTENING_INSIGHTS_FAILED] user_id=%s error=%s", current_user.id, str(e)[:300])
        return None


class ListeningAnswer(BaseModel):
    questionId: int
    selectedOption: Optional[str] = None


class ListeningTestSubmitRequest(BaseModel):
    answers: List[ListeningAnswer]
    elapsed_seconds: Optional[int] = None


@router.post("/tests/{test_id}/submit")
async def submit_test(
    test_id: int,
    request: ListeningTestSubmitRequest,
    current_user: UserInfo = Depends(get_current_user),
    user_db: Client = Depends(get_user_supabase),
):
    """Grade a whole test session at once (all Part A/B/C questions), record one
    'listening' submission, report per-part bands so weak parts feed the skill
    graph, and reveal each section's transcript (withheld until now)."""
    if _submit_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many submissions — please slow down.")

    supabase = get_supabase()
    _require_listening_plan(supabase, current_user, test_id)
    t = await run_sync(
        supabase.table("listening_tests").select("id").eq("id", test_id).eq("is_active", True).execute
    )
    if not t.data:
        raise HTTPException(status_code=404, detail="Test not found")

    sections = await run_sync(
        supabase.table("listening_sections").select("id, part, transcript").eq("test_id", test_id).eq("is_active", True).execute
    )
    part_by_section = {s["id"]: s["part"] for s in sections.data}
    sids = list(part_by_section.keys())
    if not sids:
        raise HTTPException(status_code=404, detail="Test has no sections")

    qrows = await run_sync(
        supabase.table("questions").select("id, content, correct_answer, type, section_id").in_("section_id", sids).execute
    )
    questions_by_id = {q["id"]: q for q in qrows.data}
    part_by_qid = {q["id"]: part_by_section.get(q["section_id"]) for q in qrows.data}

    # only grade answers to questions that actually belong to this test
    answers = [a for a in request.answers if a.questionId in questions_by_id]
    mcq_by_id = {qid: q for qid, q in questions_by_id.items() if q.get("type") != "short_answer"}
    short_by_id = {qid: q for qid, q in questions_by_id.items() if q.get("type") == "short_answer"}
    answers_by_id = {a.questionId: a.selectedOption for a in answers}

    mcq_graded = grade_exact_match(mcq_by_id, [a.model_dump() for a in answers])

    short_items = [
        {"questionId": qid, "content": short_by_id[qid]["content"], "expected": short_by_id[qid]["correct_answer"], "answer": answers_by_id.get(qid) or ""}
        for qid in short_by_id
        if qid in answers_by_id and short_by_id[qid].get("correct_answer") is not None
    ]
    short_results_map = await grade_open_ended_answers(short_items, subject="Listening", user_id=current_user.id)
    if short_items and short_results_map is None:
        raise HTTPException(status_code=503, detail="Scoring is temporarily unavailable. Please try again in a few minutes.")

    short_results = [{
        "questionId": it["questionId"],
        "selected": it["answer"],
        "correct_answer": short_by_id[it["questionId"]]["correct_answer"],
        "is_correct": (short_results_map or {}).get(it["questionId"], {}).get("is_correct", False),
        "feedback": (short_results_map or {}).get(it["questionId"], {}).get("feedback", ""),
    } for it in short_items]

    combined = combine_graded_results(mcq_graded, short_results)

    # Per-part bands, so a weak Part A vs. strong Part C is visible + feeds skills.
    per_part_counts: Dict[str, Dict[str, int]] = {}
    for r in combined["results"]:
        part = part_by_qid.get(r["questionId"]) or "?"
        bucket = per_part_counts.setdefault(part, {"correct": 0, "graded": 0})
        bucket["graded"] += 1
        if r["is_correct"]:
            bucket["correct"] += 1
    per_part = {
        part: round((c["correct"] / c["graded"]) * 6, 2) if c["graded"] else 0.0
        for part, c in per_part_counts.items()
    }
    if per_part:
        await record_skill_observations(
            current_user.id, {f"listening:{part}": band for part, band in per_part.items()}
        )

    await run_sync(
        user_db.table("submissions").insert({
            "user_id": current_user.id,
            # NOT scenario_id: listening_tests is a different id space than the
            # scenarios table scenario_id is FK'd to (writing test_id there
            # violated that FK and 500'd every full-test submission). test_id
            # lives in feedback instead.
            "module": "listening",
            "answer": f"{combined['correct']}/{combined['graded']} correct",
            "score": combined["band"],
            "feedback": json.dumps({
                "test_id": test_id,
                "correct": combined["correct"],
                "graded": combined["graded"],
                "results": combined["results"],
                "per_part": per_part,
                "elapsed_seconds": request.elapsed_seconds,
            }),
        }).execute
    )

    insights = await _build_listening_insights(per_part, current_user, user_db)

    return {
        "score": combined["band"],
        "correct": combined["correct"],
        "total": combined["graded"],
        "results": combined["results"],
        "per_part": per_part,
        "transcripts": {s["id"]: s.get("transcript") for s in sections.data},
        "insights": insights,
    }


# ── EXPLANATIONS (cached, generated once per question) ───────────────

@router.get("/questions/{question_id}/explanation")
async def get_explanation(
    question_id: int,
    current_user: UserInfo = Depends(get_current_user),
):
    """Cache-through explanation for one question. First caller pays one AI call;
    everyone after gets it free off the question row. No passage-evidence highlight
    like Reading has -- audio has no on-screen text to point at."""
    if _explanation_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many requests — please slow down.")

    supabase = get_supabase()
    q = await run_sync(
        supabase.table("questions").select("id, content, options, correct_answer, explanation")
        .eq("id", question_id).execute
    )
    if not q.data:
        raise HTTPException(status_code=404, detail="Question not found")
    question = q.data[0]

    if question.get("explanation"):
        return {"explanation": question["explanation"]}

    explanation = await generate_mcq_explanation(question, subject="Listening", context_noun="audio extract")
    if not explanation:
        raise HTTPException(status_code=503, detail="Explanation is temporarily unavailable. Please try again.")

    await run_sync(
        supabase.table("questions").update({"explanation": explanation}).eq("id", question_id).execute
    )
    return {"explanation": explanation}


# ── WRONG-ANSWER NOTEBOOK ─────────────────────────────────────────────

MISTAKES_LOOKBACK_SUBMISSIONS = 100


@router.get("/mistakes")
async def list_mistakes(
    current_user: UserInfo = Depends(get_current_user),
    user_db: Client = Depends(get_user_supabase),
):
    """Every question the user has ever gotten wrong in listening practice, most
    recent attempt per question, newest first. Built entirely from data already on
    submissions.feedback -- mirrors reading.py's /mistakes."""
    supabase = get_supabase()
    subs = await run_sync(
        user_db.table("submissions").select("feedback, created_at")
        .eq("user_id", current_user.id).eq("module", "listening")
        .order("created_at", desc=True).limit(MISTAKES_LOOKBACK_SUBMISSIONS).execute
    )

    feedback_blobs = []
    for s in subs.data:
        try:
            fb = json.loads(s["feedback"]) if isinstance(s["feedback"], str) else (s["feedback"] or {})
        except (json.JSONDecodeError, TypeError):
            continue
        feedback_blobs.append(fb)

    wrong_by_qid = resolve_latest_wrong_answers(feedback_blobs)
    if not wrong_by_qid:
        return []

    qids = list(wrong_by_qid.keys())
    qdata = await run_sync(
        supabase.table("questions").select("id, content, options, correct_answer, section_id, explanation")
        .in_("id", qids).execute
    )
    section_ids = [q["section_id"] for q in qdata.data if q.get("section_id")]
    sections_by_id: Dict[int, str] = {}
    if section_ids:
        s = await run_sync(
            supabase.table("listening_sections").select("id, title").in_("id", section_ids).execute
        )
        sections_by_id = {row["id"]: row["title"] for row in s.data}

    return [{
        "questionId": q["id"],
        "content": q["content"],
        "options": json.loads(q["options"]) if q.get("options") else [],
        "correct_answer": q["correct_answer"],
        "your_answer": wrong_by_qid[q["id"]].get("selected"),
        "section_title": sections_by_id.get(q.get("section_id")),
        "explanation": q.get("explanation"),
    } for q in qdata.data]


LISTENING_PART_LABELS = {"A": "Part A", "B": "Part B", "C": "Part C"}


@router.get("/weakness")
async def listening_weakness(
    current_user: UserInfo = Depends(get_current_user),
    user_db: Client = Depends(get_user_supabase),
):
    """The student's weakest listening parts. Unlike other modules' weak-spot
    lists, parts have a fixed exam sequence (A -> B -> C) so -- unlike
    skill_graph.get_weakness's default weakest-first order -- these sort back
    into that sequence rather than by band."""
    rows = await get_weakness(user_db, current_user.id, "listening:", lambda s: LISTENING_PART_LABELS.get(s, s))
    return sorted(rows, key=lambda r: r["skill"])


# ── ADMIN: questions validation (shared by save + update) ────────────

class ListeningQuestionIn(BaseModel):
    content: str
    type: str = "mcq"  # "mcq" (exact-match) or "short_answer" (AI-graded, Part A gap-fill)
    options: List[str] = []
    correct_answer: str = ""  # blank allowed -- content can be saved before its answer is known


class ListeningQuestionUpdateIn(ListeningQuestionIn):
    id: Optional[int] = None  # existing question id to update in place; omitted = new question


def _validate_questions(questions: List["ListeningQuestionIn"]) -> None:
    """MCQ needs >=2 options and, if an answer is given, it must exactly match one.
    A blank correct_answer is allowed on either type -- filled in later."""
    if not questions:
        raise HTTPException(status_code=400, detail="At least one question is required")
    for q in questions:
        if q.type == "short_answer":
            continue
        if len(q.options) < 2:
            raise HTTPException(status_code=400, detail=f"Question needs at least 2 options: {q.content[:50]}")
        if q.correct_answer and q.correct_answer not in q.options:
            raise HTTPException(status_code=400, detail=f"Correct answer must exactly match one option: {q.content[:50]}")


def _insert_question(supabase, q: "ListeningQuestionIn", section_id: int) -> None:
    supabase.table("questions").insert({
        "module": "listening",
        "type": q.type,
        "content": q.content,
        "options": json.dumps(q.options) if q.options else None,
        "correct_answer": q.correct_answer or None,
        "section_id": section_id,
    }).execute()


# ── ADMIN: sections (a section = one extract with its own audio) ─────

class ListeningSectionSaveRequest(BaseModel):
    title: str
    part: str = "B"
    difficulty: str = "intermediate"
    audio_url: Optional[str] = None  # set here if already uploaded, else via /audio later
    transcript: Optional[Any] = None  # jsonb: speaker turns [{speaker, text}] or plain text
    body: Optional[str] = None  # Part A notes template (headings + context bullets + numbered blanks)
    questions: List[ListeningQuestionIn]
    test_id: Optional[int] = None  # optionally group this section into a full test/paper


@router.post("/admin/save")
def save_section(req: ListeningSectionSaveRequest, _admin=Depends(require_admin)):
    """Save a reviewed section + its questions. Audio can be attached now (audio_url)
    or later via /admin/sections/{id}/audio."""
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")
    if req.part not in ("A", "B", "C"):
        raise HTTPException(status_code=400, detail="Part must be A, B, or C")
    _validate_questions(req.questions)

    supabase = get_supabase()
    section = supabase.table("listening_sections").insert({
        "title": req.title,
        "part": req.part,
        "difficulty": req.difficulty,
        "audio_url": req.audio_url,
        "transcript": req.transcript,
        "body": req.body,
        "is_active": True,
        "test_id": req.test_id,
    }).execute().data[0]

    for q in req.questions:
        _insert_question(supabase, q, section["id"])

    return {"success": True, "section_id": section["id"], "questions_saved": len(req.questions)}


class ListeningSectionUpdateRequest(BaseModel):
    title: str
    part: str = "B"
    difficulty: str = "intermediate"
    transcript: Optional[Any] = None
    body: Optional[str] = None
    questions: List[ListeningQuestionUpdateIn]
    # audio + test assignment have their own endpoints -- never edited here, so a
    # content save can't silently wipe them (frontend never sends them).


@router.put("/admin/sections/{section_id}")
def update_section(section_id: int, req: ListeningSectionUpdateRequest, _admin=Depends(require_admin)):
    """Edit an already-saved section. Existing questions (with an id) are updated in
    place -- never deleted -- so past submissions/mistakes entries keep resolving.
    New questions (no id) get inserted."""
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")
    if req.part not in ("A", "B", "C"):
        raise HTTPException(status_code=400, detail="Part must be A, B, or C")
    _validate_questions(req.questions)

    supabase = get_supabase()
    existing = supabase.table("listening_sections").select("id").eq("id", section_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Section not found")

    supabase.table("listening_sections").update({
        "title": req.title,
        "part": req.part,
        "difficulty": req.difficulty,
        "transcript": req.transcript,
        "body": req.body,
    }).eq("id", section_id).execute()

    updated = 0
    inserted = 0
    for q in req.questions:
        payload = {
            "type": q.type,
            "content": q.content,
            "options": json.dumps(q.options) if q.options else None,
            "correct_answer": q.correct_answer or None,
        }
        if q.id is not None:
            # section_id guard: a mismatched id can't edit a question in another section.
            supabase.table("questions").update(payload).eq("id", q.id).eq("section_id", section_id).execute()
            updated += 1
        else:
            _insert_question(supabase, q, section_id)
            inserted += 1

    return {"success": True, "updated": updated, "inserted": inserted}


@router.get("/admin/sections")
def admin_list_sections(_admin=Depends(require_admin)):
    """All sections (active or not) for the admin management list, with the title of
    the test each belongs to (null if ungrouped)."""
    supabase = get_supabase()
    data = supabase.table("listening_sections").select(
        "id, title, part, difficulty, is_active, created_at, test_id, audio_url"
    ).order("created_at", desc=True).execute()
    tests = supabase.table("listening_tests").select("id, title").execute()
    test_title = {t["id"]: t["title"] for t in tests.data}
    return [{**s, "has_audio": bool(s.get("audio_url")), "test_title": test_title.get(s.get("test_id"))} for s in data.data]


@router.get("/admin/sections/{section_id}")
def admin_get_section(section_id: int, _admin=Depends(require_admin)):
    """Full section detail for the admin editor -- includes correct_answer, each
    question's DB id, transcript, and audio_url."""
    supabase = get_supabase()
    s = supabase.table("listening_sections").select(
        "id, title, part, difficulty, audio_url, transcript, body, test_id"
    ).eq("id", section_id).execute()
    if not s.data:
        raise HTTPException(status_code=404, detail="Section not found")
    qs = supabase.table("questions").select(
        "id, content, type, options, correct_answer"
    ).eq("section_id", section_id).order("id").execute()
    return {**s.data[0], "questions": [_question_out(q, include_answer=True) for q in qs.data]}


class SetActiveRequest(BaseModel):
    is_active: bool


@router.post("/admin/sections/{section_id}/active")
def set_section_active(section_id: int, req: SetActiveRequest, _admin=Depends(require_admin)):
    """Publish/unpublish a single section (hides it from students and any test it
    belongs to) without deleting it."""
    supabase = get_supabase()
    existing = supabase.table("listening_sections").select("id").eq("id", section_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Section not found")
    supabase.table("listening_sections").update({"is_active": req.is_active}).eq("id", section_id).execute()
    return {"success": True, "is_active": req.is_active}


@router.delete("/admin/sections/{section_id}")
def delete_section(section_id: int, _admin=Depends(require_admin)):
    """Permanently delete a section and its questions. Prefer /active (hide) if unsure."""
    supabase = get_supabase()
    existing = supabase.table("listening_sections").select("id").eq("id", section_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Section not found")
    supabase.table("questions").delete().eq("section_id", section_id).execute()
    supabase.table("listening_sections").delete().eq("id", section_id).execute()
    return {"success": True}


class AssignSectionRequest(BaseModel):
    test_id: Optional[int] = None  # null detaches the section from any test


@router.post("/admin/sections/{section_id}/assign")
def assign_section_to_test(section_id: int, req: AssignSectionRequest, _admin=Depends(require_admin)):
    """Attach an existing section to a test (or detach with test_id=null)."""
    supabase = get_supabase()
    existing = supabase.table("listening_sections").select("id").eq("id", section_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Section not found")
    if req.test_id is not None:
        t = supabase.table("listening_tests").select("id").eq("id", req.test_id).execute()
        if not t.data:
            raise HTTPException(status_code=404, detail="Test not found")
    supabase.table("listening_sections").update({"test_id": req.test_id}).eq("id", section_id).execute()
    return {"success": True}


async def _upload_to_bucket(path: str, contents: bytes, content_type: str) -> str:
    """Upload bytes to the audio bucket at `path`, return the public URL."""
    supabase = get_supabase()
    await run_sync(
        supabase.storage.from_(AUDIO_BUCKET).upload,
        path, contents, {"content-type": content_type},
    )
    public = supabase.storage.from_(AUDIO_BUCKET).get_public_url(path)
    # supabase-py has returned either a plain string or a dict across versions.
    url = public if isinstance(public, str) else (public.get("publicUrl") or public.get("publicURL") or "")
    if not url:
        raise HTTPException(status_code=502, detail="Upload succeeded but no public URL was returned")
    return url


async def _store_and_set_audio(
    section_id: int, contents: bytes, ext: str, content_type: str,
    transcript: Optional[Any] = None,
    start: Optional[float] = None, end: Optional[float] = None,
) -> str:
    """Upload audio bytes into the section's folder, set audio_url (and optionally the
    transcript + cut range) on the section, and return the public URL. Shared by upload,
    generate, and split. start/end are stored for display when the clip came from a cut."""
    url = await _upload_to_bucket(f"sections/{section_id}/{uuid.uuid4().hex}.{ext}", contents, content_type)
    update: Dict[str, Any] = {"audio_url": url}
    if transcript is not None:
        update["transcript"] = transcript
    if start is not None and end is not None:
        update["audio_start"] = start
        update["audio_end"] = end
    get_supabase().table("listening_sections").update(update).eq("id", section_id).execute()
    return url


@router.post("/admin/sections/{section_id}/audio")
async def upload_section_audio(
    section_id: int,
    audio: UploadFile = File(...),
    _admin=Depends(require_admin),
):
    """Upload one mp3/wav/m4a for a section and set it as the section's audio_url.
    Public bucket, so the returned URL plays directly in an <audio> tag. Replacing
    audio just overwrites audio_url (the old object is orphaned, harmless)."""
    if _upload_rate_limiter.is_rate_limited("admin"):
        raise HTTPException(status_code=429, detail="Too many uploads — please slow down.")
    ext = AUDIO_CONTENT_TYPES.get(audio.content_type)
    if not ext:
        raise HTTPException(status_code=400, detail="Use an mp3, wav, or m4a file")
    contents = await audio.read()
    if len(contents) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Audio must be under 25MB")

    supabase = get_supabase()
    existing = supabase.table("listening_sections").select("id").eq("id", section_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Section not found")

    url = await _store_and_set_audio(section_id, contents, ext, audio.content_type)
    return {"url": url}


class TtsTurnIn(BaseModel):
    speaker: str
    text: str


class GenerateAudioRequest(BaseModel):
    turns: List[TtsTurnIn]
    voices: Optional[Dict[str, str]] = None  # speaker label -> OpenAI voice; auto-assigned if omitted
    model: Optional[str] = None  # None resolves to the "tts_openai" purpose (Admin > AI Models)


@router.get("/admin/tts-voices")
def list_tts_voices(_admin=Depends(require_admin)):
    """The OpenAI voices the admin can assign to speakers when generating audio."""
    return {"voices": OPENAI_VOICES}


@router.post("/admin/sections/{section_id}/generate-audio")
async def generate_section_audio(
    section_id: int,
    req: GenerateAudioRequest,
    _admin=Depends(require_admin),
):
    """Generate a section's audio from a 2-speaker transcript via OpenAI TTS, stitch
    the turns into one mp3, store it as the section's audio_url, and save the turns as
    the section transcript (the regeneration source + the post-test reveal)."""
    if _tts_rate_limiter.is_rate_limited("admin"):
        raise HTTPException(status_code=429, detail="Too many generations — please slow down.")
    if not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=502, detail="AI provider not configured")

    supabase = get_supabase()
    existing = supabase.table("listening_sections").select("id").eq("id", section_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Section not found")

    turns = [t.model_dump() for t in req.turns]
    try:
        audio_bytes = await generate_two_speaker_audio(turns, req.voices, req.model)
    except TtsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("[listening tts] generation failed for section %s: %s", section_id, str(e)[:300])
        raise HTTPException(status_code=502, detail="Audio generation failed. Try again.")

    url = await _store_and_set_audio(section_id, audio_bytes, "mp3", "audio/mpeg", transcript=turns)
    return {"url": url}


# ── ADMIN: tests (a test = one full paper grouping many sections) ────

class ListeningTestCreate(BaseModel):
    title: str


@router.post("/admin/tests")
def create_test(req: ListeningTestCreate, _admin=Depends(require_admin)):
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="Test title is required")
    supabase = get_supabase()
    # Draft by default: a new test is empty, so it starts hidden until its sections
    # + audio are attached and reviewed, then the admin flips it live.
    try:
        row = supabase.table("listening_tests").insert({"title": req.title.strip(), "is_active": False}).execute().data[0]
    except Exception as e:
        if "duplicate key" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"A listening test titled \"{req.title.strip()}\" already exists")
        raise
    return row


@router.get("/admin/tests")
def admin_list_tests(_admin=Depends(require_admin)):
    """All tests + a readiness summary per test: active-section count, which parts
    (A/B/C) are present, total questions, how many still lack a correct answer, and
    how many sections still lack audio -- so incomplete tests are flaggable without
    expanding each. Only ACTIVE sections count."""
    supabase = get_supabase()
    tests = supabase.table("listening_tests").select("id, title, is_active, created_at").order("created_at", desc=True).execute().data
    sections = supabase.table("listening_sections").select(
        "id, part, test_id, is_active, audio_url"
    ).not_.is_("test_id", "null").execute().data
    active = [s for s in sections if s.get("is_active")]
    sid_to_test = {s["id"]: s["test_id"] for s in active}
    qrows = supabase.table("questions").select(
        "section_id, correct_answer"
    ).in_("section_id", list(sid_to_test.keys())).execute().data if sid_to_test else []

    summary: Dict[int, dict] = {
        t["id"]: {"section_count": 0, "parts": set(), "question_count": 0, "missing_answers": 0, "missing_audio": 0}
        for t in tests
    }
    for s in active:
        row = summary.get(s["test_id"])
        if row is not None:
            row["section_count"] += 1
            row["parts"].add(s["part"])
            if not (s.get("audio_url") or "").strip():
                row["missing_audio"] += 1
    for q in qrows:
        row = summary.get(sid_to_test.get(q["section_id"]))
        if row is not None:
            row["question_count"] += 1
            if not (q.get("correct_answer") or "").strip():
                row["missing_answers"] += 1

    return [{
        **t,
        "section_count": summary[t["id"]]["section_count"],
        "parts": sorted(summary[t["id"]]["parts"]),
        "question_count": summary[t["id"]]["question_count"],
        "missing_answers": summary[t["id"]]["missing_answers"],
        "missing_audio": summary[t["id"]]["missing_audio"],
    } for t in tests]


@router.get("/admin/tests/{test_id}/detail")
def admin_test_detail(test_id: int, _admin=Depends(require_admin)):
    """Full contents of one test for the admin drill-down: sections grouped by part
    (A->B->C), each with its questions (options + correct_answer), audio presence, and
    a missing-answer count. Includes hidden sections (is_active=false) so they can be
    managed."""
    supabase = get_supabase()
    t = supabase.table("listening_tests").select("id, title, is_active, part_audio, part_audio_times").eq("id", test_id).execute()
    if not t.data:
        raise HTTPException(status_code=404, detail="Test not found")

    sections = supabase.table("listening_sections").select(
        "id, title, part, difficulty, is_active, audio_url, body, audio_start, audio_end"
    ).eq("test_id", test_id).execute().data
    sections.sort(key=lambda s: (_PART_ORDER.get(s["part"], 9), s["id"]))

    sids = [s["id"] for s in sections]
    qrows = supabase.table("questions").select(
        "id, content, type, options, correct_answer, section_id"
    ).in_("section_id", sids).order("id").execute().data if sids else []
    q_by_section: Dict[int, list] = {}
    for q in qrows:
        q_by_section.setdefault(q["section_id"], []).append(q)

    def _section_out(s: dict) -> dict:
        qs = q_by_section.get(s["id"], [])
        return {
            "id": s["id"],
            "title": s["title"],
            "part": s["part"],
            "difficulty": s["difficulty"],
            "is_active": s["is_active"],
            "has_audio": bool(s.get("audio_url")),
            "audio_start": s.get("audio_start"),
            "audio_end": s.get("audio_end"),
            "body": s.get("body"),
            "question_count": len(qs),
            "missing_answers": sum(1 for q in qs if not (q.get("correct_answer") or "").strip()),
            "questions": [_question_out(q, include_answer=True) for q in qs],
        }

    groups = [
        {"part": part, "sections": [_section_out(s) for s in sections if s["part"] == part]}
        for part in ("A", "B", "C")
    ]
    groups = [g for g in groups if g["sections"]]
    return {
        "id": t.data[0]["id"],
        "title": t.data[0]["title"],
        "is_active": t.data[0]["is_active"],
        "part_audio": t.data[0].get("part_audio") or {},
        "part_audio_times": t.data[0].get("part_audio_times") or {},
        "groups": groups,
    }


@router.get("/admin/tests/{test_id}/preview")
def admin_preview_test(test_id: int, _admin=Depends(require_admin)):
    """What students will see, but works BEFORE publishing: same payload as the
    student GET /tests/{id}, ignoring is_active so an admin can review a test as a
    full session before making it live."""
    return _load_test_payload(test_id, include_inactive=True)


@router.post("/admin/tests/{test_id}/active")
def set_test_active(test_id: int, req: SetActiveRequest, _admin=Depends(require_admin)):
    """Publish/unpublish a whole test. Unpublished tests vanish from the student list."""
    supabase = get_supabase()
    existing = supabase.table("listening_tests").select("id").eq("id", test_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Test not found")
    supabase.table("listening_tests").update({"is_active": req.is_active}).eq("id", test_id).execute()
    return {"success": True, "is_active": req.is_active}


@router.delete("/admin/tests/{test_id}")
def delete_test(test_id: int, _admin=Depends(require_admin)):
    """Delete a test. Its sections are NOT deleted -- they detach (test_id -> null via
    ON DELETE SET NULL) and remain as standalone sections to reuse or delete."""
    supabase = get_supabase()
    existing = supabase.table("listening_tests").select("id").eq("id", test_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Test not found")
    supabase.table("listening_tests").delete().eq("id", test_id).execute()
    return {"success": True}


# ── ADMIN: AI content drafting (PDF question extract, audio transcribe) ───
# Mirrors reading.py's OpenRouter/Gemini pipeline: Gemini reads the PDF/audio
# natively and returns structured section + question JSON for admin review.
# Nothing is persisted by extract/transcribe except the audio file itself --
# the admin reviews the draft, then POSTs /admin/save.

LISTENING_EXTRACT_PROMPT = """You are an OET Listening content specialist. The attached PDF is a real OET Listening test QUESTION PAPER (the printed booklet the candidate writes on — not the audio). Extract every question from all three parts, exactly as written. Do NOT invent or paraphrase content.

An OET Listening paper has three parts, and you MUST handle them differently:

- PART A: TWO extracts (questions 1-24, twelve per extract), each a health professional talking to a patient, presented as a NOTES sheet the candidate completes while listening. Treat EACH extract as its OWN section (part="A"). For each:
  - body = reproduce the ENTIRE notes sheet as it appears: the patient name line, the section headings (e.g. "Patient's description of symptoms"), the non-blank context bullets (e.g. "loss of mobility", "problems sleeping"), and each numbered blank shown inline as "(N) ______". Preserve order and structure. Use Markdown (headings, bullet lists) so it renders like the printed sheet.
  - questions = one "short_answer" question PER numbered blank, in order. content = a short label identifying that blank in context (e.g. "(1) back injury sustained (lifting ___)"). options = []. correct_answer = the answer from the answer key if one is available, otherwise "" (empty).
- PART B: SIX short independent extracts (questions 25-30), each with ONE multiple-choice question. Treat EACH extract as its OWN section (part="B") with a single "mcq" question. Omit body (Part B has no on-screen notes).
- PART C: TWO longer extracts — an interview or a presentation (questions 31-42), each with SIX multiple-choice questions. Treat EACH extract as its OWN section (part="C") containing only its own six questions. Omit body.

CRITICAL: OET Listening Part B AND Part C multiple-choice questions have exactly THREE options (A, B, C) — never four. (This differs from OET Reading Part C, which has four.)

For every "mcq" question:
- content = the question stem exactly as written (e.g. "What does she warn her colleague about?").
- options = the full text of each choice in order, WITHOUT the "A/B/C" labels.
- correct_answer = if an answer key is available (a second attached PDF, or a key section inside this PDF), copy the correct option's OWN exact text character-for-character from your options list. Otherwise "".

For every "short_answer" question (Part A blanks only):
- content = the blank's label/context as described above.
- options = [].
- correct_answer = the reference answer from the key as plain text, or "".

Return ONLY this JSON, no other text:
{
  "sections": [
    {"title": "short descriptive title", "part": "A", "difficulty": "beginner|intermediate|advanced", "body": "the notes sheet as Markdown", "questions": [{"content": "(1) ...", "type": "short_answer", "options": [], "correct_answer": ""}]},
    {"title": "...", "part": "B", "difficulty": "intermediate", "questions": [{"content": "...", "type": "mcq", "options": ["...", "...", "..."], "correct_answer": "must be identical to one option, or empty"}]}
  ]
}

If the PDF contains no usable OET Listening content, return {"error": "No OET listening content found in this PDF"}."""


async def _openrouter_pdf(prompt: str, pdf_base64: str, answer_key_base64: Optional[str], max_tokens: int, tag: str) -> Dict[str, Any]:
    """Send a PDF (and optional answer-key PDF) to the "listening_ocr" purpose
    (mistral-ocr file-parser reads it as rendered pages -- real OET papers are
    watermark-stamped, which the free text engine chokes on) and parse the
    JSON reply. Same call shape reading.py uses."""
    message_content: List[Dict[str, Any]] = [
        {"type": "text", "text": prompt},
        {"type": "file", "file": {"filename": "listening.pdf", "file_data": f"data:application/pdf;base64,{pdf_base64}"}},
    ]
    if answer_key_base64:
        message_content.append({"type": "file", "file": {
            "filename": "answer_key.pdf", "file_data": f"data:application/pdf;base64,{answer_key_base64}",
        }})

    result = await _call_ai(
        [{"role": "user", "content": message_content}],
        purpose="listening_ocr",
        max_tokens=max_tokens,
        json_mode=True,
        temperature=0.2,
        extra_payload={"plugins": [{"id": "file-parser", "pdf": {"engine": "mistral-ocr"}}]},
        timeout=240.0,
    )
    if result.get("provider_failure"):
        raise HTTPException(status_code=504, detail="Extraction took too long. Try uploading one part at a time.")

    if result.get("finish_reason") == "length":
        # ponytail: no salvage-recovery yet (reading added it only after big papers
        # truncated live). If a monster listening paper truncates, the parse fails and
        # the admin retries one part at a time. Add reading-style _salvage if it recurs.
        logger.warning("[%s] response truncated (finish_reason=length) at max_tokens", tag)

    if "raw_feedback" in result:
        logger.warning("[%s] JSON parse failed, raw content head=%s", tag, result["raw_feedback"][:1000])
        raise HTTPException(
            status_code=502,
            detail="The paper was too large to extract in one pass. Try uploading one part (A, B or C) at a time.",
        )
    if result.get("error"):
        logger.warning("[%s] model returned no content, raw head=%s", tag, json.dumps(result)[:500])
    return result


@router.post("/admin/extract")
async def extract_listening(
    file: UploadFile = File(...),
    answer_key: Optional[UploadFile] = File(None),
    _admin=Depends(require_admin),
):
    """Upload an OET Listening question-paper PDF (and optionally a separate answer-key
    PDF); return a structured, editable sections + questions draft for admin review.
    Nothing is saved -- the admin reviews then POSTs /admin/save (and attaches audio
    via upload or generate-audio)."""
    if _extract_rate_limiter.is_rate_limited("admin"):
        raise HTTPException(status_code=429, detail="Too many extractions — please slow down.")
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    if answer_key is not None and answer_key.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status_code=400, detail="Answer key must be a PDF")

    contents = await file.read()
    if len(contents) > MAX_PDF_BYTES:
        raise HTTPException(status_code=400, detail="PDF must be under 10MB")
    pdf_base64 = base64.b64encode(contents).decode("utf-8")

    answer_key_base64 = None
    if answer_key is not None:
        answer_contents = await answer_key.read()
        if len(answer_contents) > MAX_PDF_BYTES:
            raise HTTPException(status_code=400, detail="Answer key PDF must be under 10MB")
        answer_key_base64 = base64.b64encode(answer_contents).decode("utf-8")

    return await _openrouter_pdf(LISTENING_EXTRACT_PROMPT, pdf_base64, answer_key_base64, max_tokens=60000, tag="listening-extract")


LISTENING_TRANSCRIBE_PROMPT = """You are an OET Listening content specialist. Listen to the attached audio and produce (1) a verbatim, speaker-labelled transcript and (2) comprehension questions, matching whichever OET Listening part this recording fits:

- PART A (a health professional consultation, note-completion): produce "short_answer" gap-fill questions, each a short label for a fact stated in the audio; correct_answer = the exact word(s) spoken (a short phrase, not a full sentence). Also produce a "body": a Markdown notes sheet with headings and the numbered blanks, like the printed OET Part A sheet.
- PART B (one short, self-contained workplace extract, ~1 minute): produce exactly ONE "mcq" question with THREE options testing the gist/purpose. Omit body.
- PART C (a longer interview or presentation): produce 6 "mcq" questions with THREE options each, covering the recording in order. Omit body.

Every OET Listening "mcq" question has exactly THREE options. For every "mcq", correct_answer must be identical to one of its own options, character-for-character.

Return ONLY this JSON, no other text:
{
  "title": "short descriptive title",
  "part": "A, B, or C",
  "difficulty": "beginner|intermediate|advanced",
  "transcript": [{"speaker": "Physiotherapist", "text": "..."}, {"speaker": "Patient", "text": "..."}],
  "body": "Part A notes sheet as Markdown, or null for B/C",
  "questions": [
    {"content": "...", "type": "mcq", "options": ["...", "...", "..."], "correct_answer": "must match one option exactly"},
    {"content": "(1) ...", "type": "short_answer", "options": [], "correct_answer": "the missing word(s)"}
  ]
}

If the audio is not usable OET Listening content, return {"error": "No usable listening content found in this audio"}."""


async def _transcribe_audio_draft(audio_base64: str, audio_format: str) -> Dict[str, Any]:
    """Send audio to the "listening_ocr" purpose (Gemini transcribes natively
    via OpenRouter) and get back a structured transcript + questions draft."""
    result = await _call_ai(
        [{"role": "user", "content": [
            {"type": "text", "text": LISTENING_TRANSCRIBE_PROMPT},
            {"type": "input_audio", "input_audio": {"data": audio_base64, "format": audio_format}},
        ]}],
        purpose="listening_ocr",
        max_tokens=8000,
        json_mode=True,
        temperature=0.2,
        timeout=240.0,
    )
    if result.get("provider_failure"):
        raise HTTPException(status_code=504, detail="Transcription took too long. Try a shorter clip.")
    if "raw_feedback" in result:
        logger.warning("[listening transcribe] JSON parse failed, raw head=%s", result["raw_feedback"][:1000])
        raise HTTPException(status_code=502, detail="AI returned an unreadable response. Try again.")
    return result


@router.post("/admin/transcribe")
async def transcribe_listening(
    file: UploadFile = File(...),
    _admin=Depends(require_admin),
):
    """Upload a real audio extract: it's stored to the bucket (the audio is the
    deliverable) and transcribed into a section draft (transcript + questions) for
    admin review. Returns the draft + the audio's public URL to pass to /admin/save."""
    if _extract_rate_limiter.is_rate_limited("admin"):
        raise HTTPException(status_code=429, detail="Too many transcriptions — please slow down.")

    audio_format = AUDIO_CONTENT_TYPES.get(file.content_type)
    if not audio_format:
        raise HTTPException(status_code=400, detail="Use an mp3, wav, or m4a file")
    contents = await file.read()
    if len(contents) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Audio must be under 25MB")

    audio_url = await _upload_to_bucket(f"pending/{uuid.uuid4().hex}.{audio_format}", contents, file.content_type)
    draft = await _transcribe_audio_draft(base64.b64encode(contents).decode("utf-8"), audio_format)
    if draft.get("error"):
        logger.warning("[listening transcribe] model returned no content, raw error=%s", draft.get("error"))
    return {**draft, "audio_url": audio_url}


# ── ADMIN: attach answers from a key PDF ─────────────────────────────

ATTACH_ANSWERS_PROMPT_TEMPLATE = """You are matching answers from an OET Listening answer-key PDF to an \
already-known, ordered list of listening questions. The questions are given below in their original order — \
match them to the answer key by that same order and by question content, exactly as the key numbers them.

Questions (in order):
{questions_json}

For each question, find its answer in the attached answer-key PDF and return:
- For "mcq" questions: the correct option's own exact text, copied character-for-character from that \
question's "options" list above (never the answer key's own wording).
- For "short_answer" questions: the reference answer text from the key, as plain text.

Only include a question in your response if you can confidently find its answer in the key — skip (omit) \
any question you can't resolve rather than guessing.

Return ONLY this JSON, no other text:
{{"answers": [{{"questionId": 0, "correct_answer": "..."}}]}}"""


async def _attach_answers_from_pdf(questions: List[dict], answer_key_base64: str) -> Dict[int, str]:
    """One AI call: given ordered questions + a separate answer-key PDF, return
    {questionId: correct_answer} for whichever questions it can resolve. Mirrors
    reading.py's attach-answers."""
    questions_json = json.dumps([
        {"questionId": q["id"], "content": q["content"], "type": q["type"], "options": q["options"]}
        for q in questions
    ], indent=2)

    result = await _call_ai(
        [{"role": "user", "content": [
            {"type": "text", "text": ATTACH_ANSWERS_PROMPT_TEMPLATE.format(questions_json=questions_json)},
            {"type": "file", "file": {"filename": "answer_key.pdf", "file_data": f"data:application/pdf;base64,{answer_key_base64}"}},
        ]}],
        purpose="listening_ocr",
        max_tokens=8000,
        json_mode=True,
        temperature=0.1,
        extra_payload={"plugins": [{"id": "file-parser", "pdf": {"engine": "mistral-ocr"}}]},
        timeout=180.0,
    )
    if result.get("provider_failure"):
        raise HTTPException(status_code=504, detail="Matching timed out. Try again.")
    if "raw_feedback" in result:
        logger.warning("[listening attach answers] JSON parse failed, raw head=%s", result["raw_feedback"][:1000])
        raise HTTPException(status_code=502, detail="AI returned an unreadable response. Try again.")
    return {a["questionId"]: a["correct_answer"] for a in result.get("answers", []) if a.get("correct_answer")}


def _apply_attached_answers(supabase, questions: List[dict], answers_by_qid: Dict[int, str]) -> int:
    """Write resolved answers back, skipping any MCQ answer that doesn't exactly match
    an option (never save a wrong answer). Returns how many were applied."""
    questions_by_id = {q["id"]: q for q in questions}
    matched = 0
    for qid, answer in answers_by_qid.items():
        q = questions_by_id.get(qid)
        if not q:
            continue  # model returned an id not in this set
        if q["type"] == "mcq" and answer not in q["options"]:
            continue  # doesn't match an option exactly -- skip rather than save wrong
        supabase.table("questions").update({"correct_answer": answer}).eq("id", qid).execute()
        matched += 1
    return matched


async def _read_answer_key_pdf(answer_key: UploadFile) -> str:
    if answer_key.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status_code=400, detail="Answer key must be a PDF")
    contents = await answer_key.read()
    if len(contents) > MAX_PDF_BYTES:
        raise HTTPException(status_code=400, detail="Answer key PDF must be under 10MB")
    return base64.b64encode(contents).decode("utf-8")


@router.post("/admin/sections/{section_id}/attach-answers")
async def attach_section_answers(
    section_id: int,
    answer_key: UploadFile = File(...),
    _admin=Depends(require_admin),
):
    """Upload an answer-key PDF for ONE section; AI matches it against that section's
    questions (by order + content) and fills correct_answer. Unresolved questions stay
    blank for manual review or a retry."""
    if _extract_rate_limiter.is_rate_limited("admin"):
        raise HTTPException(status_code=429, detail="Too many requests — please slow down.")
    answer_key_base64 = await _read_answer_key_pdf(answer_key)

    supabase = get_supabase()
    qs = supabase.table("questions").select("id, content, type, options").eq("section_id", section_id).order("id").execute()
    if not qs.data:
        raise HTTPException(status_code=404, detail="Section not found or has no questions")
    questions = [{
        "id": q["id"], "content": q["content"],
        "type": "short_answer" if q.get("type") == "short_answer" else "mcq",
        "options": json.loads(q["options"]) if q.get("options") else [],
    } for q in qs.data]

    answers_by_qid = await _attach_answers_from_pdf(questions, answer_key_base64)
    matched = _apply_attached_answers(supabase, questions, answers_by_qid)
    return {"matched": matched, "total": len(questions)}


@router.post("/admin/tests/{test_id}/attach-answers")
async def attach_test_answers(
    test_id: int,
    answer_key: UploadFile = File(...),
    _admin=Depends(require_admin),
):
    """Upload ONE answer-key PDF for a whole test: AI matches it against every question
    in every section (Part A -> B -> C, in paper order) and fills correct_answer across
    the lot. Same safety as the single-section attach."""
    if _extract_rate_limiter.is_rate_limited("admin"):
        raise HTTPException(status_code=429, detail="Too many requests — please slow down.")
    answer_key_base64 = await _read_answer_key_pdf(answer_key)

    supabase = get_supabase()
    t = supabase.table("listening_tests").select("id").eq("id", test_id).execute()
    if not t.data:
        raise HTTPException(status_code=404, detail="Test not found")
    sections = supabase.table("listening_sections").select("id, part").eq("test_id", test_id).execute().data
    part_by_sid = {s["id"]: s["part"] for s in sections}
    sids = list(part_by_sid.keys())
    if not sids:
        raise HTTPException(status_code=404, detail="Test has no sections")

    qrows = supabase.table("questions").select("id, content, type, options, section_id").in_("section_id", sids).execute().data
    if not qrows:
        raise HTTPException(status_code=404, detail="Test has no questions")

    # Order the way the paper (and its key) run: Part A -> B -> C, then section, then question.
    qrows.sort(key=lambda q: (_PART_ORDER.get(part_by_sid.get(q["section_id"]), 9), q["section_id"], q["id"]))
    questions = [{
        "id": q["id"], "content": q["content"],
        "type": "short_answer" if q.get("type") == "short_answer" else "mcq",
        "options": json.loads(q["options"]) if q.get("options") else [],
    } for q in qrows]

    answers_by_qid = await _attach_answers_from_pdf(questions, answer_key_base64)
    matched = _apply_attached_answers(supabase, questions, answers_by_qid)
    return {"matched": matched, "total": len(questions)}


# ── ADMIN: split one full-test recording into per-section clips ───────

@router.post("/admin/tests/{test_id}/split-audio")
async def split_test_audio(
    test_id: int,
    file: UploadFile = File(...),
    segments: str = Form(...),
    _admin=Depends(require_admin),
):
    """Upload ONE continuous recording (all parts) plus a list of
    [{section_id, start, end}] in seconds; ffmpeg cuts each segment out and attaches it
    as that section's audio. Lets an admin use a single OET recording instead of
    pre-splitting it into per-extract clips."""
    if _upload_rate_limiter.is_rate_limited("admin"):
        raise HTTPException(status_code=429, detail="Too many uploads — please slow down.")
    if file.content_type not in AUDIO_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Use an mp3, wav, or m4a file")
    try:
        seg_list = json.loads(segments)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid segment data")
    if not isinstance(seg_list, list) or not seg_list:
        raise HTTPException(status_code=400, detail="Enter start/end times for at least one section")

    supabase = get_supabase()
    rows = supabase.table("listening_sections").select("id").eq("test_id", test_id).execute().data
    valid_ids = {r["id"] for r in rows}
    if not valid_ids:
        raise HTTPException(status_code=404, detail="Test has no sections")

    contents = await file.read()
    if len(contents) > MAX_FULL_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Full recording must be under 100MB")

    # One temp file, cut many times. ffmpeg re-decodes per cut, fine for a low-volume
    # admin action. The full file never enters the bucket -- only the small clips do.
    src_fd, src_path = tempfile.mkstemp(suffix=".audio")
    os.close(src_fd)
    attached: List[int] = []
    failed: List[Any] = []
    try:
        with open(src_path, "wb") as f:
            f.write(contents)
        for seg in seg_list:
            sid = seg.get("section_id")
            start, end = seg.get("start"), seg.get("end")
            if sid not in valid_ids or not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or end <= start:
                failed.append(sid)
                continue
            try:
                clip = await run_sync(cut_segment, src_path, float(start), float(end))
                await _store_and_set_audio(sid, clip, "mp3", "audio/mpeg", start=float(start), end=float(end))
                attached.append(sid)
            except Exception as e:
                logger.error("[listening split] section %s cut failed: %s", sid, str(e)[:200])
                failed.append(sid)
    finally:
        try:
            os.remove(src_path)
        except OSError:
            pass

    if not attached:
        raise HTTPException(status_code=502, detail="Could not cut any segments — check your start/end times.")
    return {"attached": attached, "failed": failed}


# ── ADMIN: per-PART audio (narrator + that part's extracts, one clip per part) ──

def _set_part_audio(test_id: int, part: str, url: str, start: Optional[float] = None, end: Optional[float] = None) -> None:
    """Merge one part's intro audio URL into the test's part_audio map ({A,B,C} -> url),
    and its cut range into part_audio_times (display only) when it came from a cut."""
    supabase = get_supabase()
    row = supabase.table("listening_tests").select("part_audio, part_audio_times").eq("id", test_id).execute()
    data = row.data[0] if row.data else {}
    audio = (data.get("part_audio") or {})
    audio[part] = url
    update: Dict[str, Any] = {"part_audio": audio}
    if start is not None and end is not None:
        times = (data.get("part_audio_times") or {})
        times[part] = {"start": start, "end": end}
        update["part_audio_times"] = times
    supabase.table("listening_tests").update(update).eq("id", test_id).execute()


@router.post("/admin/tests/{test_id}/parts/{part}/audio")
async def upload_part_audio(
    test_id: int,
    part: str,
    audio: UploadFile = File(...),
    _admin=Depends(require_admin),
):
    """Upload one audio file for a whole part (A/B/C) -- the narrator + all that part's
    extracts. Plays once when the student enters the part."""
    if part not in ("A", "B", "C"):
        raise HTTPException(status_code=400, detail="Part must be A, B, or C")
    if _upload_rate_limiter.is_rate_limited("admin"):
        raise HTTPException(status_code=429, detail="Too many uploads — please slow down.")
    ext = AUDIO_CONTENT_TYPES.get(audio.content_type)
    if not ext:
        raise HTTPException(status_code=400, detail="Use an mp3, wav, or m4a file")
    contents = await audio.read()
    if len(contents) > MAX_FULL_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Audio must be under 100MB")

    supabase = get_supabase()
    if not supabase.table("listening_tests").select("id").eq("id", test_id).execute().data:
        raise HTTPException(status_code=404, detail="Test not found")

    url = await _upload_to_bucket(f"tests/{test_id}/part-{part}-{uuid.uuid4().hex}.{ext}", contents, audio.content_type)
    _set_part_audio(test_id, part, url)
    return {"part": part, "url": url}


@router.post("/admin/tests/{test_id}/split-parts")
async def split_part_audio(
    test_id: int,
    file: UploadFile = File(...),
    segments: str = Form(...),
    _admin=Depends(require_admin),
):
    """Upload ONE full recording + [{part, start, end}] in seconds; ffmpeg cuts each
    part out and sets it as that part's audio. The lazy way to turn a single OET
    recording into the three part clips."""
    if _upload_rate_limiter.is_rate_limited("admin"):
        raise HTTPException(status_code=429, detail="Too many uploads — please slow down.")
    if file.content_type not in AUDIO_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Use an mp3, wav, or m4a file")
    try:
        seg_list = json.loads(segments)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid segment data")
    if not isinstance(seg_list, list) or not seg_list:
        raise HTTPException(status_code=400, detail="Enter start/end times for at least one part")

    supabase = get_supabase()
    if not supabase.table("listening_tests").select("id").eq("id", test_id).execute().data:
        raise HTTPException(status_code=404, detail="Test not found")

    contents = await file.read()
    if len(contents) > MAX_FULL_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Full recording must be under 100MB")

    src_fd, src_path = tempfile.mkstemp(suffix=".audio")
    os.close(src_fd)
    attached: List[str] = []
    failed: List[Any] = []
    try:
        with open(src_path, "wb") as f:
            f.write(contents)
        for seg in seg_list:
            part = seg.get("part")
            start, end = seg.get("start"), seg.get("end")
            if part not in ("A", "B", "C") or not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or end <= start:
                failed.append(part)
                continue
            try:
                clip = await run_sync(cut_segment, src_path, float(start), float(end))
                url = await _upload_to_bucket(f"tests/{test_id}/part-{part}-{uuid.uuid4().hex}.mp3", clip, "audio/mpeg")
                _set_part_audio(test_id, part, url, start=float(start), end=float(end))
                attached.append(part)
            except Exception as e:
                logger.error("[listening split-parts] part %s cut failed: %s", part, str(e)[:200])
                failed.append(part)
    finally:
        try:
            os.remove(src_path)
        except OSError:
            pass

    if not attached:
        raise HTTPException(status_code=502, detail="Could not cut any parts — check your start/end times.")
    return {"attached": attached, "failed": failed}


# ── ADMIN: AI auto-detect extract cuts (Deepgram ASR + cue-matching) ──

async def _map_cuts_via_llm(lines: List[str], sections: List[dict]) -> Dict[str, List[dict]]:
    """Given a timestamped transcript + the test's ordered extracts, ask the LLM to read
    the narrator's scripted cues and return (a) each extract's start/end and (b) each
    part's intro start/end, in seconds. The LLM reads times straight off the accurate ASR
    transcript (never guesses from raw audio). Returns {"cuts": [{section_id,start,end}],
    "intros": [{part,start,end}]}."""
    section_list = "\n".join(f"{i + 1}. Part {s['part']} — {s['title']}" for i, s in enumerate(sections))
    parts = sorted({s["part"] for s in sections}, key=lambda p: _PART_ORDER.get(p, 9))
    transcript = "\n".join(lines)
    prompt = f"""You are given a timestamped transcript of a full OET Listening recording. Each line starts with the time in SECONDS in square brackets, e.g. "[132.5] some words".

The test has {len(sections)} extracts, in THIS order:
{section_list}

OET narration structure:
- Part A: note-completion consultations. The narrator says "Extract one" / "Extract two" and "You now have thirty seconds to look at the notes", then the conversation.
- Part B: six short extracts, each introduced by "Now look at question N" and "You hear a ..." (a nurse, a manager, etc.).
- Part C: long interviews/presentations, introduced by "Now look at extract one/two" and "You hear ...".

TASK 1 — for EACH extract in order, find:
- start = the second the narrator BEGINS introducing that extract (include the extract's own intro, e.g. "Extract one. You hear a physiotherapist...").
- end = just before the NEXT extract's intro begins, or the end of that part.

TASK 2 — for EACH part present ({', '.join(parts)}), find the PART INTRO:
- start = where the narrator begins that part's GENERAL instructions ("Part A. In this part of the test, you'll hear two extracts..."). For Part A, start at the very beginning of the test intro (second 0).
- end = where the FIRST extract of that part begins (the start you gave that extract in Task 1).

Use ONLY timestamps that appear in the transcript. Times are seconds (numbers). Give exactly {len(sections)} cuts (index 1..{len(sections)}) and one intro per part.

Transcript:
{transcript}

Return ONLY this JSON, no other text:
{{"cuts": [{{"index": 1, "start": 0.0, "end": 0.0}}], "intros": [{{"part": "A", "start": 0.0, "end": 0.0}}]}}"""

    result = await _call_ai(
        [{"role": "user", "content": prompt}],
        purpose="listening_audio_segmentation",
        max_tokens=2000,
        json_mode=True,
    )
    if result.get("provider_failure"):
        return {"cuts": [], "intros": []}
    cuts: List[dict] = []
    for c in result.get("cuts", []):
        i, start, end = c.get("index"), c.get("start"), c.get("end")
        if not isinstance(i, int) or i < 1 or i > len(sections):
            continue
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or end <= start:
            continue
        cuts.append({"section_id": sections[i - 1]["section_id"], "start": float(start), "end": float(end)})
    intros: List[dict] = []
    for c in result.get("intros", []):
        part, start, end = c.get("part"), c.get("start"), c.get("end")
        if part not in ("A", "B", "C") or not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or end <= start:
            continue
        intros.append({"part": part, "start": float(start), "end": float(end)})
    return {"cuts": cuts, "intros": intros}


@router.post("/admin/tests/{test_id}/detect-audio-cuts")
async def detect_audio_cuts(
    test_id: int,
    file: UploadFile = File(...),
    _admin=Depends(require_admin),
):
    """Transcribe the full recording (Deepgram) and use the narrator's scripted cues to
    PROPOSE a start/end for each extract, mapped to the test's sections in order. Returns
    the proposed cuts for admin review -- nothing is cut or attached here. The admin
    tweaks the times, then runs the normal split-audio to actually cut + attach."""
    if _extract_rate_limiter.is_rate_limited("admin"):
        raise HTTPException(status_code=429, detail="Too many requests — please slow down.")
    if file.content_type not in AUDIO_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Use an mp3, wav, or m4a file")
    if not settings.DEEPGRAM_API_KEY:
        raise HTTPException(status_code=502, detail="Transcription provider not configured")

    supabase = get_supabase()
    rows = supabase.table("listening_sections").select("id, part, title").eq("test_id", test_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Test has no sections yet — add them first")
    rows.sort(key=lambda s: (_PART_ORDER.get(s["part"], 9), s["id"]))
    sections = [{"section_id": s["id"], "part": s["part"], "title": s["title"] or ""} for s in rows]

    contents = await file.read()
    if len(contents) > MAX_FULL_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Full recording must be under 100MB")

    try:
        words = await deepgram_transcribe(contents, file.content_type)
    except RuntimeError as e:
        logger.error("[detect cuts] deepgram failed: %s", str(e)[:200])
        raise HTTPException(status_code=502, detail="Transcription failed. Try again.")
    if not words:
        raise HTTPException(status_code=502, detail="Couldn't transcribe the audio — check the file.")

    result = await _map_cuts_via_llm(timestamped_lines(words), sections)
    if not result["cuts"] and not result["intros"]:
        raise HTTPException(status_code=502, detail="Couldn't detect the boundaries — set the times manually.")
    return {"cuts": result["cuts"], "intros": result["intros"]}
