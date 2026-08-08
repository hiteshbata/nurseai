from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from app.core.supabase import get_supabase
from app.core.threading import run_sync
from app.core.rate_limit import SlidingWindowRateLimiter
from app.routers.auth import get_current_user, get_user_supabase, UserInfo
from supabase import Client
from app.routers.admin import require_admin
from app.routers.mock import has_mock_section_access
from app.core.feature_flags import require_feature
from app.services.ai_scoring import score_writing, _call_ai, WRITING_CRITERIA_MAX
from app.services.plan_gating import has_writing_access, get_plan_from_profile
from app.services.skill_graph import record_skill_observations, get_weakness
from app.services.observation_service import validate_and_normalize
from app.services.coaching_messages import RECOMMENDATION_REASON, ACTIONABLE_IMPROVEMENT, CONFIDENCE_MESSAGE
from app.core.redis_client import get_redis
import asyncio
import base64
import hashlib
import json
import logging
import secrets
import time

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/writing", tags=["writing"], dependencies=[Depends(require_feature("writing_practice"))])

SUBMIT_RATE_LIMIT_MAX_CALLS = 20
SUBMIT_RATE_LIMIT_WINDOW_SECONDS = 600
_submit_rate_limiter = SlidingWindowRateLimiter(SUBMIT_RATE_LIMIT_MAX_CALLS, SUBMIT_RATE_LIMIT_WINDOW_SECONDS, name="writing:submit")

SUBMIT_IMAGE_RATE_LIMIT_MAX_CALLS = 10
SUBMIT_IMAGE_RATE_LIMIT_WINDOW_SECONDS = 600
_submit_image_rate_limiter = SlidingWindowRateLimiter(SUBMIT_IMAGE_RATE_LIMIT_MAX_CALLS, SUBMIT_IMAGE_RATE_LIMIT_WINDOW_SECONDS, name="writing:submit_image")

_extract_rate_limiter = SlidingWindowRateLimiter(30, 600, name="writing:extract")

MAX_IMAGE_BYTES = 5 * 1024 * 1024
# base64 inflates size ~4/3; reject oversized payloads before spending CPU on decode.
MAX_IMAGE_BASE64_CHARS = MAX_IMAGE_BYTES * 4 // 3 + 4

MAX_PDF_BYTES = 10 * 1024 * 1024

WRITING_PLAN_GATE_ENABLED = True

# A typed OET letter runs a few hundred words -- 20k chars is generous
# headroom while still bounding worst-case prompt-token cost.
MAX_WRITING_CONTENT_CHARS = 20_000

# Learner-facing labels for the six OET Writing criteria -- same copy as
# WRITING_CRITERIA in frontend/app/components/SessionFeedback.tsx, so the
# insights card names a criterion the same way the score breakdown above it does.
WRITING_SKILL_LABELS = {
    "purpose": "Purpose",
    "content": "Content",
    "conciseness": "Conciseness & Clarity",
    "genre_style": "Genre & Style",
    "organization": "Organisation & Layout",
    "language": "Language",
}


def _writing_skill_label(tag: str) -> str:
    criterion = tag.rsplit(":", 1)[-1]
    return WRITING_SKILL_LABELS.get(criterion, criterion.replace("_", " ").title())


def normalize_writing_score(raw_score: float, max_score: int) -> float:
    """Rescale a writing criterion's raw score (0-3 for purpose, 0-7 for the
    other five -- see WRITING_CRITERIA_MAX) onto the shared 0-6 OET band scale
    ObservationService expects. Scaling by ratio preserves each criterion's
    percentile-of-max standing, so a criterion at e.g. 90% of its own max lands
    at the same ~5.4 band a native 0-6 Speaking/Reading/Listening criterion
    would -- keeping EMA blending and weakness-ranking comparable across
    modules. Local to Writing only; ObservationService and score_writing's
    rubric are unchanged."""
    if max_score <= 0:
        return 0.0
    return round((raw_score / max_score) * 6, 2)


class WritingSubmitRequest(BaseModel):
    scenario_id: int
    content: str = Field(max_length=MAX_WRITING_CONTENT_CHARS)


class WritingOcrRequest(BaseModel):
    # One base64 JPEG/PNG per page — a handwritten letter can run onto a 2nd page.
    images: List[str]


