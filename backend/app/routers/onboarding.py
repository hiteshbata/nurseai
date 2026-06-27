from fastapi import APIRouter, Depends
from app.core.supabase import get_supabase
from app.routers.auth import get_current_user, UserInfo
from app.schemas.onboarding import OnboardingCreate, OnboardingResponse
from datetime import datetime

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/status")
def get_onboarding_status(
    current_user: UserInfo = Depends(get_current_user),
):
    supabase = get_supabase()
    try:
        data = supabase.table("user_profiles").select("*").eq("user_id", current_user.id).execute()
        if data.data:
            return data.data[0]
    except Exception:
        pass
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
        "updated_at": now,
    }

    try:
        existing = supabase.table("user_profiles").select("user_id").eq("user_id", current_user.id).execute()
    except Exception:
        return OnboardingResponse(user_id=current_user.id, onboarding_completed=True)

    if existing.data:
        supabase.table("user_profiles").update(body).eq("user_id", current_user.id).execute()
    else:
        body["created_at"] = now
        supabase.table("user_profiles").insert(body).execute()

    result = supabase.table("user_profiles").select("*").eq("user_id", current_user.id).execute()
    return result.data[0]


@router.put("/baseline")
def save_baseline_score(
    baseline_score: float,
    current_user: UserInfo = Depends(get_current_user),
):
    supabase = get_supabase()
    now = datetime.utcnow().isoformat()

    existing = supabase.table("user_profiles").select("user_id").eq("user_id", current_user.id).execute()
    if existing.data:
        supabase.table("user_profiles").update({
            "baseline_score": baseline_score,
            "updated_at": now,
        }).eq("user_id", current_user.id).execute()
    else:
        supabase.table("user_profiles").insert({
            "user_id": current_user.id,
            "baseline_score": baseline_score,
            "onboarding_completed": False,
            "has_taken_oet": False,
            "created_at": now,
            "updated_at": now,
        }).execute()

    return {"baseline_score": baseline_score}
