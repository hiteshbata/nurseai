import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from app.core.supabase import get_supabase
from app.routers.auth import get_current_user, UserInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profile", tags=["profile"])

# Tables that store rows keyed by user_id and aren't already guaranteed to
# cascade-delete at the DB level -- cleaned up explicitly so account deletion
# doesn't leave orphaned rows regardless of how FKs are configured in Supabase.
# session_transcripts must come before session_usage: it has a NOT NULL FK
# to session_usage.id, so deleting the parent first violates that constraint.
_USER_OWNED_TABLES = [
    "submissions",
    "session_transcripts",
    "session_usage",
    "user_profiles",
    "user_roles",
    "payments",
    "failed_payments",
]


def _delete_user_owned_rows(supabase, user_id: str) -> None:
    for table in _USER_OWNED_TABLES:
        supabase.table(table).delete().eq("user_id", user_id).execute()
    # referrals has two FK columns (referrer_id, referred_id), no single user_id
    supabase.table("referrals").delete().eq("referrer_id", user_id).execute()
    supabase.table("referrals").delete().eq("referred_id", user_id).execute()


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

    _delete_user_owned_rows(supabase, current_user.id)

    try:
        supabase.auth.admin.delete_user(current_user.id)
    except Exception:
        logger.exception("delete-account failed | user_id=%s", current_user.id)
        raise HTTPException(status_code=500, detail="Could not delete account. Please try again or contact support.")
