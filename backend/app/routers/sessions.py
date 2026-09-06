import logging
from fastapi import APIRouter, Depends, HTTPException
from app.core.config import settings
from app.routers.auth import get_current_user, get_user_supabase, UserInfo
from app.core.supabase import get_supabase
from supabase import Client
from app.services.plan_gating import get_plan_from_profile, parse_timestamp
from app.services.institution_access import (
    get_effective_speaking_limit,
    get_active_institution_module_access,
    is_active_institution_member,
)
from app.services.institution_admin import get_qualifying_memberships, ROLE_RANK
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])

MAX_INCREMENT_RETRIES = 5


def get_month_start_utc():
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def _usage_payload(profile_data: dict, month_start: str, plan_limit: int) -> dict:
    """Pure computation, no DB access. If the stored reset_date is stale,
    reports sessions_used as 0 without writing -- the actual reset write
    only happens on the check-and-increment (POST) path.

    plan_limit is resolved by the caller (get_effective_speaking_limit) --
    an active institution speaking grant replaces the B2C plan limit
    entirely, so this function never re-derives it from PLAN_LIMITS itself.

    bonus_sessions (from referrals/admin grants) is a spend-down wallet, not
    a monthly allowance: it's only drawn on once the plan's own monthly quota
    is exhausted, and unlike sessions_used_this_month it's never reset --
    unspent bonus carries over across months untouched."""
    plan = get_plan_from_profile(profile_data)
    bonus_sessions = profile_data.get("bonus_sessions", 0)

    reset_date = profile_data.get("sessions_reset_date")
    if not reset_date or reset_date < month_start:
        sessions_used = 0
    else:
        sessions_used = profile_data.get("sessions_used_this_month", 0)

    plan_remaining = max(0, plan_limit - sessions_used)

    return {
        "sessions_used": sessions_used,
        "sessions_limit": plan_limit + bonus_sessions,
        "sessions_remaining": plan_remaining + bonus_sessions,
        "bonus_sessions": bonus_sessions,
        "plan": plan,
        "auto_renew_enabled": bool(profile_data.get("auto_renew_enabled")),
        "plan_expires_at": profile_data.get("plan_expires_at"),
    }


@router.get("/usage")
def get_session_usage(current_user: UserInfo = Depends(get_current_user)):
    supabase = get_supabase()

    # Smallest reusable way to expose institution state to the frontend: it
    # already fetches /sessions/usage for plan/quota on every authenticated
    # route (see AppShell.tsx), so nav visibility rides along here instead of
    # a second endpoint/fetch. modules is only resolved when the membership
    # check is true -- a plain B2C user skips the extra query entirely.
    is_institution_member = is_active_institution_member(supabase, current_user.id)
    institution_modules = (
        sorted(get_active_institution_module_access(supabase, current_user.id)["modules"])
        if is_institution_member else []
    )

    # Same ride-along as above, for the Institution nav section: highest
    # teacher/institution_admin role across any active qualifying membership,
    # or None. This is nav-visibility only -- the actual authorization
    # boundary is require_active_institution_role on the /institution/*
    # routes themselves, re-resolved server-side on every call.
    admin_memberships = get_qualifying_memberships(supabase, current_user.id, "teacher")
    institution_admin_role = (
        max((m["role"] for m in admin_memberships), key=lambda r: ROLE_RANK[r])
        if admin_memberships else None
    )

    profile = supabase.table("user_profiles").select(
        "plan, plan_expires_at, sessions_used_this_month, sessions_reset_date, auto_renew_enabled, bonus_sessions"
    ).eq("user_id", current_user.id).execute()

    if not profile.data:
        free_limit = get_effective_speaking_limit(supabase, current_user.id, "free")
        return {
            "sessions_used": 0,
            "sessions_limit": free_limit,
            "sessions_remaining": free_limit,
            "bonus_sessions": 0,
            "plan": "free",
            "auto_renew_enabled": False,
            "plan_expires_at": None,
            "is_institution_member": is_institution_member,
            "institution_modules": institution_modules,
            "institution_admin_role": institution_admin_role,
        }

    plan = get_plan_from_profile(profile.data[0])
    plan_limit = get_effective_speaking_limit(supabase, current_user.id, plan)
    payload = _usage_payload(profile.data[0], get_month_start_utc(), plan_limit)
    payload["is_institution_member"] = is_institution_member
    payload["institution_modules"] = institution_modules
    payload["institution_admin_role"] = institution_admin_role
    return payload


