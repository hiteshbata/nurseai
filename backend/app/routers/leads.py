import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from app.core.supabase import get_supabase
from app.core.captcha import verify_captcha
from app.core.rate_limit import SlidingWindowRateLimiter
from app.routers.auth import _client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leads", tags=["leads"])

# Unauthenticated, public-facing form -- cap submissions per IP so it can't be
# used to spam the institute_leads table or flood support's inbox equivalent.
_institute_lead_rate_limiter = SlidingWindowRateLimiter(5, 3600, name="leads:institute")


class InstituteLeadCreate(BaseModel):
    institute_name: str = Field(min_length=1, max_length=200)
    contact_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    student_count: int | None = Field(default=None, ge=1, le=100_000)
    message: str | None = Field(default=None, max_length=2000)
    captcha_token: Optional[str] = None


@router.post("/institute", status_code=201)
async def create_institute_lead(lead: InstituteLeadCreate, request: Request):
    client_ip = _client_ip(request)
    if _institute_lead_rate_limiter.is_rate_limited(client_ip):
        raise HTTPException(status_code=429, detail="Too many submissions — please try again later.")
    if not await verify_captcha(lead.captcha_token, client_ip):
        raise HTTPException(status_code=400, detail="Captcha verification failed.")

    try:
        get_supabase().table("institute_leads").insert(lead.model_dump(exclude={"captcha_token"})).execute()
    except Exception:
        logger.exception("Failed to store institute lead")
        raise HTTPException(status_code=500, detail="Could not submit your request — please try again.")

    return {"success": True}