MAX_OCR_PAGES = 3


async def _require_writing_plan(supabase, user_id: str, scenario_id: Optional[int] = None) -> str:
    """Plan-gate writing access (Pro/Elite). Shared by scenario submit and OCR.

    An anonymous or free-plan free-trial mock student is also let through when
    `scenario_id` is the exact Writing scenario their own active mock is
    currently on -- see has_mock_section_access in mock.py. That path never
    scores the letter (see submit_writing's mock branch); it only lets the
    student write the answer and save it. Callers that don't pass
    scenario_id (OCR, phone handoff) never grant this bypass."""
    if not WRITING_PLAN_GATE_ENABLED:
        return ""  # gate temporarily off (see WRITING_PLAN_GATE_ENABLED)
    profile = await run_sync(
        supabase.table("user_profiles").select("plan, plan_expires_at").eq("user_id", user_id).execute
    )
    plan = get_plan_from_profile(profile.data[0] if profile.data else {})
    if has_writing_access(plan):
        return plan
    if scenario_id is not None and has_mock_section_access(supabase, user_id, "writing", scenario_id):
        return plan
    raise HTTPException(
        status_code=403,
        detail={
            "error": "Writing practice requires Pro or Elite plan",
            "upgrade_required": True,
            "current_plan": plan,
        },
    )


async def _require_writing_scenario(supabase, user_id: str, scenario_id: int) -> tuple[dict, str]:
    """Plan-gate writing access and fetch the scenario. Shared by the submit path."""
    plan = await _require_writing_plan(supabase, user_id, scenario_id)
    scenario_data = await run_sync(
        supabase.table("scenarios").select("id, title, setting, nurse_card").eq("id", scenario_id).execute
    )
    if not scenario_data.data:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return scenario_data.data[0], plan


async def _score_and_save(supabase, user_db, user_id: str, scenario_id: int, content: str, nurse_card: dict, scenario_title: str, case_notes: str = "") -> tuple[dict, Dict[str, float]]:
    """Score writing content and persist the submission. Used by /submit (typed, or
    text confirmed after photo OCR). Returns (feedback, normalized_criterion_scores) --
    the latter for the caller to build insights from without re-deriving it."""
    feedback = await score_writing(
        content=content,
        nurse_card=nurse_card,
        scenario_title=scenario_title,
        case_notes=case_notes,
        supabase=supabase,
    )

    if feedback.get("provider_failure"):
        raise HTTPException(
            status_code=503,
            detail="Scoring is temporarily unavailable. Please try again in a few minutes.",
        )

    await run_sync(
        user_db.table("submissions").insert({
            "user_id": user_id,
            "scenario_id": scenario_id,
            "module": "writing",
            "answer": content,
            "score": feedback.get("overall_score") or 0,
            "feedback": json.dumps(feedback),
        }).execute
    )

    raw_criterion_scores = {
        f"writing:{criterion}": normalize_writing_score(data["score"], WRITING_CRITERIA_MAX[criterion])
        for criterion, data in feedback.get("scores", {}).items()
        if isinstance(data, dict) and isinstance(data.get("score"), (int, float)) and criterion in WRITING_CRITERIA_MAX
    }
    criterion_scores = validate_and_normalize("writing", raw_criterion_scores)
    await record_skill_observations(user_id, criterion_scores)

    return feedback, criterion_scores


@router.get("/scenarios")
def list_scenarios(current_user: UserInfo = Depends(get_current_user)):
    """List all active writing scenarios."""
    supabase = get_supabase()
    data = supabase.table("scenarios").select(
        "id, title, setting, difficulty, nurse_card"
    ).eq("module", "writing").eq("is_active", True).execute()
    return data.data


@router.get("/weakness")
async def writing_weakness(
    current_user: UserInfo = Depends(get_current_user),
    user_db: Client = Depends(get_user_supabase),
):
    """The student's weakest writing criteria (organization, language, ...),
    weakest first. See skill_graph.get_weakness."""
    return await get_weakness(user_db, current_user.id, "writing:")


@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: int, current_user: UserInfo = Depends(get_current_user)):
    """Get a writing scenario with nurse card (scoring rubric NOT sent to student)."""
    supabase = get_supabase()
    data = supabase.table("scenarios").select(
        "id, title, setting, difficulty, nurse_card"
    ).eq("id", scenario_id).eq("is_active", True).execute()
    if not data.data:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return data.data[0]


