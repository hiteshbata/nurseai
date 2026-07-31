import logging
import secrets
import string

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import settings
from app.core.supabase import get_supabase
from app.routers.auth import get_current_user, UserInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/referrals", tags=["referrals"])

_CODE_ALPHABET = string.ascii_uppercase + string.digits
_MAX_CODE_ATTEMPTS = 5
_RANDOM_CODE_LENGTH = 6
_NAME_SUFFIX_LENGTH = 2


def _generate_code(name: str) -> str:
    """Name-based code (e.g. "HITESH42") when we have a usable name, so
    students can read a friend's code aloud instead of copy-pasting only --
    falls back to a fully random code for names with no ASCII letters
    (non-Latin scripts, blank name) rather than emitting an empty base."""
    first_word = name.split()[0] if name.split() else ""
    base = "".join(ch for ch in first_word if ch.isalnum() and ch.isascii()).upper()[:8]
    if not base:
        return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_RANDOM_CODE_LENGTH))
    suffix = "".join(secrets.choice(string.digits) for _ in range(_NAME_SUFFIX_LENGTH))
    return f"{base}{suffix}"


def _get_or_create_referral_code(supabase, user_id: str, name: str) -> str:
    supabase.table("user_profiles").upsert(
        {"user_id": user_id}, on_conflict="user_id", ignore_duplicates=True
    ).execute()

    profile = supabase.table("user_profiles").select("referral_code").eq("user_id", user_id).execute()
    existing = profile.data[0].get("referral_code") if profile.data else None
    if existing:
        return existing

    for _ in range(_MAX_CODE_ATTEMPTS):
        code = _generate_code(name)
        try:
            supabase.table("user_profiles").update({"referral_code": code}).eq("user_id", user_id).execute()
            return code
        except Exception:
            logger.warning("referral code collision, retrying | user_id=%s", user_id)
    raise RuntimeError("Could not generate a unique referral code")


@router.get("/me")
def get_my_referrals(current_user: UserInfo = Depends(get_current_user)):
    supabase = get_supabase()
    code = _get_or_create_referral_code(supabase, current_user.id, current_user.name or "")

    profile = supabase.table("user_profiles").select("bonus_sessions").eq("user_id", current_user.id).execute()
    bonus_sessions = profile.data[0].get("bonus_sessions", 0) if profile.data else 0

    referred = supabase.table("referrals").select("status").eq("referrer_id", current_user.id).execute()
    rows = referred.data or []

    return {
        "referral_code": code,
        "referral_link": f"{settings.FRONTEND_URL}/auth/register?ref={code}",
        "bonus_sessions": bonus_sessions,
        "referred_count": len(rows),
        "rewarded_count": sum(1 for r in rows if r["status"] == "rewarded"),
    }


class RedeemReferralRequest(BaseModel):
    code: str


@router.post("/redeem")
def redeem_referral(payload: RedeemReferralRequest, current_user: UserInfo = Depends(get_current_user)):
    supabase = get_supabase()
    code = payload.code.strip().upper()
    if not code:
        return {"redeemed": False}

    referrer = supabase.table("user_profiles").select("user_id").eq("referral_code", code).execute()
    if not referrer.data:
        return {"redeemed": False}
    referrer_id = referrer.data[0]["user_id"]
    if referrer_id == current_user.id:
        return {"redeemed": False}

    already = supabase.table("referrals").select("id").eq("referred_id", current_user.id).execute()
    if already.data:
        return {"redeemed": False}

    supabase.table("referrals").insert({
        "referrer_id": referrer_id,
        "referred_id": current_user.id,
        "status": "pending",
    }).execute()
    logger.info("referral redeemed | referrer=%s referred=%s", referrer_id, current_user.id)
    return {"redeemed": True}
