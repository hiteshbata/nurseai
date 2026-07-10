from fastapi import APIRouter, Depends, HTTPException
from app.core.config import settings
from app.routers.auth import get_current_user, UserInfo
from app.core.supabase import get_supabase
from app.core.plans import PLAN_LIMITS
from app.services.plan_gating import get_plan_from_profile, parse_timestamp
from datetime import datetime, timezone

router = APIRouter(prefix="/sessions", tags=["sessions"])

MAX_INCREMENT_RETRIES = 5


def get_month_start_utc():
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def _usage_payload(profile_data: dict, month_start: str) -> dict:
    """Pure computation, no DB access. If the stored reset_date is stale,
    reports sessions_used as 0 without writing -- the actual reset write
    only happens on the check-and-increment (POST) path."""
    plan = get_plan_from_profile(profile_data)
    limit = PLAN_LIMITS.get(plan, 3)

    reset_date = profile_data.get("sessions_reset_date")
    if not reset_date or reset_date < month_start:
        sessions_used = 0
    else:
        sessions_used = profile_data.get("sessions_used_this_month", 0)

    return {
        "sessions_used": sessions_used,
        "sessions_limit": limit,
        "sessions_remaining": max(0, limit - sessions_used),
        "plan": plan,
        "auto_renew_enabled": bool(profile_data.get("auto_renew_enabled")),
        "plan_expires_at": profile_data.get("plan_expires_at"),
    }


@router.get("/usage")
def get_session_usage(current_user: UserInfo = Depends(get_current_user)):
    supabase = get_supabase()

    profile = supabase.table("user_profiles").select(
        "plan, plan_expires_at, sessions_used_this_month, sessions_reset_date, auto_renew_enabled"
    ).eq("user_id", current_user.id).execute()

    if not profile.data:
        free_limit = PLAN_LIMITS["free"]
        return {
            "sessions_used": 0,
            "sessions_limit": free_limit,
            "sessions_remaining": free_limit,
            "plan": "free",
            "auto_renew_enabled": False,
            "plan_expires_at": None,
        }

    return _usage_payload(profile.data[0], get_month_start_utc())


@router.post("/check-and-increment")
def check_and_increment_session(
    current_user: UserInfo = Depends(get_current_user),
):
    supabase = get_supabase()

    # The compare-and-swap update below only ever matches an existing row;
    # a user with no user_profiles row yet (e.g. registered but never
    # completed onboarding) would fail every retry and always 409. This
    # upsert only creates a row when one is missing (ON CONFLICT DO
    # NOTHING) -- it never touches an existing row's data.
    supabase.table("user_profiles").upsert(
        {"user_id": current_user.id, "sessions_used_this_month": 0},
        on_conflict="user_id",
        ignore_duplicates=True,
    ).execute()

    for _ in range(MAX_INCREMENT_RETRIES):
        profile = supabase.table("user_profiles").select(
            "plan, plan_expires_at, sessions_used_this_month, sessions_reset_date, auto_renew_enabled"
        ).eq("user_id", current_user.id).execute()
        profile_data = profile.data[0]
        month_start = get_month_start_utc()
        reset_date = profile_data.get("sessions_reset_date")

        if not reset_date or reset_date < month_start:
            # Reset write lives here (POST path), not in the GET /usage handler.
            supabase.table("user_profiles").update({
                "sessions_used_this_month": 0,
                "sessions_reset_date": month_start,
            }).eq("user_id", current_user.id).execute()
            profile_data = {
                **profile_data,
                "sessions_used_this_month": 0,
                "sessions_reset_date": month_start,
            }

        usage = _usage_payload(profile_data, month_start)

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
    so a client can't fabricate an id to skip the quota charge. Also rejects a
    session past CHAT_SESSION_MAX_SECONDS old -- otherwise a session_id (in
    particular a free user's premium-trial first session) stays valid forever
    and can keep hitting /chat and /tts at whatever tier it was granted."""
    supabase = get_supabase()
    result = (
        supabase.table("session_usage")
        .select("id, created_at")
        .eq("id", session_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return False
    created_at = parse_timestamp(result.data[0].get("created_at"))
    if created_at is None:
        return True
    age_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()
    return age_seconds <= settings.CHAT_SESSION_MAX_SECONDS


def is_first_ever_session(user_id: str, session_type: str = "speaking") -> bool:
    """True if this user has at most one session_usage row of this type ever.
    session_usage rows are created by check_and_increment_session at session
    start (before any /chat or /tts calls), so this stays true for the whole
    duration of a user's very first session and flips to false the moment
    they start a second one — used to grant free-tier users one full-quality
    "premium trial" session."""
    supabase = get_supabase()
    result = (
        supabase.table("session_usage")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("session_type", session_type)
        .execute()
    )
    return (result.count or 0) <= 1
