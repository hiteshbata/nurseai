"""Learner-facing Technique Practice API: catalog, lesson detail, and
practice submission on top of the Phase B foundation (techniques /
micro_practices / practice_attempts tables, technique_grading.py,
technique_progress.py -- see those modules for the grading/progress
contracts this router is a thin HTTP surface over).

Free for every authenticated user, not plan-gated. This is the on-ramp that
teaches beginners the skills needed for paid Reading/Listening/Writing/Mock
Test practice -- gating the on-ramp itself would work against its own
purpose (approved product decision, 2026-08-11)."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from supabase import Client

from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.supabase import get_supabase
from app.core.threading import run_sync
from app.routers.auth import get_current_user, get_user_supabase, UserInfo
from app.services import technique_grading, technique_progress

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/techniques", tags=["techniques"])

_attempt_rate_limiter = SlidingWindowRateLimiter(30, 600, name="techniques:attempt")

_CATALOG_FIELDS = ("id", "module", "slug", "name", "description", "learning_objective", "difficulty", "estimated_minutes")
_DETAIL_FIELDS = _CATALOG_FIELDS + ("lesson_content",)
_PRACTICE_FIELDS = "id, title, instructions, content, scoring_type, difficulty, stage"


def _mastery_by_tag(user_db: Client, user_id: str, tags: List[str]) -> Dict[str, dict]:
    """One query for every technique's mastery at once, keyed by skill_tag --
    same user_skill_stats table skill_graph.get_weakness already reads."""
    if not tags:
        return {}
    rows = user_db.table("user_skill_stats").select("skill_tag, attempts, ema_score").eq(
        "user_id", user_id
    ).in_("skill_tag", tags).execute().data
    return {r["skill_tag"]: r for r in rows}


def _mastery_payload(row: Optional[dict]) -> dict:
    attempts = row["attempts"] if row else 0
    band = float(row["ema_score"]) if row else None
    return {
        "level": technique_progress.mastery_level(attempts, band),
        "attempts": attempts,
        "band": band,
    }


@router.get("")
def list_techniques(
    current_user: UserInfo = Depends(get_current_user),
    user_db: Client = Depends(get_user_supabase),
):
    """Full catalog (all 4 modules) -- frontend groups by module client-side,
    same as /reading/passages staying flat. Every authenticated user sees
    every technique; not plan-gated (see module docstring)."""
    supabase = get_supabase()
    rows = supabase.table("techniques").select(
        ", ".join(("skill_tag",) + _CATALOG_FIELDS)
    ).eq("active", True).order("module").order("sort_order").execute().data

    tags = [technique_progress.technique_skill_tag(r["skill_tag"]) for r in rows]
    mastery_rows = _mastery_by_tag(user_db, current_user.id, tags)

    return [{
        **{k: r[k] for k in _CATALOG_FIELDS},
        "mastery": _mastery_payload(mastery_rows.get(technique_progress.technique_skill_tag(r["skill_tag"]))),
    } for r in rows]


@router.get("/{slug}")
def get_technique(
    slug: str,
    current_user: UserInfo = Depends(get_current_user),
    user_db: Client = Depends(get_user_supabase),
):
    """Lesson content + the available practice exercises if any have been
    seeded yet (expected_response withheld). Not every technique has a
    micro-practice seeded yet -- `practices` is [] and `practice` is null in
    that case; the frontend shows a "practice coming soon" state rather than
    erroring.

    A technique can have several practices at different stage/difficulty
    (Phase D) -- `practices` lists all of them in progression order
    (sort_order), and `practice` is the one recommended next, picked off the
    learner's own mastery bucket via technique_progress.recommended_stage.
    `practice` keeps the exact shape it had pre-Phase D so a frontend that
    hasn't picked up `practices` yet keeps working unchanged."""
    supabase = get_supabase()
    t = supabase.table("techniques").select(
        ", ".join(("skill_tag",) + _DETAIL_FIELDS)
    ).eq("slug", slug).eq("active", True).execute()
    if not t.data:
        raise HTTPException(status_code=404, detail="Technique not found")
    technique = t.data[0]

    mp = supabase.table("micro_practices").select(_PRACTICE_FIELDS).eq(
        "technique_id", technique["id"]
    ).eq("active", True).order("sort_order").order("id").execute()
    practices = mp.data

    tag = technique_progress.technique_skill_tag(technique["skill_tag"])
    mastery_row = _mastery_by_tag(user_db, current_user.id, [tag]).get(tag)

    stage = technique_progress.recommended_stage(
        mastery_row["attempts"] if mastery_row else 0,
        float(mastery_row["ema_score"]) if mastery_row else None,
    )
    practice = next((p for p in practices if p["stage"] == stage), practices[0] if practices else None)

    return {
        **{k: technique[k] for k in _DETAIL_FIELDS},
        "practice": practice,
        "practices": practices,
        "mastery": _mastery_payload(mastery_row),
    }


class TechniqueAttemptRequest(BaseModel):
    micro_practice_id: int
    answer: Any = None
    started_at: Optional[datetime] = None


@router.post("/{slug}/attempts")
async def submit_technique_attempt(
    slug: str,
    request: TechniqueAttemptRequest,
    current_user: UserInfo = Depends(get_current_user),
    user_db: Client = Depends(get_user_supabase),
):
    """Grade one micro-practice submission and record it. user_id always
    comes from the authenticated caller, never the request body, and the
    attempt insert goes through the RLS-scoped client (own-row policy) --
    a learner can never submit into another user's history, at the API
    layer or the database layer."""
    if _attempt_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many submissions — please slow down.")

    supabase = get_supabase()
    t = await run_sync(
        supabase.table("techniques").select("id, skill_tag").eq("slug", slug).eq("active", True).execute
    )
    if not t.data:
        raise HTTPException(status_code=404, detail="Technique not found")
    technique = t.data[0]

    mp = await run_sync(
        supabase.table("micro_practices").select(
            "id, instructions, content, expected_response, scoring_type"
        ).eq("id", request.micro_practice_id).eq("technique_id", technique["id"]).eq("active", True).execute
    )
    if not mp.data:
        raise HTTPException(status_code=404, detail="Practice exercise not found")
    micro_practice = mp.data[0]

    try:
        graded = await technique_grading.grade_micro_practice(
            micro_practice, {"answer": request.answer}, user_id=current_user.id,
        )
    except technique_grading.InvalidScoringType:
        logger.error(
            "[TECHNIQUE_ATTEMPT] technique_id=%s micro_practice_id=%s has an invalid scoring_type",
            technique["id"], micro_practice["id"],
        )
        raise HTTPException(status_code=503, detail="This practice exercise is temporarily unavailable.")

    await run_sync(
        user_db.table("practice_attempts").insert({
            "user_id": current_user.id,
            "technique_id": technique["id"],
            "micro_practice_id": micro_practice["id"],
            "response": {"answer": request.answer},
            "score": graded["score"],
            "feedback": graded["feedback"],
            "mistakes": graded["mistakes"],
            "started_at": request.started_at.isoformat() if request.started_at else None,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).execute
    )

    await technique_progress.record_technique_progress(current_user.id, technique["skill_tag"], graded["score"])

    tag = technique_progress.technique_skill_tag(technique["skill_tag"])
    mastery_row = _mastery_by_tag(user_db, current_user.id, [tag]).get(tag)

    return {
        "score": graded["score"],
        "feedback": graded["feedback"],
        "mistakes": graded["mistakes"],
        "provider_failure": graded.get("provider_failure", False),
        "mastery": _mastery_payload(mastery_row),
    }
