from fastapi import APIRouter, Depends, HTTPException
from app.core.config import settings
from app.routers.auth import get_current_user, UserInfo
from app.core.supabase import get_supabase
from app.core.plans import PLAN_LIMITS
from app.services.plan_gating import get_plan_from_profile
from datetime import datetime, timezone

router = APIRouter(prefix="/sessions", tags=["sessions"])

MAX_INCREMENT_RETRIES = 5


def get_month_start_utc():
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


@router.get("/usage")
async def get_session_usage(current_user: UserInfo = Depends(get_current_user)):
    supabase = get_supabase()

    profile = supabase.table("user_profiles").select(
        "plan, plan_expires_at, sessions_used_this_month, sessions_reset_date"
    ).eq("user_id", current_user.id).execute()

    if not profile.data:
        return {"sessions_used": 0, "sessions_limit": 3, "plan": "free"}

    profile_data = profile.data[0]
    plan = get_plan_from_profile(profile_data)
    limit = PLAN_LIMITS.get(plan, 3)

    reset_date = profile_data.get("sessions_reset_date")
    month_start = get_month_start_utc()

    if not reset_date or reset_date < month_start:
        supabase.table("user_profiles").update({
            "sessions_used_this_month": 0,
            "sessions_reset_date": month_start,
        }).eq("user_id", current_user.id).execute()
        sessions_used = 0
    else:
        sessions_used = profile_data.get("sessions_used_this_month", 0)

    return {
        "sessions_used": sessions_used,
        "sessions_limit": limit,
        "sessions_remaining": max(0, limit - sessions_used),
        "plan": plan,
    }


@router.post("/check-and-increment")
async def check_and_increment_session(
    current_user: UserInfo = Depends(get_current_user),
):
    supabase = get_supabase()

    for _ in range(MAX_INCREMENT_RETRIES):
        usage = await get_session_usage(current_user)

        if usage["sessions_remaining"] <= 0:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "session_limit_reached",
                    "message": f"You have used all {usage['sessions_limit']} sessions this month.",
                    "plan": usage["plan"],
                    "upgrade_required": usage["plan"] == "free",
                },
            )

        # Compare-and-swap: only succeeds if sessions_used_this_month hasn't
        # changed since we read it, so two concurrent requests can't both
        # observe the same count and both write the same incremented value.
        result = (
            supabase.table("user_profiles")
            .update({"sessions_used_this_month": usage["sessions_used"] + 1})
            .eq("user_id", current_user.id)
            .eq("sessions_used_this_month", usage["sessions_used"])
            .execute()
        )
        if result.data:
            break
    else:
        raise HTTPException(
            status_code=409,
            detail="Could not record session usage due to a conflicting request — please try again.",
        )

    session_row = supabase.table("session_usage").insert({
        "user_id": current_user.id,
        "session_type": "speaking",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    session_id = session_row.data[0]["id"] if session_row.data else None

    return {
        "allowed": True,
        "session_id": session_id,
        "sessions_used": usage["sessions_used"] + 1,
        "sessions_remaining": usage["sessions_remaining"] - 1,
    }


def validate_session(user_id: str, session_id: int) -> bool:
    """Confirm session_id was actually issued to this user by check_and_increment_session,
    so a client can't fabricate an id to skip the quota charge."""
    supabase = get_supabase()
    result = (
        supabase.table("session_usage")
        .select("id")
        .eq("id", session_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    return bool(result.data)
