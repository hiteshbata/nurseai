import logging

from fastapi import APIRouter, Depends, HTTPException
from app.core.supabase import get_supabase
from app.routers.auth import get_current_user, UserInfo
from app.schemas.onboarding import OnboardingCreate, OnboardingResponse
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/status")
def get_onboarding_status(
    current_user: UserInfo = Depends(get_current_user),
):
    supabase = get_supabase()
    try:
        data = supabase.table("user_profiles").select("*").eq("user_id", current_user.id).execute()
    except Exception:
        logger.error("Failed to fetch onboarding status for user_id=%s", current_user.id, exc_info=True)
        raise HTTPException(status_code=503, detail="Could not check onboarding status. Please try again.")

    if data.data:
        return data.data[0]
    return {"onboarding_completed": False}


@router.post("/complete", response_model=OnboardingResponse)
def complete_onboarding(
    payload: OnboardingCreate,
    current_user: UserInfo = Depends(get_current_user),
):
    supabase = get_supabase()
    now = datetime.utcnow().isoformat()

    body = {
        "user_id": current_user.id,
        "onboarding_completed": payload.onboarding_completed,
        "exam_date": payload.exam_date.isoformat() if payload.exam_date else None,
        "target_band": payload.target_band,
        "baseline_score": payload.baseline_score,
        "has_taken_oet": payload.has_taken_oet,
        "previous_band": payload.previous_band,
        "destination_country": payload.destination_country,
        "days_per_week": payload.days_per_week,
        "state": payload.state,
        "qualification": payload.qualification,
        "years_of_experience": payload.years_of_experience,
        "nursing_specialty": payload.nursing_specialty,
        "updated_at": now,
    }

    result = supabase.table("user_profiles").upsert(body, on_conflict="user_id").execute()
    return result.data[0]


@router.put("/baseline")
def save_baseline_score(
    baseline_score: float,
    current_user: UserInfo = Depends(get_current_user),
):
    supabase = get_supabase()
    now = datetime.utcnow().isoformat()

    supabase.table("user_profiles").upsert({
        "user_id": current_user.id,
        "baseline_score": baseline_score,
        "updated_at": now,
    }, on_conflict="user_id").execute()

    return {"baseline_score": baseline_score}
