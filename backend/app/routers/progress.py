from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.core.supabase import get_supabase
from app.core.threading import run_sync
from app.core.rate_limit import SlidingWindowRateLimiter
from app.routers.auth import get_current_user, UserInfo
from app.services.ai_scoring import _call_ai
from app.services.plan_gating import get_plan_from_profile, has_study_plan_access, get_history_limit
from app.services.coach import (
    compute_criteria_averages,
    compute_streaks,
    identify_weak_criteria,
    weeks_until,
    build_study_plan,
    CRITERIA_LABELS,
)
import json

router = APIRouter(prefix="/progress", tags=["progress"])

STUDY_PLAN_MIN_SESSIONS = 3

COACH_SUMMARY_RATE_LIMIT_MAX_CALLS = 10
COACH_SUMMARY_RATE_LIMIT_WINDOW_SECONDS = 600
_coach_summary_rate_limiter = SlidingWindowRateLimiter(COACH_SUMMARY_RATE_LIMIT_MAX_CALLS, COACH_SUMMARY_RATE_LIMIT_WINDOW_SECONDS)

@router.get("/stats")
def get_user_stats(
    current_user: UserInfo = Depends(get_current_user),
):
    supabase = get_supabase()

    # Only score/module are needed for the aggregates below -- narrow select
    # avoids transferring full answer/feedback text for every submission
    # a user has ever made, which otherwise grows unboundedly with history.
    agg_data = supabase.table("submissions").select("score, module").eq(
        "user_id", current_user.id
    ).execute()
    submissions = agg_data.data

    # Narrow created_at-only query over the full history so streaks aren't
    # limited by the top-10 cap on recent_submissions below.
    dates_data = supabase.table("submissions").select("created_at").eq(
        "user_id", current_user.id
    ).execute()
    current_streak, longest_streak = compute_streaks([s["created_at"] for s in dates_data.data])

    if not submissions:
        return {
            "total_submissions": 0,
            "average_score": 0,
            "module_scores": {"speaking": 0, "writing": 0, "reading": 0, "listening": 0},
            "recent_submissions": [],
            "current_streak": current_streak,
            "longest_streak": longest_streak,
        }

    def to_band(val: float) -> float:
        return round((val / 100) * 6, 2) if val > 6 else val

    total = len(submissions)
    scores = [to_band(s["score"]) for s in submissions]
    avg = sum(scores) / total

    module_scores = {}
    for mod in ["speaking", "writing", "reading", "listening"]:
        mod_subs = [to_band(s["score"]) for s in submissions if s["module"] == mod]
        module_scores[mod] = sum(mod_subs) / len(mod_subs) if mod_subs else 0

    # Bounded at the DB level (ORDER BY + LIMIT) instead of fetching every
    # submission just to sort them in Python and keep the top 10.
    recent_data = supabase.table("submissions").select(
        "id, module, score, feedback, created_at"
    ).eq("user_id", current_user.id).order("created_at", desc=True).limit(10).execute()
    recent_list = [{
        "id": s["id"],
        "module": s["module"],
        "score": to_band(s["score"]),
        "feedback": (s.get("feedback") or "No feedback")[:100],
        "created_at": s["created_at"],
    } for s in recent_data.data]

    return {
        "total_submissions": total,
        "average_score": avg,
        "module_scores": module_scores,
        "recent_submissions": recent_list,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
    }

@router.get("/history")
def get_submission_history(
    module: str | None = None,
    limit: int = 20,
    current_user: UserInfo = Depends(get_current_user),
):
    supabase = get_supabase()

    profile_data = supabase.table("user_profiles").select(
        "plan, plan_expires_at"
    ).eq("user_id", current_user.id).execute()
    profile = profile_data.data[0] if profile_data.data else {}
    plan = get_plan_from_profile(profile)
    effective_limit = min(limit, get_history_limit(plan))

    query = supabase.table("submissions").select("*").eq("user_id", current_user.id)
    if module:
        query = query.eq("module", module)
    data = query.order("created_at", desc=True).limit(effective_limit).execute()
    return [{
        "id": s["id"],
        "module": s["module"],
        "score": s["score"],
        "created_at": s["created_at"],
    } for s in data.data]

@router.get("/coach-summary")
async def get_coach_summary(current_user: UserInfo = Depends(get_current_user)):
    if _coach_summary_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many requests — please slow down.")

    supabase = get_supabase()

    data = await run_sync(
        supabase.table("submissions").select("feedback, score, created_at")
        .eq("user_id", current_user.id).eq("module", "speaking")
        .order("created_at", desc=True).limit(5).execute
    )

    sessions = [s for s in data.data if s.get("feedback") and s["feedback"] != "No feedback"]

    if len(sessions) < 3:
        return {
            "summary_text": None,
            "message": "Complete 3 speaking sessions to unlock your personalized coach summary.",
            "sessions_count": len(sessions),
        }

    excerpts = []
    for s in sessions:
        try:
            fb = json.loads(s["feedback"])
            scores = fb.get("scores", {}) or {}
            criteria_snapshot = {k: v.get("score") for k, v in scores.items() if isinstance(v, dict)}
            excerpts.append({
                "top_strength": fb.get("top_strength", ""),
                "top_improvement": fb.get("top_improvement", ""),
                "overall_band": fb.get("overall_band", ""),
                "criteria": criteria_snapshot,
            })
        except (json.JSONDecodeError, AttributeError):
            continue

    if len(excerpts) < 3:
        return {
            "summary_text": None,
            "message": "Could not parse enough session data for a summary.",
            "sessions_count": len(excerpts),
        }

    prompt = f"""You are an OET coach. Based on the student's last {len(excerpts)} speaking sessions, write a 2-3 sentence summary of their performance.

Session data (feedback JSON excerpts):
{json.dumps(excerpts, indent=2)}

Write in this exact style:
"Your top strength: {{specific strength}}. Focus area this week: {{specific improvement}}. {{Optional third sentence about consistency or trend}}."

Be specific — cite actual criteria from the data (empathy, fluency, grammar, etc.) and reference real top_strength/top_improvement values. Do NOT use generic phrases like "keep practicing"."""

    result = await _call_ai(
        [{"role": "user", "content": prompt}],
        max_tokens=300,
        provider="openrouter",
        model="google/gemini-2.5-flash",
    )

    summary = result.get("raw_feedback", "").strip()

    return {
        "summary_text": summary or "Unable to generate summary at this time.",
        "message": None,
        "sessions_count": len(excerpts),
    }


