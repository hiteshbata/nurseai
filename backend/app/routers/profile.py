from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from app.core.supabase import get_supabase
from app.routers.auth import get_current_user, UserInfo

router = APIRouter(prefix="/profile", tags=["profile"])


class PracticePlanUpdate(BaseModel):
    target_band: Optional[str] = None
    exam_date: Optional[str] = None
    days_per_week: Optional[int] = None


@router.put("/practice-plan")
def update_practice_plan(
    payload: PracticePlanUpdate,
    current_user: UserInfo = Depends(get_current_user),
):
    supabase = get_supabase()

    body = {}
    now = datetime.utcnow().isoformat()

    if payload.target_band is not None:
        body["target_band"] = payload.target_band
    if payload.exam_date is not None:
        body["exam_date"] = payload.exam_date
    if payload.days_per_week is not None:
        body["days_per_week"] = payload.days_per_week

    if not body:
        existing = supabase.table("user_profiles").select("*").eq("user_id", current_user.id).execute()
        if existing.data:
            return existing.data[0]
        return {"onboarding_completed": False}

    body["updated_at"] = now

    supabase.table("user_profiles").update(body).eq("user_id", current_user.id).execute()

    result = supabase.table("user_profiles").select("*").eq("user_id", current_user.id).execute()
    if result.data:
        return result.data[0]
    return {"onboarding_completed": False}
