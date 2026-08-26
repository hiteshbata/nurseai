import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.supabase import get_supabase
from app.routers.admin import require_admin, _write_audit_log
from app.routers.auth import UserInfo, _client_ip

router = APIRouter(prefix="/institutions", tags=["institutions"])


class InviteCreate(BaseModel):
    """No `role` field, deliberately -- Phase 2 only issues student
    invitations. The endpoint below always writes role="student"; there is
    nothing here for a client to override it with."""
    institution_id: str
    max_uses: Optional[int] = None
    expires_at: Optional[datetime] = None

    @field_validator("max_uses")
    @classmethod
    def _max_uses_positive_or_none(cls, v):
        if v is not None and v < 1:
            raise ValueError("max_uses must be null (unlimited) or >= 1")
        return v

    @field_validator("expires_at")
    @classmethod
    def _expires_at_in_future(cls, v):
        if v is not None:
            check_time = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
            if check_time <= datetime.now(timezone.utc):
                raise ValueError("expires_at must be in the future")
        return v


@router.post("/invites")
def create_institution_invite(
    req: InviteCreate,
    current_user: UserInfo = Depends(require_admin),
):
    """Staff-only. Generates a bearer join token for an existing, active
    institution. Institution + module rows are created directly in Supabase
    for Phase 2 (see spec 2026-08-26 §5.4) -- this endpoint only mints
    invites, and only ever for role="student" (see InviteCreate)."""
    supabase = get_supabase()

    institutions = (
        supabase.table("institutions").select("id, status")
        .eq("id", req.institution_id).execute()
    )
    if not institutions.data:
        raise HTTPException(status_code=404, detail="Institution not found")
    if institutions.data[0]["status"] != "active":
        raise HTTPException(status_code=400, detail="Institution is not active")

    token = secrets.token_urlsafe(24)
    row = {
        "institution_id": req.institution_id,
        "token": token,
        "role": "student",
        "max_uses": req.max_uses,
        "expires_at": req.expires_at.isoformat() if req.expires_at else None,
        "created_by": current_user.id,
    }
    result = supabase.table("institution_invites").insert(row).execute()
    created = result.data[0]

    _write_audit_log(
        supabase, current_user, "institution_invite_created", "institution_invite",
        target_id=created["id"], target_label=req.institution_id,
    )

    return {
        "id": created["id"],
        "token": created["token"],
        "max_uses": created.get("max_uses"),
        "expires_at": created.get("expires_at"),
    }


preview_rate_limiter = SlidingWindowRateLimiter(
    max_calls=30, window_seconds=60, name="institution_invite_preview"
)

_INVITE_NOT_FOUND = HTTPException(
    status_code=404, detail="Invitation not found or no longer valid"
)


@router.get("/invites/{token}")
def get_invite_preview(token: str, request: Request):
    """Public, token-gated. Never returns the raw token or any internal id --
    see spec 2026-08-26 §5.2 for the exact allow-list."""
    if preview_rate_limiter.is_rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many requests. Try again shortly.")

    supabase = get_supabase()
    # Explicit, minimal column lists -- not select("*") -- even though the
    # response below is already allow-listed. Keeps the DB read itself from
    # ever pulling token/id/role/created_by/created_at or institution
    # contact_email/speaking_sessions_per_month/created_at, regardless of
    # what the response-building code does later.
    invites = (
        supabase.table("institution_invites")
        .select("institution_id, status, expires_at, max_uses, use_count")
        .eq("token", token).eq("status", "active").execute()
    )
    if not invites.data:
        raise _INVITE_NOT_FOUND
    invite = invites.data[0]

    if invite.get("expires_at"):
        expires_at = datetime.fromisoformat(invite["expires_at"].replace("Z", "+00:00"))
        if expires_at <= datetime.now(timezone.utc):
            raise _INVITE_NOT_FOUND

    max_uses = invite.get("max_uses")
    if max_uses is not None and invite.get("use_count", 0) >= max_uses:
        raise _INVITE_NOT_FOUND

    institutions = (
        supabase.table("institutions")
        .select("name, logo_url, status")
        .eq("id", invite["institution_id"]).eq("status", "active").execute()
    )
    if not institutions.data:
        raise _INVITE_NOT_FOUND
    institution = institutions.data[0]

    modules = (
        supabase.table("institution_modules")
        .select("module")
        .eq("institution_id", invite["institution_id"]).eq("enabled", True).execute()
    )

    return {
        "institution_name": institution["name"],
        "logo_url": institution.get("logo_url"),
        "modules": [m["module"] for m in modules.data],
        "expires_at": invite.get("expires_at"),
    }
