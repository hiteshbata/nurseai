from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.routers.auth import get_current_user, UserInfo
from app.services.ai_scoring import analyze_speaking_submission, analyze_writing_submission
import json

router = APIRouter(prefix="/scoring", tags=["scoring"])

CRITERIA_KEYS = [
    "empathy",
    "patient_perspective",
    "providing_structure",
    "information_gathering",
    "information_giving",
    "intelligibility",
    "fluency",
    "appropriateness_of_language",
    "grammar",
]


@router.get("/criteria-averages")
async def get_criteria_averages(current_user: UserInfo = Depends(get_current_user)):
    supabase = get_supabase()

    data = supabase.table("submissions").select(
        "feedback, created_at"
    ).eq("user_id", current_user.id).eq("module", "speaking").order(
        "created_at", desc=True
    ).execute()

    accumulators = {k: {"sum": 0.0, "count": 0} for k in CRITERIA_KEYS}

    for sub in data.data:
        try:
            feedback = json.loads(sub.get("feedback") or "{}")
        except json.JSONDecodeError:
            continue
        scores = feedback.get("scores", {}) or {}

        empathy_score = scores.get("empathy", {}).get("score")
        if empathy_score is None:
            empathy_score = scores.get("relationship_building", {}).get("score")
        if empathy_score is not None:
            accumulators["empathy"]["sum"] += empathy_score
            accumulators["empathy"]["count"] += 1

        for key in CRITERIA_KEYS[1:]:
            score = scores.get(key, {}).get("score")
            if score is not None:
                accumulators[key]["sum"] += score
                accumulators[key]["count"] += 1

    result = {}
    all_null = True
    for key, acc in accumulators.items():
        if acc["count"] >= 3:
            result[key] = round(acc["sum"] / acc["count"], 2)
            all_null = False
        else:
            result[key] = None

    return {
        "criteria_averages": result,
        "total_sessions_scored": len(data.data),
        "has_sufficient_data": not all_null,
    }

class ScoringRequest(BaseModel):
    question_id: int
    response: str
    module: str = "writing"

@router.post("/submit")
async def submit_for_scoring(
    request: ScoringRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    supabase = get_supabase()
    try:
        data = supabase.table("questions").select("*").eq("id", request.question_id).execute()
        if not data.data:
            raise HTTPException(status_code=404, detail="Question not found")
        question = data.data[0]

        if request.module == "writing":
            feedback = await analyze_writing_submission(request.response, question["content"])
        else:
            feedback = await analyze_speaking_submission(request.response, question["content"])

        overall_score = feedback.get("overall_score", 7.0)
        supabase.table("submissions").insert({
            "user_id": current_user.id,
            "question_id": question["id"],
            "module": request.module,
            "answer": request.response,
            "score": overall_score,
            "feedback": json.dumps(feedback),
        }).execute()

        return {"success": True, "score": overall_score, "feedback": feedback}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to score response")
