from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.core.supabase import get_supabase
from app.core.threading import run_sync
from app.core.rate_limit import SlidingWindowRateLimiter
from app.routers.auth import get_current_user, get_user_supabase, UserInfo
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
from app.services.coaching_messages import CONFIDENCE_MESSAGE
from app.services.dashboard_analytics import compute_trend, get_skill_insights, pick_weakest_module
from supabase import Client
import json

router = APIRouter(prefix="/progress", tags=["progress"])

STUDY_PLAN_MIN_SESSIONS = 3

COACH_SUMMARY_RATE_LIMIT_MAX_CALLS = 10
COACH_SUMMARY_RATE_LIMIT_WINDOW_SECONDS = 600
_coach_summary_rate_limiter = SlidingWindowRateLimiter(COACH_SUMMARY_RATE_LIMIT_MAX_CALLS, COACH_SUMMARY_RATE_LIMIT_WINDOW_SECONDS, name="progress:coach_summary")

STUDY_PLAN_RATE_LIMIT_MAX_CALLS = 10
STUDY_PLAN_RATE_LIMIT_WINDOW_SECONDS = 600
_study_plan_rate_limiter = SlidingWindowRateLimiter(STUDY_PLAN_RATE_LIMIT_MAX_CALLS, STUDY_PLAN_RATE_LIMIT_WINDOW_SECONDS, name="progress:study_plan")

MODULE_NAMES = ["speaking", "writing", "reading", "listening"]


@router.get("/stats")
async def get_user_stats(
    current_user: UserInfo = Depends(get_current_user),
    user_db: Client = Depends(get_user_supabase),
):
    supabase = get_supabase()

    # One narrow, oldest-first query backs the overall average, per-module
    # averages+trend, last-activity, and streak -- replaces the previous two
    # separate full-history scans (score+module, then created_at again).
    agg_data = supabase.table("submissions").select("score, module, created_at").eq(
        "user_id", current_user.id
    ).order("created_at").execute()
    submissions = agg_data.data
    current_streak, longest_streak = compute_streaks([s["created_at"] for s in submissions])

    if not submissions:
        return {
            "total_submissions": 0,
            "average_score": 0,
            "module_scores": {m: 0 for m in MODULE_NAMES},
            "recent_submissions": [],
            "current_streak": current_streak,
            "longest_streak": longest_streak,
            "module_averages": {
                m: {
                    "average": 0, "trend": "insufficient_data", "last_activity": None,
                    "submission_count": 0, "weakest_skill": None, "strongest_skill": None,
                }
                for m in MODULE_NAMES
            },
            "weak_skills": [],
            "next_best_action": None,
        }

    def to_band(val: float) -> float:
        return round((val / 100) * 6, 2) if val > 6 else val

    total = len(submissions)
    scores = [to_band(s["score"]) for s in submissions]
    avg = sum(scores) / total

    module_scores = {}
    module_averages = {}
    for mod in MODULE_NAMES:
        mod_subs = [s for s in submissions if s["module"] == mod]  # oldest-first, from the query order above
        mod_scores = [to_band(s["score"]) for s in mod_subs]
        mod_avg = sum(mod_scores) / len(mod_scores) if mod_scores else 0
        module_scores[mod] = mod_avg
        module_averages[mod] = {
            "average": mod_avg,
            "trend": compute_trend(mod_scores) if mod_scores else "insufficient_data",
            "last_activity": mod_subs[-1]["created_at"] if mod_subs else None,
            "submission_count": len(mod_subs),
        }

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

    # Per-module weakest/strongest skill + cross-module weak-skills list +
    # a module-level Next Best Action pointer -- all read off the same
    # skill_graph.get_weakness() every module's own /weakness endpoint
    # already uses (see app.services.dashboard_analytics).
    skill_insights = await get_skill_insights(user_db, current_user.id)
    for mod in MODULE_NAMES:
        module_averages[mod].update(skill_insights["module_extremes"][mod])
    weak_skills = skill_insights["weak_skills"]

    next_best_action = None
    weakest_module = pick_weakest_module(module_averages)
    if weakest_module:
        matching_skill = next((s for s in weak_skills if s["module"] == weakest_module), None)
        if matching_skill:
            reason = f"{matching_skill['label']} is your weakest area in {weakest_module}, based on your recent sessions."
            confidence_message = CONFIDENCE_MESSAGE["history"].format(attempts=matching_skill["attempts"])
            based_on = "history"
        else:
            reason = f"Your {weakest_module} average ({module_averages[weakest_module]['average']:.1f}/6) is your lowest-scoring module."
            confidence_message = "Not enough attempts yet on individual skills within this module -- keep practicing to sharpen this."
            based_on = "module_average"
        next_best_action = {
            "module": weakest_module,
            "reason": reason,
            "confidence_message": confidence_message,
            "based_on": based_on,
        }

    return {
        "total_submissions": total,
        "average_score": avg,
        "module_scores": module_scores,
        "recent_submissions": recent_list,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "module_averages": module_averages,
        "weak_skills": weak_skills,
        "next_best_action": next_best_action,
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
        purpose="progress_summary",
        max_tokens=300,
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
    if _study_plan_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many requests -- please try again in a while.")
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
        supabase.table("submissions").select("scenario_id, feedback, score")
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

    attempted_ids = {s["scenario_id"] for s in submissions if s.get("scenario_id")}
    scored_by_scenario: Dict[int, List[float]] = {}
    for s in submissions:
        sid = s.get("scenario_id")
        if sid:
            scored_by_scenario.setdefault(sid, []).append(s.get("score") or 0)

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

    question_ids = [a["questionId"] for a in test_data.answers if a.get("questionId")]
    questions_data = (
        supabase.table("questions").select("id, module, correct_answer")
        .in_("id", question_ids).execute()
        if question_ids else None
    )
    questions_by_id = {q["id"]: q for q in questions_data.data} if questions_data else {}

    # Only MCQ questions (reading/listening) carry a correct_answer -- speaking/writing
    # are open-ended and can't be auto-graded, so they're excluded from scoring.
    module_results: Dict[str, List[bool]] = {}
    graded_count = 0
    correct_count = 0
    for a in test_data.answers:
        q = questions_by_id.get(a.get("questionId"))
        if not q or q.get("correct_answer") is None:
            continue
        graded_count += 1
        is_correct = a.get("selectedOption") == q["correct_answer"]
        if is_correct:
            correct_count += 1
        module_results.setdefault(q["module"], []).append(is_correct)

    score = round((correct_count / graded_count) * 6, 2) if graded_count else 0.0

    module_scores = {}
    for mod in ["speaking", "writing", "reading", "listening"]:
        results = module_results.get(mod)
        module_scores[mod] = round(sum(results) / len(results) * 6, 2) if results else 0

    supabase.table("submissions").insert({
        "user_id": current_user.id,
        "scenario_id": test_data.answers[0]["questionId"] if test_data.answers else 0,
        "module": "test",
        "answer": "Full test submission",
        "score": score,
        "feedback": "Test completed",
    }).execute()

    return {
        "score": score,
        "correct": correct_count,
        "incorrect": graded_count - correct_count,
        "total": total_count,
        "module_scores": module_scores,
    }