# A double-click or client retry resubmitting the exact same letter for the
# same scenario within this window is almost certainly a duplicate, not a
# genuine second attempt -- blocks it from scoring (and skill-graph-recording)
# twice. Redis-backed with a per-process fallback, same shape as
# auth.py's _role_recently_upserted.
SUBMIT_DEDUP_WINDOW_SECONDS = 60
_recent_submit_keys: dict[str, float] = {}


def _is_duplicate_submit(user_id: str, scenario_id: int, content: str) -> bool:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    key = f"writing_submit_dedup:{user_id}:{scenario_id}:{digest}"
    client = get_redis()
    if client is not None:
        return not client.set(key, "1", nx=True, ex=SUBMIT_DEDUP_WINDOW_SECONDS)
    now = time.time()
    expired_keys = [k for k, ts in _recent_submit_keys.items() if now - ts > SUBMIT_DEDUP_WINDOW_SECONDS]
    for k in expired_keys:
        del _recent_submit_keys[k]
    if key in _recent_submit_keys:
        return True
    _recent_submit_keys[key] = now
    return False


def _recommend_writing_scenarios(current_user: UserInfo, user_db: Client, limit: int) -> list:
    """Shared ranking, same algorithm as speaking._recommend_scenarios: unattempted
    scenarios first (shuffled, so repeat visits don't always see the same one), then
    the user's lowest-scored attempted scenarios, weakest first."""
    import random

    supabase = get_supabase()
    all_scenarios = supabase.table("scenarios").select(
        "id, title, setting, difficulty, nurse_card"
    ).eq("module", "writing").eq("is_active", True).execute()
    if not all_scenarios.data:
        raise HTTPException(status_code=404, detail="No scenarios available")

    feedback_data = user_db.table("submissions").select(
        "scenario_id, score"
    ).eq("user_id", current_user.id).eq("module", "writing").execute()
    avg_scores: Dict[int, list] = {}
    for s in feedback_data.data:
        qid = s.get("scenario_id")
        if qid:
            avg_scores.setdefault(qid, []).append(s.get("score", 0))

    unattempted = [s for s in all_scenarios.data if s["id"] not in avg_scores]
    random.shuffle(unattempted)
    weakest_first = sorted(avg_scores.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
    scenarios_by_id = {s["id"]: s for s in all_scenarios.data}

    recs = []
    seen_ids = set()

    for s in unattempted:
        if len(recs) >= limit:
            break
        recs.append({
            "scenario_id": s["id"], "title": s["title"], "setting": s["setting"],
            "difficulty": s["difficulty"], "reason": "New - you haven't tried this scenario yet",
        })
        seen_ids.add(s["id"])

    for qid, scores in weakest_first:
        if len(recs) >= limit:
            break
        if qid in seen_ids:
            continue
        pick = scenarios_by_id.get(qid)
        if not pick:
            continue
        avg = sum(scores) / len(scores)
        recs.append({
            "scenario_id": pick["id"], "title": pick["title"], "setting": pick["setting"],
            "difficulty": pick["difficulty"],
            "reason": f"Needs practice - your average score for this scenario is {avg:.1f}/6",
        })
        seen_ids.add(qid)

    if not recs:
        for s in random.sample(all_scenarios.data, min(limit, len(all_scenarios.data))):
            recs.append({
                "scenario_id": s["id"], "title": s["title"], "setting": s["setting"],
                "difficulty": s["difficulty"], "reason": "Try this scenario",
            })

    return recs


async def _build_writing_insights(
    criterion_scores: Dict[str, float],
    current_user: UserInfo,
    user_db: Client,
) -> Optional[dict]:
    """Rule-based V1 recommendation, same shape/control-flow as
    reading._build_reading_insights and speaking._build_speaking_insights
    (Sprint 4, ported locally per the same not-yet-shared-service note as
    those two). criterion_scores are already writing:<criterion> tags on the
    shared 0-6 band (see normalize_writing_score), so get_weakness and the
    coaching templates need no writing-specific handling.

    Best-effort like record_skill_observations: the submission is already
    scored and saved by the time this runs, so a weakness-history or
    recommendation query blipping must not turn an already-successful score
    into a 500."""
    if not criterion_scores:
        return None
    try:
        strongest_tag, strongest_score = max(criterion_scores.items(), key=lambda kv: kv[1])
        strongest_label = _writing_skill_label(strongest_tag)

        history = await get_weakness(user_db, current_user.id, "writing:", _writing_skill_label)
        if history:
            weakest = history[0]
            weakest_tag = f"writing:{weakest['skill']}"
            weakest_label = weakest["label"]
            weakest_score = weakest["band"]
            basis = "history"
            template_args = {"label": weakest_label, "attempts": weakest["attempts"]}
        else:
            weakest_tag, weakest_score = min(criterion_scores.items(), key=lambda kv: kv[1])
            weakest_label = _writing_skill_label(weakest_tag)
            basis = "session"
            template_args = {"label": weakest_label, "attempts": 1}

        next_best_action = None
        try:
            recs = await run_sync(_recommend_writing_scenarios, current_user, user_db, 1)
            if recs:
                next_best_action = recs[0]
        except HTTPException:
            pass  # no scenarios available -- insights still useful without a pick

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
        logger.warning("[WRITING_INSIGHTS_FAILED] user_id=%s error=%s", current_user.id, str(e)[:300])
        return None


@router.post("/submit")
async def submit_writing(
    request: WritingSubmitRequest,
    current_user: UserInfo = Depends(get_current_user),
    user_db: Client = Depends(get_user_supabase),
):
    """Submit a typed writing response for scoring."""
    if _submit_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many submissions — please slow down.")
    if _is_duplicate_submit(current_user.id, request.scenario_id, request.content):
        raise HTTPException(status_code=409, detail="This submission is already being scored — please wait.")

    supabase = get_supabase()
    scenario, plan = await _require_writing_scenario(supabase, current_user.id, request.scenario_id)

    # Free-tier mock test: Writing is reachable (see _require_writing_plan's mock
    # bypass) but not scored -- that's the paywall. Save the letter as-is, skip
    # the AI scoring call entirely (it's the expensive OCR/AI step this tier is
    # meant to avoid), and tell the student to upgrade to see feedback.
    if plan == "free" and has_mock_section_access(supabase, current_user.id, "writing", request.scenario_id):
        await run_sync(
            user_db.table("submissions").insert({
                "user_id": current_user.id,
                "scenario_id": request.scenario_id,
                "module": "writing",
                "answer": request.content,
                "score": 0,
                "feedback": json.dumps({"locked": True, "upgrade_required": True}),
            }).execute
        )
        return {
            "success": True,
            "locked": True,
            "upgrade_required": True,
            "message": "Upgrade to Pro or Elite to see your Writing score and feedback.",
        }

    feedback, criterion_scores = await _score_and_save(
        supabase, user_db, current_user.id, request.scenario_id,
        request.content, scenario.get("nurse_card", {}), scenario.get("title", ""),
        case_notes=scenario.get("setting", ""),
    )
    insights = await _build_writing_insights(criterion_scores, current_user, user_db)

    return {"success": True, "feedback": feedback, "insights": insights}


async def _read_ocr_page(idx: int, img_b64: str) -> str:
    """OCR one page via the "writing_ocr" purpose (Admin > AI Models controls
    the primary/fallback model pair). Raises HTTPException(502) naming the
    page if both fail, so the caller surfaces which photo to re-take."""
    result = await _call_ai(
        [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Read this handwritten nursing letter. Extract and return ONLY the text content, exactly as written. Preserve line breaks and paragraphs. Do not correct spelling or grammar."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
            ],
        }],
        purpose="writing_ocr",
        max_tokens=1500,
        # 30s (not _call_ai's 60s default): a hung provider fails fast to the
        # fallback model instead of eating a full minute before it's tried.
        timeout=30.0,
    )
    if result.get("provider_failure"):
        raise HTTPException(status_code=502, detail=f"Could not read page {idx + 1}. Try a clearer, well-lit photo.")
    return result.get("raw_feedback", "").strip()


