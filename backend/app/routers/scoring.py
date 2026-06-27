from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.routers.auth import get_current_user, UserInfo
from app.services.ai_scoring import analyze_speaking_submission, analyze_writing_submission
import json

router = APIRouter(prefix="/scoring", tags=["scoring"])

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
