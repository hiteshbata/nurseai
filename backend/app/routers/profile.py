from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime, timezone
from app.core.supabase import get_supabase
from app.routers.auth import get_current_user, UserInfo

router = APIRouter(prefix="/profile", tags=["profile"])

# Tables that store rows keyed by user_id and aren't already guaranteed to
# cascade-delete at the DB level -- cleaned up explicitly so account deletion
# doesn't leave orphaned rows regardless of how FKs are configured in Supabase.
_USER_OWNED_TABLES = ["submissions", "session_usage", "user_profiles", "user_roles"]


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
    now = datetime.now(timezone.utc).isoformat()

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


@router.delete("/account", status_code=204)
def delete_account(
    current_user: UserInfo = Depends(get_current_user),
):
    supabase = get_supabase()

    for table in _USER_OWNED_TABLES:
        supabase.table(table).delete().eq("user_id", current_user.id).execute()

    try:
        supabase.auth.admin.delete_user(current_user.id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete account: {str(e)}")
