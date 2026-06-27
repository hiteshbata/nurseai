from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from app.core.supabase import get_supabase
from app.routers.auth import get_current_user, UserInfo
from app.services.ai_scoring import get_grammar_feedback

router = APIRouter(prefix="/grammar", tags=["grammar"])


class GrammarRequest(BaseModel):
    mistakes: List[str]
    student_level: str = "intermediate"


@router.post("/teach")
async def teach_grammar(
    request: GrammarRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """Get personalized grammar teaching for detected mistakes."""
    supabase = get_supabase()
    result = await get_grammar_feedback(
        mistakes=request.mistakes,
        student_level=request.student_level,
        supabase=supabase,
    )
    return result