async def _ocr_images(images: List[str]) -> str:
    """OCR each page image (base64) and return the combined text. OCR only —
    the student reviews/edits the result before it is scored, so a misread
    never silently costs them Language/spelling marks.

    Pages are read concurrently (gather preserves order), so wall-time is one
    page, not the sum -- a slow/hung provider on page 1 no longer stacks on
    top of pages 2-3."""
    pages = await asyncio.gather(*(
        _read_ocr_page(idx, img_b64) for idx, img_b64 in enumerate(images)
    ))
    return "\n\n".join(pages)


@router.post("/ocr")
async def ocr_writing_images(
    request: WritingOcrRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """Read one or more photos of a handwritten letter and return the combined
    text for the student to review and edit before submitting for scoring."""
    if _submit_image_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many photo reads — please slow down.")

    if not request.images:
        raise HTTPException(status_code=400, detail="No photo provided")
    if len(request.images) > MAX_OCR_PAGES:
        raise HTTPException(status_code=400, detail=f"Up to {MAX_OCR_PAGES} photos per letter")

    for img_b64 in request.images:
        if len(img_b64) > MAX_IMAGE_BASE64_CHARS:
            raise HTTPException(status_code=400, detail="Each photo must be under 5MB")
        try:
            decoded = base64.b64decode(img_b64, validate=True)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid image data")
        if len(decoded) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=400, detail="Each photo must be under 5MB")

    supabase = get_supabase()
    await _require_writing_plan(supabase, current_user.id)

    text = await _ocr_images(request.images)
    return {"success": True, "text": text}


