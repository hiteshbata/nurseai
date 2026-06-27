from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.routers.auth import get_current_user, UserInfo
from app.services.ai_scoring import compare_attempts
import json

router = APIRouter(prefix="/compare", tags=["progress"])


class CompareRequest(BaseModel):
    scenario_id: int
    attempt1_id: int
    attempt2_id: int


@router.post("/attempts")
async def compare_attempts_endpoint(
    request: CompareRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """Compare two attempts of the same scenario."""
    supabase = get_supabase()

    # Fetch both submissions
    s1 = supabase.table("submissions").select("*").eq("id", request.attempt1_id).eq("user_id", current_user.id).execute()
    s2 = supabase.table("submissions").select("*").eq("id", request.attempt2_id).eq("user_id", current_user.id).execute()

    if not s1.data or not s2.data:
        raise HTTPException(status_code=404, detail="One or both attempts not found")

    sub1 = s1.data[0]
    sub2 = s2.data[0]

    feedback1 = json.loads(sub1.get("feedback") or "{}")
    feedback2 = json.loads(sub2.get("feedback") or "{}")

    result = await compare_attempts(
        attempt1_feedback=feedback1,
        attempt2_feedback=feedback2,
        attempt1_transcript=sub1.get("answer", ""),
        attempt2_transcript=sub2.get("answer", ""),
        supabase=supabase,
    )

    return result