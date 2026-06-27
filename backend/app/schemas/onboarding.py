from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional


class OnboardingCreate(BaseModel):
    exam_date: Optional[date] = None
    target_band: Optional[str] = None
    baseline_score: Optional[float] = None
    has_taken_oet: bool = False
    previous_band: Optional[str] = None
    destination_country: Optional[str] = None
    days_per_week: Optional[int] = None
    onboarding_completed: bool = True


class OnboardingResponse(BaseModel):
    id: str
    user_id: str
    onboarding_completed: bool
    exam_date: Optional[date] = None
    target_band: Optional[str] = None
    baseline_score: Optional[float] = None
    has_taken_oet: bool = False
    previous_band: Optional[str] = None
    destination_country: Optional[str] = None
    days_per_week: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