@router.post("/check-and-increment")
def check_and_increment_session(
    current_user: UserInfo = Depends(get_current_user),
    user_db: Client = Depends(get_user_supabase),
):
    supabase = get_supabase()
    # user_profiles writes below (sessions_used_this_month, bonus_sessions)
    # stay on the service_role client deliberately: those are entitlement
    # columns authenticated has no write grant on (see
    # backend/migrations/2026-08-02_authenticated_user_rls.sql Part 1) --
    # only the session_usage insert further down uses user_db.

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
            "plan, plan_expires_at, sessions_used_this_month, sessions_reset_date, auto_renew_enabled, bonus_sessions"
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

        plan = get_plan_from_profile(profile_data)
        plan_limit = get_effective_speaking_limit(supabase, current_user.id, plan)
        usage = _usage_payload(profile_data, month_start, plan_limit)

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

        # Spend the plan's own monthly quota before touching the bonus
        # wallet, so a never-expiring referral/bonus credit is saved for
        # whenever the plan quota runs dry rather than drained first.
        spending_bonus = usage["sessions_used"] >= plan_limit

        # Compare-and-swap: only succeeds if the counter being spent hasn't
        # changed since we read it, so two concurrent requests can't both
        # observe the same count and both write the same decremented/
        # incremented value.
        if spending_bonus:
            result = (
                supabase.table("user_profiles")
                .update({"bonus_sessions": usage["bonus_sessions"] - 1})
                .eq("user_id", current_user.id)
                .eq("bonus_sessions", usage["bonus_sessions"])
                .execute()
            )
        else:
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

    if is_first_ever_session(current_user.id, "speaking"):
        try:
            supabase.rpc("reward_referral", {"p_referred_id": current_user.id}).execute()
        except Exception:
            logger.exception("reward_referral failed | user_id=%s", current_user.id)

    return {
        "allowed": True,
        "session_id": session_id,
        "sessions_used": usage["sessions_used"] + (0 if spending_bonus else 1),
        "sessions_remaining": usage["sessions_remaining"] - 1,
        "spent_bonus": spending_bonus,
    }


def release_session_charge(user_id: str, session_id: int, spent_bonus: bool) -> None:
    """Refund a session credit that check_and_increment_session charged at
    session start when the AI call it was meant to pay for never actually
    succeeded (provider failure on session init) -- otherwise a student loses
    a real session credit for a conversation that never happened. Mirrors the
    increment's compare-and-swap so a concurrent request touching the same
    counter can't be clobbered. Also deletes the session_usage row so a
    retry can't reuse a session_id that was never really charged, and
    is_first_ever_session/validate_session don't see a session that
    officially never started."""
    supabase = get_supabase()
    for _ in range(MAX_INCREMENT_RETRIES):
        profile = supabase.table("user_profiles").select(
            "sessions_used_this_month, bonus_sessions"
        ).eq("user_id", user_id).execute()
        if not profile.data:
            break
        profile_data = profile.data[0]

        if spent_bonus:
            current = profile_data.get("bonus_sessions", 0)
            result = (
                supabase.table("user_profiles")
                .update({"bonus_sessions": current + 1})
                .eq("user_id", user_id)
                .eq("bonus_sessions", current)
                .execute()
            )
        else:
            current = profile_data.get("sessions_used_this_month", 0)
            if current <= 0:
                # Already at 0 (e.g. month rolled over between charge and
                # release) -- nothing to refund.
                break
            result = (
                supabase.table("user_profiles")
                .update({"sessions_used_this_month": current - 1})
                .eq("user_id", user_id)
                .eq("sessions_used_this_month", current)
                .execute()
            )
        if result.data:
            break
    else:
        logger.error(
            "release_session_charge: gave up refunding after retries | user_id=%s session_id=%s",
            user_id, session_id,
        )

    try:
        supabase.table("session_usage").delete().eq("id", session_id).eq("user_id", user_id).execute()
    except Exception:
        logger.exception(
            "release_session_charge: failed to delete session_usage row | user_id=%s session_id=%s",
            user_id, session_id,
        )


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


def claim_session_for_scoring(user_id: str, session_id: int) -> bool:
    """Atomically marks a session_usage row as scored (see
    public.claim_session_for_scoring, migrations/20260802030000). Returns
    False if the session was already claimed -- e.g. a retried or replayed
    /speaking/score call reusing a still-valid session_id -- so the caller
    can reject the second attempt instead of writing a duplicate submission."""
    supabase = get_supabase()
    result = supabase.rpc(
        "claim_session_for_scoring",
        {"p_session_id": session_id, "p_user_id": user_id},
    ).execute()
    return bool(result.data)


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