@router.get("/study-plan")
async def get_study_plan(current_user: UserInfo = Depends(get_current_user)):
    """Elite-only: a personalized weekly study plan built from rule-based
    weak-criteria detection across the user's speaking history, plus an
    AI-generated narrative on top. See app.services.coach for the logic."""
    supabase = get_supabase()

    profile_data = await run_sync(
        supabase.table("user_profiles").select(
            "plan, plan_expires_at, target_band, exam_date, days_per_week"
        ).eq("user_id", current_user.id).execute
    )
    profile = profile_data.data[0] if profile_data.data else {}
    plan = get_plan_from_profile(profile)

    if not has_study_plan_access(plan):
        return {"locked": True, "ready": False, "upgrade_required": True, "current_plan": plan}

    submissions_data = await run_sync(
        supabase.table("submissions").select("question_id, feedback, score")
        .eq("user_id", current_user.id).eq("module", "speaking")
        .order("created_at", desc=True).execute
    )
    submissions = submissions_data.data or []
    total_sessions_scored = len(submissions)

    if total_sessions_scored < STUDY_PLAN_MIN_SESSIONS:
        return {
            "locked": False,
            "ready": False,
            "upgrade_required": False,
            "sessions_needed": STUDY_PLAN_MIN_SESSIONS - total_sessions_scored,
            "message": (
                f"Complete {STUDY_PLAN_MIN_SESSIONS - total_sessions_scored} more speaking "
                "session(s) to unlock your personalized study plan."
            ),
        }

    criteria_averages = compute_criteria_averages([s.get("feedback") for s in submissions])
    weak_criteria = identify_weak_criteria(criteria_averages, top_n=3)

    attempted_ids = {s["question_id"] for s in submissions if s.get("question_id")}
    scored_by_scenario: Dict[int, List[float]] = {}
    for s in submissions:
        qid = s.get("question_id")
        if qid:
            scored_by_scenario.setdefault(qid, []).append(s.get("score") or 0)

    scenarios_data = await run_sync(
        supabase.table("scenarios").select("id, title, difficulty")
        .eq("module", "speaking").eq("is_active", True).execute
    )
    all_scenarios = scenarios_data.data or []
    unattempted = [s for s in all_scenarios if s["id"] not in attempted_ids]

    recommended: List[Dict[str, Any]] = unattempted[:2]
    if scored_by_scenario:
        lowest_qid = min(scored_by_scenario, key=lambda qid: sum(scored_by_scenario[qid]) / len(scored_by_scenario[qid]))
        lowest_scenario = next((s for s in all_scenarios if s["id"] == lowest_qid), None)
        if lowest_scenario and lowest_scenario not in recommended:
            recommended.append(lowest_scenario)
    if not recommended:
        recommended = all_scenarios[:3]

    exam_date_str = profile.get("exam_date")
    weeks_to_exam: Optional[int] = None
    if exam_date_str:
        try:
            exam_date = datetime.fromisoformat(str(exam_date_str).replace("Z", "+00:00"))
            if exam_date.tzinfo is None:
                exam_date = exam_date.replace(tzinfo=timezone.utc)
            weeks_to_exam = weeks_until(datetime.now(timezone.utc), exam_date)
        except ValueError:
            weeks_to_exam = None

    ai_plan = await build_study_plan(
        weak_criteria=weak_criteria,
        total_sessions_scored=total_sessions_scored,
        recommended_scenarios=recommended,
        target_band=profile.get("target_band"),
        days_per_week=profile.get("days_per_week"),
        weeks_to_exam=weeks_to_exam,
    )

    return {
        "locked": False,
        "ready": True,
        "upgrade_required": False,
        "criteria_averages": criteria_averages,
        "weak_criteria": [
            {"key": k, "label": CRITERIA_LABELS.get(k, k), "average": criteria_averages.get(k)}
            for k in weak_criteria
        ],
        "recommended_scenarios": [
            {"id": s["id"], "title": s["title"], "difficulty": s.get("difficulty")} for s in recommended
        ],
        "weeks_to_exam": weeks_to_exam,
        "total_sessions_scored": total_sessions_scored,
        **ai_plan,
    }


class TestSubmission(BaseModel):
    answers: List[Dict[str, Any]]

@router.post("/submit-test")
def submit_test(
    test_data: TestSubmission,
    current_user: UserInfo = Depends(get_current_user),
):
    supabase = get_supabase()
    total_count = len(test_data.answers)
    score = 0.0
    supabase.table("submissions").insert({
        "user_id": current_user.id,
        "question_id": test_data.answers[0]["questionId"] if test_data.answers else 0,
        "module": "test",
        "answer": "Full test submission",
        "score": score,
        "feedback": "Test completed",
    }).execute()

    return {
        "score": score,
        "correct": 0,
        "incorrect": total_count,
        "total": total_count,
        "module_scores": {"speaking": 4.5, "writing": 4.7, "reading": 4.9, "listening": 4.8},
    }