# ── PHONE HANDOFF (scan QR on laptop, upload photos from phone) ───────
# The student practices on a laptop but their letter is on their phone. The
# laptop creates a short-lived session, shows a QR; the phone opens it, uploads
# photos, we OCR them, and the laptop polls for the resulting text. Only the
# small OCR'd text is stored (keyed by an unguessable token) -- never the image
# bytes. Redis in prod so it works across workers; an in-process dict falls back
# for single-worker local dev.

_PHONE_SESSION_TTL = 900  # 15 minutes
_phone_sessions_fallback: Dict[str, Dict[str, Any]] = {}


def _phone_store_set(token: str, data: Dict[str, Any]) -> None:
    client = get_redis()
    if client:
        client.setex(f"wr_upload:{token}", _PHONE_SESSION_TTL, json.dumps(data))
    else:
        _phone_sessions_fallback[token] = {**data, "_exp": time.time() + _PHONE_SESSION_TTL}


def _phone_store_get(token: str) -> Optional[Dict[str, Any]]:
    client = get_redis()
    if client:
        raw = client.get(f"wr_upload:{token}")
        return json.loads(raw) if raw else None
    entry = _phone_sessions_fallback.get(token)
    if not entry:
        return None
    if entry.get("_exp", 0) < time.time():
        _phone_sessions_fallback.pop(token, None)
        return None
    return {k: v for k, v in entry.items() if k != "_exp"}


@router.post("/phone-session")
async def create_phone_session(current_user: UserInfo = Depends(get_current_user)):
    """Laptop: start a phone-upload session. Returns a token the laptop turns into
    a QR code / link for the phone to open."""
    supabase = get_supabase()
    await _require_writing_plan(supabase, current_user.id)
    token = secrets.token_urlsafe(24)
    _phone_store_set(token, {"user_id": current_user.id, "status": "waiting", "text": ""})
    return {"token": token}


@router.get("/phone-session/{token}")
async def poll_phone_session(token: str, current_user: UserInfo = Depends(get_current_user)):
    """Laptop: poll for the text the phone uploaded."""
    entry = _phone_store_get(token)
    if not entry:
        return {"status": "expired", "text": ""}
    if entry.get("user_id") != current_user.id:
        raise HTTPException(status_code=403, detail="Not your upload session")
    return {"status": entry.get("status", "waiting"), "text": entry.get("text", "")}


