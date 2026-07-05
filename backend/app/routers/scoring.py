from fastapi import APIRouter, Depends
from app.core.supabase import get_supabase
from app.routers.auth import get_current_user, UserInfo
from app.services.coach import compute_criteria_averages

router = APIRouter(prefix="/scoring", tags=["scoring"])


@router.get("/criteria-averages")
def get_criteria_averages(current_user: UserInfo = Depends(get_current_user)):
    supabase = get_supabase()

    data = supabase.table("submissions").select(
        "feedback, created_at"
    ).eq("user_id", current_user.id).eq("module", "speaking").order(
        "created_at", desc=True
    ).execute()

    result = compute_criteria_averages([s.get("feedback") for s in data.data])

    return {
        "criteria_averages": result,
        "total_sessions_scored": len(data.data),
        "has_sufficient_data": any(v is not None for v in result.values()),
    }
