from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.core.supabase import get_supabase
from app.routers.auth import get_current_user, UserInfo
from app.services.ai_scoring import _call_ai
import json

router = APIRouter(prefix="/progress", tags=["progress"])

@router.get("/stats")
def get_user_stats(
    current_user: UserInfo = Depends(get_current_user),
):
    supabase = get_supabase()
    data = supabase.table("submissions").select("*").eq("user_id", current_user.id).execute()
    submissions = data.data

    if not submissions:
        return {
            "total_submissions": 0,
            "average_score": 0,
            "module_scores": {"speaking": 0, "writing": 0, "reading": 0, "listening": 0},
            "recent_submissions": [],
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

    recent = sorted(submissions, key=lambda x: x["created_at"], reverse=True)[:10]
    recent_list = [{
        "id": s["id"],
        "module": s["module"],
        "score": to_band(s["score"]),
        "feedback": (s.get("feedback") or "No feedback")[:100],
        "created_at": s["created_at"],
    } for s in recent]

    return {
        "total_submissions": total,
        "average_score": avg,
        "module_scores": module_scores,
        "recent_submissions": recent_list,
    }

@router.get("/history")
def get_submission_history(
    module: str | None = None,
    limit: int = 20,
    current_user: UserInfo = Depends(get_current_user),
):
    supabase = get_supabase()
    query = supabase.table("submissions").select("*").eq("user_id", current_user.id)
    if module:
        query = query.eq("module", module)
    data = query.order("created_at", desc=True).limit(limit).execute()
    return [{
        "id": s["id"],
        "module": s["module"],
        "score": s["score"],
        "created_at": s["created_at"],
    } for s in data.data]

@router.get("/coach-summary")
async def get_coach_summary(current_user: UserInfo = Depends(get_current_user)):
    supabase = get_supabase()

    data = supabase.table("submissions").select(
        "feedback, score, created_at"
    ).eq("user_id", current_user.id).eq("module", "speaking").order(
        "created_at", desc=True
    ).limit(5).execute()

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
