import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.core.supabase import get_supabase
from app.routers.admin import require_admin, _write_audit_log
from app.routers.auth import UserInfo

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
