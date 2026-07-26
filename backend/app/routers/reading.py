"""OET Reading module.

Student side: list reading passages, fetch one with its MCQs (answers withheld),
submit answers for auto-grading. Reuses the shared `questions` table
(module='reading', options JSON, correct_answer = exact option text) and the same
selectedOption == correct_answer grading contract as /progress/submit-test.

Admin side: upload an OET reading PDF, extract passage + MCQs via OpenRouter
(Gemini reads the PDF natively), review/edit, then save. Same review-gate pattern
as the roleplay-card image extraction in scenario_generator.py.
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.core.config import settings
from app.core.supabase import get_supabase
from app.core.threading import run_sync
from app.core.rate_limit import SlidingWindowRateLimiter
from app.routers.auth import get_current_user, UserInfo
from app.routers.admin import require_admin
from app.services.ai_scoring import _try_parse_json, _call_ai, GEMINI_SCORING_FREE_MODEL
from app.services.mcq_grading import grade_exact_match, combine_graded_results, resolve_latest_wrong_answers
from app.services.open_ended_grading import grade_open_ended_answers
from app.services.explanations import generate_reading_explanation_with_evidence
from app.services.skill_graph import record_skill_observations
from app.services.reading_skills import classify_reading_skill, SKILL_LABELS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reading", tags=["reading"])

_submit_rate_limiter = SlidingWindowRateLimiter(30, 600, name="reading:submit")
_extract_rate_limiter = SlidingWindowRateLimiter(10, 600, name="reading:extract")
_explanation_rate_limiter = SlidingWindowRateLimiter(30, 600, name="reading:explanation")
_dictionary_rate_limiter = SlidingWindowRateLimiter(60, 600, name="reading:dictionary")
_regenerate_rate_limiter = SlidingWindowRateLimiter(15, 600, name="reading:regenerate-text")

# A "Text A" / "## Text B" / "**Text C**" header line marking one of Part A's four
# source texts inside the passage's concatenated body. Mirrors PART_A_HEADER in
# frontend/src/lib/utils.ts -- keep both in sync.
PART_A_HEADER = re.compile(r"^\s*#{0,6}\s*\*{0,2}\s*text\s+([A-D])\b[\s:*.\-]*$", re.IGNORECASE)

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_TERM_LENGTH = 60

# Figures/diagrams for a passage live in a public bucket; the passage body references
# them with markdown image syntax ![figure](url), rendered inline for students.
READING_IMAGE_BUCKET = "reading-images"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_CONTENT_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}


# ── GRADING ───────────────────────────────────────────────────────────
# Exact-match MCQ grading + result combining now live in app.services.mcq_grading
# (Listening reuses the same two functions). Kept as aliases since these
# names are Reading's public contract (tests import them from this module).
grade_reading = grade_exact_match


MIN_TIMED_SECONDS = 5  # below this, a client-side timer glitch is more likely than a real read


def reading_speed_wpm(word_count: int, elapsed_seconds: Optional[int]) -> Optional[int]:
    """Words-per-minute from a passage's word count and how long the student
    spent on it. None when there's nothing sane to compute from (no timer
    sent, or an implausibly short duration)."""
    if not elapsed_seconds or elapsed_seconds < MIN_TIMED_SECONDS or word_count <= 0:
        return None
    return round(word_count / (elapsed_seconds / 60))


combine_reading_results = combine_graded_results


# ── AI SHORT-ANSWER GRADING (Part A word/phrase questions) ───────────

async def _grade_short_answers(items: List[dict], user_id: str = "") -> Optional[Dict[int, dict]]:
    return await grade_open_ended_answers(items, subject="Reading", user_id=user_id)


# ── STUDENT ──────────────────────────────────────────────────────────

@router.get("/passages")
def list_passages(current_user: UserInfo = Depends(get_current_user)):
    """List active reading passages (no body/questions — kept light for the grid)."""
    supabase = get_supabase()
    data = supabase.table("reading_passages").select(
        "id, title, part, difficulty"
    ).eq("is_active", True).order("created_at", desc=True).execute()
    return data.data


@router.get("/passages/{passage_id}")
def get_passage(passage_id: int, current_user: UserInfo = Depends(get_current_user)):
    """Passage body + its MCQs. correct_answer is deliberately NOT selected so the
    answers can't be read before submitting."""
    supabase = get_supabase()
    p = supabase.table("reading_passages").select(
        "id, title, part, difficulty, body"
    ).eq("id", passage_id).eq("is_active", True).execute()
    if not p.data:
        raise HTTPException(status_code=404, detail="Passage not found")
    qs = supabase.table("questions").select(
        "id, content, options, type"
    ).eq("passage_id", passage_id).execute()
    questions = [{
        "id": q["id"],
        "content": q["content"],
        "type": "short_answer" if q.get("type") == "short_answer" else "mcq",
        "options": json.loads(q["options"]) if q.get("options") else [],
    } for q in qs.data]
    return {**p.data[0], "questions": questions}


# ── HIGHLIGHTS + NOTES (per user, per passage) ────────────────────────

class HighlightRange(BaseModel):
    start: int
    end: int


class ReadingNotesRequest(BaseModel):
    highlights: List[HighlightRange] = []
    note: Optional[str] = None


@router.get("/passages/{passage_id}/notes")
async def get_notes(passage_id: int, current_user: UserInfo = Depends(get_current_user)):
    supabase = get_supabase()
    data = await run_sync(
        supabase.table("reading_notes").select("highlights, note")
        .eq("user_id", current_user.id).eq("passage_id", passage_id).execute
    )
    if not data.data:
        return {"highlights": [], "note": None}
    row = data.data[0]
    return {"highlights": row.get("highlights") or [], "note": row.get("note")}


