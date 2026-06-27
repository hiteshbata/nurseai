from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Dict, Any
from app.core.supabase import get_supabase
from app.routers.auth import get_current_user, UserInfo

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

    total = len(submissions)
    avg = sum(s["score"] for s in submissions) / total

    module_scores = {}
    for mod in ["speaking", "writing", "reading", "listening"]:
        mod_subs = [s for s in submissions if s["module"] == mod]
        module_scores[mod] = sum(s["score"] for s in mod_subs) / len(mod_subs) if mod_subs else 0

    recent = sorted(submissions, key=lambda x: x["created_at"], reverse=True)[:10]
    recent_list = [{
        "id": s["id"],
        "module": s["module"],
        "score": s["score"],
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
        "module_scores": {"speaking": 75, "writing": 78, "reading": 82, "listening": 80},
    }