@router.post("/phone-upload/{token}")
async def phone_upload(token: str, request: WritingOcrRequest):
    """Phone: upload photos for an existing session (the token is the capability —
    no login needed on the phone). We OCR and store only the text for the laptop."""
    if _submit_image_rate_limiter.is_rate_limited(f"phone:{token}"):
        raise HTTPException(status_code=429, detail="Too many uploads — please slow down.")

    entry = _phone_store_get(token)
    if not entry:
        raise HTTPException(status_code=404, detail="This link has expired. Start again on your computer.")

    if not request.images:
        raise HTTPException(status_code=400, detail="No photo provided")
    if len(request.images) > MAX_OCR_PAGES:
        raise HTTPException(status_code=400, detail=f"Up to {MAX_OCR_PAGES} photos per letter")
    for img_b64 in request.images:
        if len(img_b64) > MAX_IMAGE_BASE64_CHARS:
            raise HTTPException(status_code=400, detail="Each photo must be under 5MB")
        try:
            decoded = base64.b64decode(img_b64, validate=True)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid image data")
        if len(decoded) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=400, detail="Each photo must be under 5MB")

    text = await _ocr_images(request.images)
    _phone_store_set(token, {**entry, "status": "done", "text": text})
    return {"success": True}


# ── ADMIN: PDF EXTRACTION ────────────────────────────────────────────
# Turn a real OET Writing task PDF into an editable scenario draft. Mirrors the
# reading module's extract->review->save pattern; nothing is saved here — the
# admin reviews the draft and POSTs it to /admin/scenarios.

WRITING_EXTRACT_PROMPT = """You are an OET Writing content specialist. The attached PDF is a real OET Writing sub-test task (case notes + a writing task). Extract exactly what is written — do NOT invent, paraphrase or expand content.

Return ONLY this JSON:
{
  "title": "<short scenario title, e.g. 'Discharge Letter - Pneumonia to Community Nurse'>",
  "difficulty": "<easy | medium | hard>",
  "case_notes": "<the FULL case notes exactly as written, preserving every section label (Patient details, Past medical history, Social background, Medical progress, Nursing management, Discharge plan, etc.) and line structure. Keep the original note form and abbreviations — students read this as the source material. Use plain text with newlines between sections.>",
  "task": "<the writing task instruction in full: the recipient (name, role, address) and what letter to write, ending with the word-count guidance, e.g. '...The body of the letter should be approximately 180-200 words.'>",
  "key_points": ["<5 concise key points the letter must cover to continue care, derived from the case notes' management/discharge plan and task — used for scoring, not shown to the student>"]
}

If the PDF is not an OET Writing task, return {"error": "No OET writing task found in this PDF"}."""


async def _extract_writing_from_pdf(pdf_base64: str) -> Dict[str, Any]:
    """Send the PDF to the "writing_content_extraction" purpose (mistral-ocr
    file-parser reads it as rendered pages — real OET PDFs are watermark-
    stamped and the raw text engine choked on them) and get back a
    structured, editable scenario draft."""
    result = await _call_ai(
        [{"role": "user", "content": [
            {"type": "text", "text": WRITING_EXTRACT_PROMPT},
            {"type": "file", "file": {
                "filename": "writing.pdf",
                "file_data": f"data:application/pdf;base64,{pdf_base64}",
            }},
        ]}],
        purpose="writing_content_extraction",
        max_tokens=8000,
        json_mode=True,
        temperature=0.2,
        extra_payload={"plugins": [{"id": "file-parser", "pdf": {"engine": "mistral-ocr"}}]},
        timeout=180.0,
    )
    if result.get("provider_failure"):
        raise HTTPException(status_code=502, detail="AI extraction failed. Try again.")
    if "raw_feedback" in result:
        logger.warning("[writing extract] JSON parse failed, raw head=%s", result["raw_feedback"][:1000])
        raise HTTPException(status_code=502, detail="Could not read that PDF. Try a clearer scan or a different file.")
    if result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@router.post("/admin/extract")
async def extract_writing(file: UploadFile = File(...), _admin=Depends(require_admin)):
    """Upload an OET Writing task PDF, return an editable scenario draft (title,
    difficulty, case notes, task, key points). Admin reviews then POSTs /admin/scenarios."""
    if _extract_rate_limiter.is_rate_limited("admin"):
        raise HTTPException(status_code=429, detail="Too many extractions — please slow down.")
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    contents = await file.read()
    if len(contents) > MAX_PDF_BYTES:
        raise HTTPException(status_code=400, detail="PDF must be under 10MB")

    pdf_base64 = base64.b64encode(contents).decode("utf-8")
    return await _extract_writing_from_pdf(pdf_base64)