@router.put("/passages/{passage_id}/notes")
async def save_notes(
    passage_id: int,
    req: ReadingNotesRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    for h in req.highlights:
        if h.start < 0 or h.end <= h.start:
            raise HTTPException(status_code=400, detail="Invalid highlight range")

    supabase = get_supabase()
    await run_sync(
        supabase.table("reading_notes").upsert({
            "user_id": current_user.id,
            "passage_id": passage_id,
            "highlights": [h.model_dump() for h in req.highlights],
            "note": req.note,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="user_id,passage_id").execute
    )
    return {"success": True}


class ReadingAnswer(BaseModel):
    questionId: int
    selectedOption: Optional[str] = None


class ReadingSubmitRequest(BaseModel):
    passage_id: int
    answers: List[ReadingAnswer]
    elapsed_seconds: Optional[int] = None


def _skill_observation_bands(results: List[dict], skill_by_qid: Dict[int, str]) -> Dict[str, float]:
    """Group graded results by comprehension skill and turn each skill's accuracy
    into a 0-6 band tagged `reading:skill:<skill>` for the shared skill graph, so
    the weakness summary can rank which question TYPES the student misses."""
    counts: Dict[str, Dict[str, int]] = {}
    for r in results:
        skill = skill_by_qid.get(r["questionId"])
        if not skill:
            continue
        b = counts.setdefault(skill, {"correct": 0, "graded": 0})
        b["graded"] += 1
        if r["is_correct"]:
            b["correct"] += 1
    return {
        f"reading:skill:{skill}": round((c["correct"] / c["graded"]) * 6, 2)
        for skill, c in counts.items() if c["graded"]
    }


@router.post("/submit")
async def submit_reading(
    request: ReadingSubmitRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """Auto-grade a reading attempt and record it as a 'reading' submission so it
    feeds the dashboard's reading band. MCQ questions (Part B/C, and Part A's
    "which text" matching) grade by exact match; Part A short-answer questions
    grade via one batched AI call since there's no fixed option to compare against."""
    if _submit_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many submissions — please slow down.")

    supabase = get_supabase()
    qids = [a.questionId for a in request.answers]
    qdata = await run_sync(
        supabase.table("questions").select("id, content, correct_answer, type").in_("id", qids).execute
    ) if qids else None
    questions_by_id = {q["id"]: q for q in qdata.data} if qdata else {}

    mcq_by_id = {qid: q for qid, q in questions_by_id.items() if q.get("type") != "short_answer"}
    short_by_id = {qid: q for qid, q in questions_by_id.items() if q.get("type") == "short_answer"}
    answers_by_id = {a.questionId: a.selectedOption for a in request.answers}

    mcq_graded = grade_reading(mcq_by_id, [a.model_dump() for a in request.answers])

    short_items = [
        {"questionId": qid, "content": q["content"], "expected": q["correct_answer"], "answer": answers_by_id.get(qid) or ""}
        for qid, q in short_by_id.items()
        if q.get("correct_answer") is not None
    ]
    short_results_map = await _grade_short_answers(short_items, user_id=current_user.id)
    if short_items and short_results_map is None:
        raise HTTPException(status_code=503, detail="Scoring is temporarily unavailable. Please try again in a few minutes.")

    short_results = [{
        "questionId": it["questionId"],
        "selected": it["answer"],
        "correct_answer": short_by_id[it["questionId"]]["correct_answer"],
        "is_correct": (short_results_map or {}).get(it["questionId"], {}).get("is_correct", False),
        "feedback": (short_results_map or {}).get(it["questionId"], {}).get("feedback", ""),
    } for it in short_items]

    combined = combine_reading_results(mcq_graded, short_results)

    passage_data = await run_sync(
        supabase.table("reading_passages").select("part, body").eq("id", request.passage_id).execute
    )
    passage_row = passage_data.data[0] if passage_data.data else None

    words_per_minute = None
    if request.elapsed_seconds and passage_row:
        word_count = len(passage_row["body"].split())
        words_per_minute = reading_speed_wpm(word_count, request.elapsed_seconds)

    if passage_row:
        part = passage_row["part"]
        skill_by_qid = {
            qid: classify_reading_skill(q["content"], q.get("type") or "mcq", part)
            for qid, q in questions_by_id.items()
        }
        await record_skill_observations(current_user.id, {
            f"reading:{part}": combined["band"],
            **_skill_observation_bands(combined["results"], skill_by_qid),
        })

    await run_sync(
        supabase.table("submissions").insert({
            "user_id": current_user.id,
            # NOT scenario_id: passages live in reading_passages, a different id
            # space than the scenarios table scenario_id is FK'd to (writing
            # scenario_id=passage_id there violated that FK and 500'd every
            # submission). The passage id is preserved in feedback instead.
            "module": "reading",
            "answer": f"{combined['correct']}/{combined['graded']} correct",
            "score": combined["band"],
            "feedback": json.dumps({
                "passage_id": request.passage_id,
                "correct": combined["correct"],
                "graded": combined["graded"],
                "results": combined["results"],
                "elapsed_seconds": request.elapsed_seconds,
                "words_per_minute": words_per_minute,
            }),
        }).execute
    )

    return {
        "score": combined["band"],
        "correct": combined["correct"],
        "total": combined["graded"],
        "results": combined["results"],
        "words_per_minute": words_per_minute,
    }


# ── READING TESTS (full-paper session: Part A -> B -> C, one submission) ──

_PART_ORDER = {"A": 0, "B": 1, "C": 2}


def _load_test_payload(test_id: int, include_inactive: bool) -> Dict[str, Any]:
    """Full test for the session player: passages ordered Part A -> B -> C, each with
    its questions, correct_answer withheld. include_inactive=True is the admin preview
    path (ignores is_active on both the test and its passages); the student path keeps
    both filters on."""
    supabase = get_supabase()
    tq = supabase.table("reading_tests").select("id, title").eq("id", test_id)
    if not include_inactive:
        tq = tq.eq("is_active", True)
    t = tq.execute()
    if not t.data:
        raise HTTPException(status_code=404, detail="Test not found")

    pq = supabase.table("reading_passages").select("id, title, part, body").eq("test_id", test_id)
    if not include_inactive:
        pq = pq.eq("is_active", True)
    passages = pq.execute().data
    passages.sort(key=lambda p: (_PART_ORDER.get(p["part"], 9), p["id"]))

    pids = [p["id"] for p in passages]
    qrows = supabase.table("questions").select(
        "id, content, options, type, passage_id"
    ).in_("passage_id", pids).execute().data if pids else []
    q_by_passage: Dict[int, list] = {}
    for q in qrows:
        q_by_passage.setdefault(q["passage_id"], []).append(q)

    out_passages = []
    for p in passages:
        qs = sorted(q_by_passage.get(p["id"], []), key=lambda x: x["id"])
        out_passages.append({
            "id": p["id"],
            "title": p["title"],
            "part": p["part"],
            "body": p["body"],
            "questions": [{
                "id": q["id"],
                "content": q["content"],
                "type": "short_answer" if q.get("type") == "short_answer" else "mcq",
                "options": json.loads(q["options"]) if q.get("options") else [],
            } for q in qs],
        })
    return {"id": t.data[0]["id"], "title": t.data[0]["title"], "passages": out_passages}


@router.get("/tests")
def list_reading_tests(current_user: UserInfo = Depends(get_current_user)):
    """Active tests that have at least one active passage. This is the student's
    'full mock reading test' list."""
    supabase = get_supabase()
    tests = supabase.table("reading_tests").select("id, title").eq("is_active", True).order("created_at", desc=True).execute().data
    if not tests:
        return []
    test_ids = [t["id"] for t in tests]
    passages = supabase.table("reading_passages").select("test_id").in_("test_id", test_ids).eq("is_active", True).execute().data
    counts: Dict[int, int] = {}
    for p in passages:
        counts[p["test_id"]] = counts.get(p["test_id"], 0) + 1
    return [{"id": t["id"], "title": t["title"], "passage_count": counts.get(t["id"], 0)} for t in tests if counts.get(t["id"], 0) > 0]


@router.get("/tests/{test_id}")
def get_reading_test(test_id: int, current_user: UserInfo = Depends(get_current_user)):
    """Full test for the session player. correct_answer is NOT sent (can't be read
    before submitting). Only active tests/passages are visible to students."""
    return _load_test_payload(test_id, include_inactive=False)


class ReadingTestSubmitRequest(BaseModel):
    answers: List[ReadingAnswer]
    elapsed_seconds: Optional[int] = None


@router.post("/tests/{test_id}/submit")
async def submit_reading_test(
    test_id: int,
    request: ReadingTestSubmitRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """Grade a whole test session at once (all Part A/B/C questions), record one
    'reading' submission, and report per-part bands so weak parts feed the skill graph."""
    if _submit_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many submissions — please slow down.")

    supabase = get_supabase()
    t = await run_sync(
        supabase.table("reading_tests").select("id").eq("id", test_id).eq("is_active", True).execute
    )
    if not t.data:
        raise HTTPException(status_code=404, detail="Test not found")

    passages = await run_sync(
        supabase.table("reading_passages").select("id, part").eq("test_id", test_id).eq("is_active", True).execute
    )
    part_by_passage = {p["id"]: p["part"] for p in passages.data}
    pids = list(part_by_passage.keys())
    if not pids:
        raise HTTPException(status_code=404, detail="Test has no passages")

    qrows = await run_sync(
        supabase.table("questions").select("id, content, correct_answer, type, passage_id").in_("passage_id", pids).execute
    )
    questions_by_id = {q["id"]: q for q in qrows.data}
    part_by_qid = {q["id"]: part_by_passage.get(q["passage_id"]) for q in qrows.data}

    # only grade answers to questions that actually belong to this test
    answers = [a for a in request.answers if a.questionId in questions_by_id]
    mcq_by_id = {qid: q for qid, q in questions_by_id.items() if q.get("type") != "short_answer"}
    short_by_id = {qid: q for qid, q in questions_by_id.items() if q.get("type") == "short_answer"}
    answers_by_id = {a.questionId: a.selectedOption for a in answers}

    mcq_graded = grade_reading(mcq_by_id, [a.model_dump() for a in answers])

    short_items = [
        {"questionId": qid, "content": short_by_id[qid]["content"], "expected": short_by_id[qid]["correct_answer"], "answer": answers_by_id.get(qid) or ""}
        for qid in short_by_id
        if qid in answers_by_id and short_by_id[qid].get("correct_answer") is not None
    ]
    short_results_map = await _grade_short_answers(short_items, user_id=current_user.id)
    if short_items and short_results_map is None:
        raise HTTPException(status_code=503, detail="Scoring is temporarily unavailable. Please try again in a few minutes.")

    short_results = [{
        "questionId": it["questionId"],
        "selected": it["answer"],
        "correct_answer": short_by_id[it["questionId"]]["correct_answer"],
        "is_correct": (short_results_map or {}).get(it["questionId"], {}).get("is_correct", False),
        "feedback": (short_results_map or {}).get(it["questionId"], {}).get("feedback", ""),
    } for it in short_items]

    combined = combine_reading_results(mcq_graded, short_results)

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
        skill_by_qid = {
            qid: classify_reading_skill(q["content"], q.get("type") or "mcq", part_by_qid.get(qid) or "?")
            for qid, q in questions_by_id.items()
        }
        await record_skill_observations(current_user.id, {
            **{f"reading:{part}": band for part, band in per_part.items()},
            **_skill_observation_bands(combined["results"], skill_by_qid),
        })

    await run_sync(
        supabase.table("submissions").insert({
            "user_id": current_user.id,
            # NOT scenario_id: reading_tests is a different id space than the
            # scenarios table scenario_id is FK'd to. test_id lives in feedback.
            "module": "reading",
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

    return {
        "score": combined["band"],
        "correct": combined["correct"],
        "total": combined["graded"],
        "results": combined["results"],
        "per_part": per_part,
    }


# ── EXPLANATIONS (cached, generated once per question) ───────────────

@router.get("/questions/{question_id}/explanation")
async def get_explanation(
    question_id: int,
    current_user: UserInfo = Depends(get_current_user),
):
    """Cache-through explanation + the verbatim passage sentence the answer comes
    from (for the "show me where" highlight). First caller pays one AI call; every
    caller after gets both stored on the question for free. If a question was
    explained before this feature (explanation cached, evidence null), one more
    call backfills the evidence so the highlight works on old questions too."""
    if _explanation_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many requests — please slow down.")

    supabase = get_supabase()
    q = await run_sync(
        supabase.table("questions").select("id, content, options, correct_answer, explanation, evidence, passage_id")
        .eq("id", question_id).execute
    )
    if not q.data:
        raise HTTPException(status_code=404, detail="Question not found")
    question = q.data[0]

    # Fully cached (explanation + evidence already resolved): serve for free.
    # evidence == "" means "we tried, no clean sentence" -- also cached, don't retry.
    if question.get("explanation") and question.get("evidence") is not None:
        return {"explanation": question["explanation"], "evidence": question["evidence"]}

    passage_body = ""
    if question.get("passage_id"):
        p = await run_sync(
            supabase.table("reading_passages").select("body").eq("id", question["passage_id"]).execute
        )
        if p.data:
            passage_body = p.data[0].get("body") or ""

    result = await generate_reading_explanation_with_evidence(question, passage_body)
    explanation = result["explanation"] or question.get("explanation") or ""
    if not explanation:
        raise HTTPException(status_code=503, detail="Explanation is temporarily unavailable. Please try again.")

    await run_sync(
        supabase.table("questions").update(
            {"explanation": explanation, "evidence": result["evidence"]}
        ).eq("id", question_id).execute
    )
    return {"explanation": explanation, "evidence": result["evidence"]}


# ── DICTIONARY (global cache, keyed by term text, not per-question) ──

async def _define_term(term: str) -> str:
    prompt = f"""You are a medical dictionary for nursing students preparing for the OET exam. \
Define the term "{term}" in plain, simple English in 1-2 short sentences, the way you'd explain it \
to a patient or a student who has never heard it before. If "{term}" isn't a medical or clinical \
term, just give its everyday definition just as briefly.

Return ONLY this JSON, no other text:
{{"definition": "your 1-2 sentence definition"}}"""

    result = await _call_ai(
        [{"role": "user", "content": prompt}],
        max_tokens=150,
        json_mode=True,
        provider="openrouter",
        model=GEMINI_SCORING_FREE_MODEL,
    )
    if result.get("provider_failure"):
        return ""
    return (result.get("definition") or "").strip()


@router.get("/dictionary")
async def get_definition(
    term: str,
    current_user: UserInfo = Depends(get_current_user),
):
    """Cache-through word lookup for the passage double-click dictionary.
    Cached forever by normalized term text -- shared across every passage,
    every student, and (later) Listening transcripts too."""
    if _dictionary_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many lookups — please slow down.")

    term_key = term.strip().lower()[:MAX_TERM_LENGTH]
    if not term_key:
        raise HTTPException(status_code=400, detail="term is required")

    supabase = get_supabase()
    cached = await run_sync(
        supabase.table("medical_terms").select("definition").eq("term", term_key).execute
    )
    if cached.data:
        await _add_vocab_card(current_user.id, term_key, cached.data[0]["definition"])
        return {"term": term_key, "definition": cached.data[0]["definition"]}

    definition = await _define_term(term_key)
    if not definition:
        raise HTTPException(status_code=503, detail="Definition is temporarily unavailable. Please try again.")

    await run_sync(
        supabase.table("medical_terms").upsert(
            {"term": term_key, "definition": definition}, on_conflict="term"
        ).execute
    )
    await _add_vocab_card(current_user.id, term_key, definition)
    return {"term": term_key, "definition": definition}


async def _add_vocab_card(user_id: str, term: str, definition: str) -> None:
    """Looking a word up is itself the signal it's unfamiliar -- auto-add it
    to the student's SRS deck. ignore_duplicates means looking up an already-
    known word again is a harmless no-op, not a progress reset. Best-effort:
    a deck-add failure must never break the dictionary lookup itself."""
    try:
        await run_sync(
            get_supabase().table("vocab_cards").upsert(
                {"user_id": user_id, "term": term, "definition": definition, "source_module": "dictionary"},
                on_conflict="user_id,term", ignore_duplicates=True,
            ).execute
        )
    except Exception as e:
        logger.warning("[VOCAB_AUTOADD_FAILED] user_id=%s term=%s error=%s", user_id, term, str(e)[:200])


# ── WRONG-ANSWER NOTEBOOK ─────────────────────────────────────────────

MISTAKES_LOOKBACK_SUBMISSIONS = 100


@router.get("/mistakes")
async def list_mistakes(current_user: UserInfo = Depends(get_current_user)):
    """Every question the user has ever gotten wrong in reading practice, most
    recent attempt per question, newest first. Built entirely from data
    already stored on submissions.feedback -- no new table needed."""
    supabase = get_supabase()
    subs = await run_sync(
        supabase.table("submissions").select("feedback, created_at")
        .eq("user_id", current_user.id).eq("module", "reading")
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
        supabase.table("questions").select("id, content, options, correct_answer, passage_id, explanation, evidence")
        .in_("id", qids).execute
    )
    passage_ids = [q["passage_id"] for q in qdata.data if q.get("passage_id")]
    passages_by_id: Dict[int, str] = {}
    if passage_ids:
        p = await run_sync(
            supabase.table("reading_passages").select("id, title").in_("id", passage_ids).execute
        )
        passages_by_id = {row["id"]: row["title"] for row in p.data}

    return [{
        "questionId": q["id"],
        "content": q["content"],
        "options": json.loads(q["options"]) if q.get("options") else [],
        "correct_answer": q["correct_answer"],
        "your_answer": wrong_by_qid[q["id"]].get("selected"),
        "passage_title": passages_by_id.get(q.get("passage_id")),
        "explanation": q.get("explanation"),
        "evidence": q.get("evidence"),
    } for q in qdata.data]


# ── WEAKNESS SUMMARY (per-skill, from the shared skill graph) ─────────

# Ignore a skill until the student has attempted it a couple of times, so one
# unlucky question doesn't brand a whole skill as a weakness.
WEAKNESS_MIN_ATTEMPTS = 2
# Bands at/above this read as "solid" -- only surface genuine weak spots.
WEAKNESS_BAND_CEILING = 5.0


@router.get("/weakness")
async def reading_weakness(current_user: UserInfo = Depends(get_current_user)):
    """The student's weak reading skills (inference, detail, scanning, ...),
    weakest first, straight off the shared skill-graph EMA that every reading
    submission already feeds. Read-only, no AI. Returns [] until there's enough
    signal (each skill needs a couple of attempts)."""
    supabase = get_supabase()
    rows = await run_sync(
        supabase.table("user_skill_stats").select("skill_tag, attempts, ema_score")
        .eq("user_id", current_user.id).like("skill_tag", "reading:skill:%").execute
    )
    out = []
    for r in rows.data:
        if r["attempts"] < WEAKNESS_MIN_ATTEMPTS:
            continue
        band = float(r["ema_score"])
        if band >= WEAKNESS_BAND_CEILING:
            continue
        skill = r["skill_tag"].split(":")[-1]
        out.append({
            "skill": skill,
            "label": SKILL_LABELS.get(skill, skill),
            "band": round(band, 1),
            "attempts": r["attempts"],
        })
    out.sort(key=lambda x: x["band"])  # weakest first
    return out


# ── ADMIN: PDF EXTRACTION + SAVE ─────────────────────────────────────

READING_EXTRACT_PROMPT = """You are an OET Reading content specialist. The attached PDF is a real OET Reading test paper. Extract every usable passage from all three parts. Extract exactly what is written — do NOT invent or paraphrase content.

A real OET Reading paper has three parts, and you must handle them differently:

- PART A: usually four texts (often labelled Text A, Text B, Text C, Text D) shared across roughly 20 questions, of two kinds:
  1. "In which text can you find information about..." / "which text (A, B, C or D)..." matching questions — these DO have a fixed answer space. Extract as type="mcq" with options exactly ["Text A", "Text B", "Text C", "Text D"] (match however many texts actually exist), correct_answer = whichever text the answer key gives, written as "Text X".
  2. "Answer with a word or short phrase from one of the texts" / sentence-completion questions — these have no options at all. Extract as type="short_answer", options=[], correct_answer = the reference answer from the answer key, as plain text (used later to AI-grade the student's own typed answer, so it does not need to be a verbatim quote).
  All Part A questions share the same texts, so output them together as ONE passage: part="A", body = all of Part A's texts concatenated with clear headers (e.g. "Text A:", "Text B:", ...), questions = every Part A question in order, each correctly tagged type="mcq" or type="short_answer" per the rules above.
- PART B: several short, independent text extracts, each followed by its OWN single 3-option (A/B/C) question. Treat EACH extract as its own separate passage (part="B"), with just that one type="mcq" question.
- PART C: one or more longer reading texts (often labelled "Text 1", "Text 2", etc.), each followed by several 4-option (A/B/C/D) questions about it. Treat EACH text as its own separate passage (part="C", type="mcq" questions), containing only the questions that belong to that specific text.

SOME Part B (and occasionally Part C) items use a TABLE instead of a paragraph as their supporting text — e.g. "What does this table show?" followed by options A/B/C, followed by the table itself. In these, the printed order can put the question and options ABOVE the table, unlike the paragraph-based items. Do not confuse an option's own text with the question stem: the question's "content" field must be the actual question or topic sentence exactly as printed (often ending in "?" or a colon/semicolon introducing choices, e.g. "The table clearly shows that;"), and must NEVER be identical to any of that same question's own "options" entries. If you find yourself about to write the same text into both "content" and one of the "options", you have picked the wrong span — look for the real question sentence nearby. Put the table itself into "body" as a GitHub-style Markdown table — a header row, then a separator row of dashes (e.g. | --- | --- | --- |), then one data row per line, columns divided by | — never into "content" or "options".

WHENEVER a passage's source text contains a TABLE (in any part, not just Part B), reproduce it in "body" as a Markdown pipe table exactly as above, so students see the same rows and columns as the paper. For a boxed callout, note, or highlighted panel, keep its text in "body" and prefix it with a short label line (e.g. "NOTE:") so it reads as a distinct block. Do not try to describe pictures/diagrams — transcribe any text inside them and skip purely decorative images.

ANSWER KEY: the correct answer is almost never marked inside the question block itself. It's given by a separate ANSWER KEY — either as a second PDF attached to this same message, or as a section near the end of this same PDF if only one file was provided. Either way it's organized into sections that mirror Part A / Part B / Part C — question numbers restart or overlap between parts, so always match a question to the answer key entry under the SAME part, never across parts. The key may give a bare letter (e.g. "7 B"), or the answer's own text (which may be worded slightly differently — punctuation, capitalization — than how you should write it). If a second PDF is attached, treat it as the authoritative answer key and use it for every question — do not leave a question's correct_answer blank or guess if the answer key resolves it.

For every "mcq" question:
- content = the question stem, exactly as written.
- options = the full text of every choice, in order (without the "A/B/C" labels).
- correct_answer = use the answer key ONLY to identify WHICH option is correct. Then copy that option's own exact text from your options list, character-for-character — never the answer key's own wording.

For every "short_answer" question (Part A type 2 only):
- content = the question stem, exactly as written (including any sentence fragment it completes).
- options = [] (empty array).
- correct_answer = the reference answer from the answer key, as plain text.

Return ONLY this JSON, no other text:
{
  "passages": [
    {
      "title": "short descriptive title for this passage",
      "part": "A, B or C",
      "difficulty": "beginner|intermediate|advanced",
      "body": "the full text of this passage, preserving paragraph breaks; render any tables as GitHub-style Markdown pipe tables",
      "questions": [
        {"content": "...", "type": "mcq", "options": ["...", "...", "..."], "correct_answer": "must be identical to one of this question's options"},
        {"content": "...", "type": "short_answer", "options": [], "correct_answer": "reference answer text"}
      ]
    }
  ]
}

If the PDF contains no usable Part A, Part B, or Part C content at all, return {"error": "No OET reading passage found in this PDF"}."""


def _salvage_passages(content: str) -> Optional[Dict[str, Any]]:
    """Recover complete passage objects from a truncated extraction response. A large
    paper can exceed max_tokens and cut the JSON mid-object, which raw_decode can't
    parse at all. Rather than lose everything, scan the "passages" array and keep every
    fully-closed {...} object (string/escape aware so braces inside text don't fool it),
    dropping the incomplete tail."""
    start = content.find('"passages"')
    if start == -1:
        return None
    bracket = content.find("[", start)
    if bracket == -1:
        return None

    objs: List[str] = []
    depth = 0
    obj_start = -1
    in_str = False
    esc = False
    for i in range(bracket + 1, len(content)):
        ch = content[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and obj_start != -1:
                objs.append(content[obj_start:i + 1])
                obj_start = -1
        elif ch == "]" and depth == 0:
            break

    passages = []
    for o in objs:
        try:
            passages.append(json.loads(o))
        except json.JSONDecodeError:
            continue
    return {"passages": passages} if passages else None


async def _extract_reading_from_pdf(pdf_base64: str, answer_key_base64: Optional[str] = None) -> Dict[str, Any]:
    """Send the PDF (and, if provided, a separate answer-key PDF) to OpenRouter
    (Gemini reads PDFs natively via the file-parser plugin) and get back structured
    passage + questions JSON. A clean, separate answer key is more reliable than one
    the model has to locate and cross-reference inside a single messy exam paper."""
    key = settings.OPENROUTER_API_KEY
    if not key:
        raise HTTPException(status_code=502, detail="AI provider not configured")

    message_content: List[Dict[str, Any]] = [
        {"type": "text", "text": READING_EXTRACT_PROMPT},
        {"type": "file", "file": {
            "filename": "reading.pdf",
            "file_data": f"data:application/pdf;base64,{pdf_base64}",
        }},
    ]
    if answer_key_base64:
        message_content.append({"type": "file", "file": {
            "filename": "answer_key.pdf",
            "file_data": f"data:application/pdf;base64,{answer_key_base64}",
        }})

    payload = {
        "model": "google/gemini-2.5-flash",
        "messages": [{"role": "user", "content": message_content}],
        # mistral-ocr: visual OCR, reads pages as rendered. Needed because real OET
        # PDFs come watermark-stamped (repeated logo images overlaid across the page) --
        # the free "pdf-text" raw content-stream engine choked on that layout and the
        # model got back scrambled/incomplete text, always falling back to "not found"
        # even on valid papers. OCR costs more per page but this is a low-volume
        # admin-only path, not a per-user hot path.
        "plugins": [{"id": "file-parser", "pdf": {"engine": "mistral-ocr"}}],
        "temperature": 0.2,
        # A full 3-part paper (Part A ~20 questions + Part B 6 extracts + Part C 16
        # questions, each with full option text and body) genuinely produces a lot of
        # JSON, and a paper with big comparison TABLES in the body pushes it further --
        # 32000 was still cutting off mid-object on those, breaking JSON unrecoverably.
        # Sit near Gemini 2.5 Flash's real output ceiling (~65k). _salvage_passages
        # below still recovers the complete passages if a monster paper truncates anyway.
        "max_tokens": 60000,
        "response_format": {"type": "json_object"},
    }

    try:
        async with httpx.AsyncClient(timeout=240.0) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
    except httpx.TimeoutException:
        # OCR on a large multi-page PDF can genuinely take minutes -- surface a clean
        # message instead of letting an unhandled timeout look like a server crash.
        logger.error("[reading extract] OpenRouter request timed out")
        raise HTTPException(
            status_code=504,
            detail="Extraction took too long. Try splitting the PDF into smaller files (e.g. one per part) and uploading each separately.",
        )
    if resp.status_code != 200:
        logger.error("[reading extract] OpenRouter HTTP %s: %s", resp.status_code, resp.text[:300])
        raise HTTPException(status_code=502, detail="AI extraction failed. Try again.")

    choice = resp.json()["choices"][0]
    content = choice["message"]["content"]
    if choice.get("finish_reason") == "length":
        # The model hit the output cap and the JSON is cut mid-object. Salvage below
        # can still recover the passages that completed; log it so it's diagnosable.
        logger.warning("[reading extract] response truncated (finish_reason=length) at max_tokens")

    parsed = _try_parse_json("reading-extract", content)
    if parsed is None:
        # Most parse failures here are truncation (JSON cut mid-object). Try to recover
        # every fully-closed passage object rather than losing the whole extraction.
        salvaged = _salvage_passages(content)
        if salvaged and salvaged["passages"]:
            logger.warning(
                "[reading extract] full JSON parse failed; salvaged %d complete passage(s) from a truncated response",
                len(salvaged["passages"]),
            )
            return salvaged
        # _try_parse_json's own raw-content log is DEBUG level, and this app never
        # calls logging.basicConfig() -- the root logger defaults to WARNING, so
        # that line is silently dropped in production. Log it again here at WARNING
        # so a parse failure is actually diagnosable from Render logs.
        logger.warning("[reading extract] JSON parse failed, raw content head=%s", content[:1000])
        raise HTTPException(
            status_code=502,
            detail="The paper was too large to extract in one pass. Try uploading one part (A, B or C) at a time.",
        )
    if parsed.get("error"):
        # Model saw the document but decided nothing matched -- log what it actually
        # received so a repeat failure is diagnosable without re-asking the admin.
        logger.warning("[reading extract] model returned no passages, raw content head=%s", content[:500])
    return parsed


@router.post("/admin/extract")
async def extract_reading(
    file: UploadFile = File(...),
    answer_key: Optional[UploadFile] = File(None),
    _admin=Depends(require_admin),
):
    """Upload an OET reading PDF (and optionally a separate answer-key PDF), return a
    structured (editable) passage + questions draft for admin review. Nothing is
    saved here — the admin reviews then POSTs /save."""
    if _extract_rate_limiter.is_rate_limited("admin"):
        raise HTTPException(status_code=429, detail="Too many extractions — please slow down.")
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    if answer_key is not None and answer_key.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status_code=400, detail="Answer key must be a PDF")

    contents = await file.read()
    if len(contents) > MAX_PDF_BYTES:
        raise HTTPException(status_code=400, detail="PDF must be under 10MB")

    import base64
    pdf_base64 = base64.b64encode(contents).decode("utf-8")

    answer_key_base64 = None
    if answer_key is not None:
        answer_contents = await answer_key.read()
        if len(answer_contents) > MAX_PDF_BYTES:
            raise HTTPException(status_code=400, detail="Answer key PDF must be under 10MB")
        answer_key_base64 = base64.b64encode(answer_contents).decode("utf-8")

    return await _extract_reading_from_pdf(pdf_base64, answer_key_base64)


def _split_part_a_sections(body: str) -> List[Dict[str, Any]]:
    """Split a Part A passage body into its four "Text A"-"Text D" sections,
    keeping each header line verbatim so the body can be rebuilt byte-for-byte
    around a single edited section."""
    sections: List[Dict[str, Any]] = []
    for line in body.split("\n"):
        m = PART_A_HEADER.match(line)
        if m:
            sections.append({"label": m.group(1).upper(), "header": line, "lines": []})
        elif sections:
            sections[-1]["lines"].append(line)
    return sections


def _rebuild_part_a_body(sections: List[Dict[str, Any]], label: str, new_content: str) -> str:
    out: List[str] = []
    for s in sections:
        out.append(s["header"])
        out.extend(new_content.split("\n") if s["label"] == label else s["lines"])
    return "\n".join(out)


class RegenerateTextRequest(BaseModel):
    body: str
    label: str
    instruction: str


@router.post("/admin/regenerate-text")
async def regenerate_passage_text(req: RegenerateTextRequest, _admin=Depends(require_admin)):
    """Rewrite a single Text (A-D) within a Part A passage via AI, leaving the
    other texts untouched. Takes the body straight from the editor (not the DB)
    so unsaved edits aren't clobbered -- returns the full rebuilt body for the
    admin to review and Save as normal."""
    if _regenerate_rate_limiter.is_rate_limited("admin"):
        raise HTTPException(status_code=429, detail="Too many regenerations — please slow down.")
    label = req.label.strip().upper()
    instruction = req.instruction.strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="Say what to change before regenerating.")

    sections = _split_part_a_sections(req.body)
    target = next((s for s in sections if s["label"] == label), None)
    if not target:
        raise HTTPException(status_code=400, detail=f"Text {label} not found in this passage.")
    current_text = "\n".join(target["lines"]).strip()

    prompt = f"""You are rewriting one source text ("Text {label}") inside an OET Reading Part A passage. \
Part A has four short texts (Text A-D) that students scan to answer "which text mentions X" questions, so this \
text must stay similar in LENGTH and STYLE to the current version, on a clinical/nursing topic, and use the same \
formatting conventions (a short title, then plain paragraphs; reproduce any table as a GitHub-style Markdown pipe \
table).

Current Text {label}:
{current_text}

Admin's requested change:
{instruction}

Return ONLY this JSON, no other text:
{{"text": "the full rewritten title + body for Text {label}, same formatting conventions as shown above"}}"""

    result = await _call_ai(
        [{"role": "user", "content": prompt}],
        max_tokens=1500,
        json_mode=True,
        provider="openrouter",
        model=GEMINI_SCORING_FREE_MODEL,
    )
    new_text = (result.get("text") or "").strip()
    if result.get("provider_failure") or not new_text:
        raise HTTPException(status_code=502, detail="AI regeneration failed. Try again.")

    return {"body": _rebuild_part_a_body(sections, label, new_text)}


class ReadingQuestionIn(BaseModel):
    content: str
    type: str = "mcq"  # "mcq" (exact-match) or "short_answer" (AI-graded, Part A word/phrase)
    options: List[str] = []
    correct_answer: str = ""  # blank allowed -- content can be saved before its answer is known


def _validate_reading_questions(questions: List["ReadingQuestionIn"]) -> None:
    """Shared by create and update. MCQ needs >=2 options and, if an answer is
    given, it must exactly match one of them. A blank correct_answer is allowed
    on either type -- filled in later via attach-answers or manual edit."""
    if not questions:
        raise HTTPException(status_code=400, detail="At least one question is required")
    for q in questions:
        if q.type == "short_answer":
            continue
        if len(q.options) < 2:
            raise HTTPException(status_code=400, detail=f"Question needs at least 2 options: {q.content[:50]}")
        if q.correct_answer and q.correct_answer not in q.options:
            raise HTTPException(
                status_code=400,
                detail=f"Correct answer must exactly match one option: {q.content[:50]}",
            )


class ReadingSaveRequest(BaseModel):
    title: str
    part: str = "C"
    difficulty: str = "intermediate"
    body: str
    questions: List[ReadingQuestionIn]
    test_id: Optional[int] = None  # optionally group this passage into a full test/paper


@router.post("/admin/save")
def save_reading(req: ReadingSaveRequest, _admin=Depends(require_admin)):
    """Save a reviewed passage + its questions."""
    if not req.title.strip() or not req.body.strip():
        raise HTTPException(status_code=400, detail="Title and passage body are required")
    if req.part not in ("A", "B", "C"):
        raise HTTPException(status_code=400, detail="Part must be A, B, or C")
    _validate_reading_questions(req.questions)

    supabase = get_supabase()
    passage = supabase.table("reading_passages").insert({
        "title": req.title,
        "part": req.part,
        "difficulty": req.difficulty,
        "body": req.body,
        "is_active": True,
        "test_id": req.test_id,
    }).execute().data[0]

    for q in req.questions:
        supabase.table("questions").insert({
            "module": "reading",
            "type": q.type,
            "content": q.content,
            "options": json.dumps(q.options) if q.options else None,
            "correct_answer": q.correct_answer or None,
            "passage_id": passage["id"],
        }).execute()

    return {"success": True, "passage_id": passage["id"], "questions_saved": len(req.questions)}


@router.post("/admin/passages/{passage_id}/images")
async def upload_passage_image(
    passage_id: int,
    image: UploadFile = File(...),
    _admin=Depends(require_admin),
):
    """Upload one figure/diagram image for a passage. Returns a public URL the admin
    drops into the passage body as markdown ![figure](url) -- rendered inline for
    students. Stored as body markdown, so no extra table/column is needed."""
    if _extract_rate_limiter.is_rate_limited("admin"):
        raise HTTPException(status_code=429, detail="Too many uploads — please slow down.")
    ext = IMAGE_CONTENT_TYPES.get(image.content_type)
    if not ext:
        raise HTTPException(status_code=400, detail="Use a PNG, JPG, WEBP or GIF image")
    contents = await image.read()
    if len(contents) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image must be under 5MB")

    supabase = get_supabase()
    existing = supabase.table("reading_passages").select("id").eq("id", passage_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Passage not found")

    path = f"passages/{passage_id}/{uuid.uuid4().hex}.{ext}"
    await run_sync(
        supabase.storage.from_(READING_IMAGE_BUCKET).upload,
        path, contents, {"content-type": image.content_type},
    )
    public = supabase.storage.from_(READING_IMAGE_BUCKET).get_public_url(path)
    # supabase-py has returned either a plain string or a dict across versions.
    url = public if isinstance(public, str) else (public.get("publicUrl") or public.get("publicURL") or "")
    if not url:
        raise HTTPException(status_code=502, detail="Upload succeeded but no public URL was returned")
    return {"url": url}


@router.get("/admin/passages")
def admin_list_passages(_admin=Depends(require_admin)):
    """All passages (active or not) for the admin management list, with the title
    of the test each belongs to (null if ungrouped)."""
    supabase = get_supabase()
    data = supabase.table("reading_passages").select(
        "id, title, part, difficulty, is_active, created_at, test_id"
    ).order("created_at", desc=True).execute()
    tests = supabase.table("reading_tests").select("id, title").execute()
    test_title = {t["id"]: t["title"] for t in tests.data}
    return [{**p, "test_title": test_title.get(p.get("test_id"))} for p in data.data]


# ── ADMIN: TESTS (a test = one full paper grouping many passages) ────

class ReadingTestCreate(BaseModel):
    title: str


@router.post("/admin/tests")
def create_test(req: ReadingTestCreate, _admin=Depends(require_admin)):
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="Test title is required")
    supabase = get_supabase()
    # Draft by default: a new test is empty, so it starts hidden. Admin previews it,
    # then flips it live once its passages are attached and reviewed.
    row = supabase.table("reading_tests").insert({"title": req.title.strip(), "is_active": False}).execute().data[0]
    return row


@router.get("/admin/tests")
def admin_list_tests(_admin=Depends(require_admin)):
    """All tests + a readiness summary per test: active-passage count, which parts
    (A/B/C) are present, total questions, and how many still lack a correct answer.
    Lets the admin flag incomplete tests in the list without expanding each one.
    Only ACTIVE passages count -- a hidden passage isn't part of what students get."""
    supabase = get_supabase()
    tests = supabase.table("reading_tests").select("id, title, is_active, created_at").order("created_at", desc=True).execute().data
    passages = supabase.table("reading_passages").select(
        "id, part, test_id, is_active"
    ).not_.is_("test_id", "null").execute().data
    active = [p for p in passages if p.get("is_active")]
    pid_to_test = {p["id"]: p["test_id"] for p in active}
    qrows = supabase.table("questions").select(
        "passage_id, correct_answer"
    ).in_("passage_id", list(pid_to_test.keys())).execute().data if pid_to_test else []

    summary: Dict[int, dict] = {
        t["id"]: {"passage_count": 0, "parts": set(), "question_count": 0, "missing_answers": 0}
        for t in tests
    }
    for p in active:
        s = summary.get(p["test_id"])
        if s is not None:
            s["passage_count"] += 1
            s["parts"].add(p["part"])
    for q in qrows:
        s = summary.get(pid_to_test.get(q["passage_id"]))
        if s is not None:
            s["question_count"] += 1
            if not (q.get("correct_answer") or "").strip():
                s["missing_answers"] += 1

    return [{
        **t,
        "passage_count": summary[t["id"]]["passage_count"],
        "parts": sorted(summary[t["id"]]["parts"]),
        "question_count": summary[t["id"]]["question_count"],
        "missing_answers": summary[t["id"]]["missing_answers"],
    } for t in tests]


@router.get("/admin/tests/{test_id}/detail")
def admin_test_detail(test_id: int, _admin=Depends(require_admin)):
    """Full contents of one test for the admin drill-down: its passages grouped by
    part (A->B->C), each with its questions (options + correct_answer) and a
    missing-answer count, so incomplete content shows without opening each passage.
    Includes hidden passages too (marked is_active=false) so they can be managed."""
    supabase = get_supabase()
    t = supabase.table("reading_tests").select("id, title, is_active").eq("id", test_id).execute()
    if not t.data:
        raise HTTPException(status_code=404, detail="Test not found")

    passages = supabase.table("reading_passages").select(
        "id, title, part, difficulty, is_active"
    ).eq("test_id", test_id).execute().data
    passages.sort(key=lambda p: (_PART_ORDER.get(p["part"], 9), p["id"]))

    pids = [p["id"] for p in passages]
    qrows = supabase.table("questions").select(
        "id, content, type, options, correct_answer, passage_id"
    ).in_("passage_id", pids).order("id").execute().data if pids else []
    q_by_passage: Dict[int, list] = {}
    for q in qrows:
        q_by_passage.setdefault(q["passage_id"], []).append(q)

    def _passage_out(p: dict) -> dict:
        qs = q_by_passage.get(p["id"], [])
        return {
            "id": p["id"],
            "title": p["title"],
            "part": p["part"],
            "difficulty": p["difficulty"],
            "is_active": p["is_active"],
            "question_count": len(qs),
            "missing_answers": sum(1 for q in qs if not (q.get("correct_answer") or "").strip()),
            "questions": [{
                "id": q["id"],
                "content": q["content"],
                "type": "short_answer" if q.get("type") == "short_answer" else "mcq",
                "options": json.loads(q["options"]) if q.get("options") else [],
                "correct_answer": q.get("correct_answer"),
            } for q in qs],
        }

    groups = [
        {"part": part, "passages": [_passage_out(p) for p in passages if p["part"] == part]}
        for part in ("A", "B", "C")
    ]
    groups = [g for g in groups if g["passages"]]
    return {"id": t.data[0]["id"], "title": t.data[0]["title"], "is_active": t.data[0]["is_active"], "groups": groups}


@router.get("/admin/tests/{test_id}/preview")
def admin_preview_test(test_id: int, _admin=Depends(require_admin)):
    """What students will see, but works BEFORE publishing: same payload as the
    student GET /tests/{id}, ignoring is_active on the test and its passages so an
    admin can review a test as a full session before making it live."""
    return _load_test_payload(test_id, include_inactive=True)


class SetActiveRequest(BaseModel):
    is_active: bool


@router.post("/admin/tests/{test_id}/active")
def set_test_active(test_id: int, req: SetActiveRequest, _admin=Depends(require_admin)):
    """Publish/unpublish a whole test. Unpublished tests vanish from the student list."""
    supabase = get_supabase()
    existing = supabase.table("reading_tests").select("id").eq("id", test_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Test not found")
    supabase.table("reading_tests").update({"is_active": req.is_active}).eq("id", test_id).execute()
    return {"success": True, "is_active": req.is_active}


@router.post("/admin/passages/{passage_id}/active")
def set_passage_active(passage_id: int, req: SetActiveRequest, _admin=Depends(require_admin)):
    """Publish/unpublish a single passage (hides it from students and from any test
    it belongs to) without deleting it."""
    supabase = get_supabase()
    existing = supabase.table("reading_passages").select("id").eq("id", passage_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Passage not found")
    supabase.table("reading_passages").update({"is_active": req.is_active}).eq("id", passage_id).execute()
    return {"success": True, "is_active": req.is_active}


@router.delete("/admin/passages/{passage_id}")
def delete_passage(passage_id: int, _admin=Depends(require_admin)):
    """Permanently delete a passage and its questions. Past submissions keep their
    stored feedback, but the deleted questions no longer resolve in the mistakes
    notebook -- expected when removing bad content. Prefer /active (hide) if unsure."""
    supabase = get_supabase()
    existing = supabase.table("reading_passages").select("id").eq("id", passage_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Passage not found")
    supabase.table("questions").delete().eq("passage_id", passage_id).execute()
    supabase.table("reading_passages").delete().eq("id", passage_id).execute()
    return {"success": True}


@router.delete("/admin/tests/{test_id}")
def delete_test(test_id: int, _admin=Depends(require_admin)):
    """Delete a test. Its passages are NOT deleted -- they detach (test_id -> null via
    the FK's ON DELETE SET NULL) and stay as standalone passages you can reuse or
    delete one by one."""
    supabase = get_supabase()
    existing = supabase.table("reading_tests").select("id").eq("id", test_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Test not found")
    supabase.table("reading_tests").delete().eq("id", test_id).execute()
    return {"success": True}


class AssignPassageRequest(BaseModel):
    test_id: Optional[int] = None  # null detaches the passage from any test


@router.post("/admin/passages/{passage_id}/assign")
def assign_passage_to_test(passage_id: int, req: AssignPassageRequest, _admin=Depends(require_admin)):
    """Attach an existing passage to a test (or detach with test_id=null). The
    quick way to group passages that were saved individually before tests existed."""
    supabase = get_supabase()
    existing = supabase.table("reading_passages").select("id").eq("id", passage_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Passage not found")
    if req.test_id is not None:
        t = supabase.table("reading_tests").select("id").eq("id", req.test_id).execute()
        if not t.data:
            raise HTTPException(status_code=404, detail="Test not found")
    supabase.table("reading_passages").update({"test_id": req.test_id}).eq("id", passage_id).execute()
    return {"success": True}


@router.get("/admin/passages/{passage_id}")
def admin_get_passage(passage_id: int, _admin=Depends(require_admin)):
    """Full passage detail for the admin editor -- unlike the student-facing
    /passages/{id}, this includes correct_answer and each question's DB id so
    blanks can be spotted and edits can target a specific row."""
    supabase = get_supabase()
    p = supabase.table("reading_passages").select(
        "id, title, part, difficulty, body"
    ).eq("id", passage_id).execute()
    if not p.data:
        raise HTTPException(status_code=404, detail="Passage not found")
    qs = supabase.table("questions").select(
        "id, content, type, options, correct_answer"
    ).eq("passage_id", passage_id).order("id").execute()
    questions = [{
        "id": q["id"],
        "content": q["content"],
        "type": "short_answer" if q.get("type") == "short_answer" else "mcq",
        "options": json.loads(q["options"]) if q.get("options") else [],
        "correct_answer": q.get("correct_answer"),
    } for q in qs.data]
    return {**p.data[0], "questions": questions}


class ReadingQuestionUpdateIn(ReadingQuestionIn):
    id: Optional[int] = None  # existing question id to update in place; omitted = new question


class ReadingPassageUpdateRequest(BaseModel):
    title: str
    part: str = "C"
    difficulty: str = "intermediate"
    body: str
    questions: List[ReadingQuestionUpdateIn]
    # Test assignment is NOT edited here -- it has its own endpoint
    # (POST /admin/passages/{id}/assign). This request never carries test_id, so
    # applying it here would silently detach the passage from its test on every
    # content save (frontend never sends it -> always None -> wipes the assignment).


@router.put("/admin/passages/{passage_id}")
def update_reading_passage(
    passage_id: int,
    req: ReadingPassageUpdateRequest,
    _admin=Depends(require_admin),
):
    """Edit an already-saved passage. Existing questions (with an id) are updated
    in place -- never deleted -- so past submissions/mistakes-notebook entries that
    reference their id by number keep resolving. New questions (no id) get inserted."""
    if not req.title.strip() or not req.body.strip():
        raise HTTPException(status_code=400, detail="Title and passage body are required")
    if req.part not in ("A", "B", "C"):
        raise HTTPException(status_code=400, detail="Part must be A, B, or C")
    _validate_reading_questions(req.questions)

    supabase = get_supabase()
    existing = supabase.table("reading_passages").select("id").eq("id", passage_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Passage not found")

    supabase.table("reading_passages").update({
        "title": req.title,
        "part": req.part,
        "difficulty": req.difficulty,
        "body": req.body,
    }).eq("id", passage_id).execute()

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
            # passage_id guard: a mismatched id can't be used to edit a question
            # belonging to a different passage.
            supabase.table("questions").update(payload).eq("id", q.id).eq("passage_id", passage_id).execute()
            updated += 1
        else:
            supabase.table("questions").insert({**payload, "module": "reading", "passage_id": passage_id}).execute()
            inserted += 1

    return {"success": True, "updated": updated, "inserted": inserted}


ATTACH_ANSWERS_PROMPT_TEMPLATE = """You are matching answers from an OET answer-key PDF to an \
already-known, ordered list of reading questions from ONE passage. The questions are given below \
in their original order — match them to the answer key by that same order and by question content, \
exactly as the key numbers them.

Questions (in order):
{questions_json}

For each question, find its answer in the attached answer-key PDF and return:
- For "mcq" questions: the correct option's own exact text, copied character-for-character from \
that question's "options" list above (never the answer key's own wording).
- For "short_answer" questions: the reference answer text from the key, as plain text.

Only include a question in your response if you can confidently find its answer in the key — skip \
(omit) any question you can't resolve rather than guessing.

Return ONLY this JSON, no other text:
{{"answers": [{{"questionId": 0, "correct_answer": "..."}}]}}"""


async def _attach_answers_from_pdf(questions: List[dict], answer_key_base64: str) -> Dict[int, str]:
    """One AI call: given a passage's already-saved questions and a separate answer-key
    PDF, return {questionId: correct_answer} for whichever questions it can resolve."""
    key = settings.OPENROUTER_API_KEY
    if not key:
        raise HTTPException(status_code=502, detail="AI provider not configured")

    questions_json = json.dumps([
        {"questionId": q["id"], "content": q["content"], "type": q["type"], "options": q["options"]}
        for q in questions
    ], indent=2)
    prompt = ATTACH_ANSWERS_PROMPT_TEMPLATE.format(questions_json=questions_json)

    payload = {
        "model": "google/gemini-2.5-flash",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "file", "file": {
                    "filename": "answer_key.pdf",
                    "file_data": f"data:application/pdf;base64,{answer_key_base64}",
                }},
            ],
        }],
        "plugins": [{"id": "file-parser", "pdf": {"engine": "mistral-ocr"}}],
        "temperature": 0.1,
        "max_tokens": 8000,
        "response_format": {"type": "json_object"},
    }

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
    except httpx.TimeoutException:
        logger.error("[attach answers] OpenRouter request timed out")
        raise HTTPException(status_code=504, detail="Matching timed out. Try again.")
    if resp.status_code != 200:
        logger.error("[attach answers] OpenRouter HTTP %s: %s", resp.status_code, resp.text[:300])
        raise HTTPException(status_code=502, detail="AI matching failed. Try again.")

    content = resp.json()["choices"][0]["message"]["content"]
    parsed = _try_parse_json("reading-attach-answers", content)
    if parsed is None:
        logger.warning("[attach answers] JSON parse failed, raw content head=%s", content[:1000])
        raise HTTPException(status_code=502, detail="AI returned an unreadable response. Try again.")

    return {a["questionId"]: a["correct_answer"] for a in parsed.get("answers", []) if a.get("correct_answer")}


@router.post("/admin/passages/{passage_id}/attach-answers")
async def attach_answers(
    passage_id: int,
    answer_key: UploadFile = File(...),
    _admin=Depends(require_admin),
):
    """Upload a clean answer-key PDF for ONE already-saved passage; AI matches it
    against that passage's existing questions (by order + content) and fills in
    correct_answer. Skips any question it can't confidently resolve -- those stay
    blank for manual review or a retry."""
    if _extract_rate_limiter.is_rate_limited("admin"):
        raise HTTPException(status_code=429, detail="Too many requests — please slow down.")
    if answer_key.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status_code=400, detail="Answer key must be a PDF")

    contents = await answer_key.read()
    if len(contents) > MAX_PDF_BYTES:
        raise HTTPException(status_code=400, detail="Answer key PDF must be under 10MB")

    supabase = get_supabase()
    qs = supabase.table("questions").select(
        "id, content, type, options"
    ).eq("passage_id", passage_id).order("id").execute()
    if not qs.data:
        raise HTTPException(status_code=404, detail="Passage not found or has no questions")
    questions = [{
        "id": q["id"],
        "content": q["content"],
        "type": "short_answer" if q.get("type") == "short_answer" else "mcq",
        "options": json.loads(q["options"]) if q.get("options") else [],
    } for q in qs.data]

    import base64
    answer_key_base64 = base64.b64encode(contents).decode("utf-8")
    answers_by_qid = await _attach_answers_from_pdf(questions, answer_key_base64)

    questions_by_id = {q["id"]: q for q in questions}
    matched = 0
    for qid, answer in answers_by_qid.items():
        q = questions_by_id.get(qid)
        if not q:
            continue  # model returned an id that isn't actually in this passage
        if q["type"] == "mcq" and answer not in q["options"]:
            continue  # doesn't match an option exactly -- skip rather than save a bad answer
        supabase.table("questions").update({"correct_answer": answer}).eq("id", qid).execute()
        matched += 1

    return {"matched": matched, "total": len(questions)}


@router.post("/admin/tests/{test_id}/attach-answers")
async def attach_test_answers(
    test_id: int,
    answer_key: UploadFile = File(...),
    _admin=Depends(require_admin),
):
    """Upload ONE answer-key PDF for a whole test: AI matches it against every question
    in every passage of the test (Part A -> B -> C, in paper order) and fills in
    correct_answer across the lot -- so a full paper's answers go in with one upload
    instead of per passage. Same safety as the single-passage attach: an MCQ answer
    that doesn't exactly match an option is skipped rather than saved wrong."""
    if _extract_rate_limiter.is_rate_limited("admin"):
        raise HTTPException(status_code=429, detail="Too many requests — please slow down.")
    if answer_key.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status_code=400, detail="Answer key must be a PDF")

    contents = await answer_key.read()
    if len(contents) > MAX_PDF_BYTES:
        raise HTTPException(status_code=400, detail="Answer key PDF must be under 10MB")

    supabase = get_supabase()
    t = supabase.table("reading_tests").select("id").eq("id", test_id).execute()
    if not t.data:
        raise HTTPException(status_code=404, detail="Test not found")

    passages = supabase.table("reading_passages").select("id, part").eq("test_id", test_id).execute().data
    part_by_pid = {p["id"]: p["part"] for p in passages}
    pids = list(part_by_pid.keys())
    if not pids:
        raise HTTPException(status_code=404, detail="Test has no passages")

    qrows = supabase.table("questions").select(
        "id, content, type, options, passage_id"
    ).in_("passage_id", pids).execute().data
    if not qrows:
        raise HTTPException(status_code=404, detail="Test has no questions")

    # Order questions the way the paper (and its key) run: Part A -> B -> C, then by
    # passage, then by question -- gives the matcher the same sequence as the key.
    qrows.sort(key=lambda q: (_PART_ORDER.get(part_by_pid.get(q["passage_id"]), 9), q["passage_id"], q["id"]))
    questions = [{
        "id": q["id"],
        "content": q["content"],
        "type": "short_answer" if q.get("type") == "short_answer" else "mcq",
        "options": json.loads(q["options"]) if q.get("options") else [],
    } for q in qrows]

    import base64
    answer_key_base64 = base64.b64encode(contents).decode("utf-8")
    answers_by_qid = await _attach_answers_from_pdf(questions, answer_key_base64)

    questions_by_id = {q["id"]: q for q in questions}
    matched = 0
    for qid, answer in answers_by_qid.items():
        q = questions_by_id.get(qid)
        if not q:
            continue
        if q["type"] == "mcq" and answer not in q["options"]:
            continue
        supabase.table("questions").update({"correct_answer": answer}).eq("id", qid).execute()
        matched += 1

    return {"matched": matched, "total": len(questions)}
