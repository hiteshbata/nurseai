"""Phase 4: institution-admin dashboard (overview, roster, invites).

Every route resolves its institution scope from the caller's own active,
role-qualifying membership via require_active_institution_role -- never
from a client-supplied institution_id/role/user_id. See
docs/superpowers/specs/2026-08-28-institution-phase4-admin.md.
"""
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.core.config import settings
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.supabase import get_supabase
from app.routers.admin import _write_audit_log
from app.routers.auth import UserInfo, get_current_user
from app.routers.sessions import get_month_start_utc, _usage_payload
from app.services.institution_admin import InstitutionScope, require_active_institution_role

router = APIRouter(prefix="/institution", tags=["institution"])

require_teacher = require_active_institution_role("teacher")
require_institution_admin = require_active_institution_role("institution_admin")

# Defense against a compromised/abused admin credential minting invites in a
# loop -- not a substitute for the authorization check above, and not a cap
# on how many active invites an institution may hold.
invite_create_rate_limiter = SlidingWindowRateLimiter(
    max_calls=20, window_seconds=3600, name="institution:invite_create"
)


@router.get("/overview")
def get_institution_overview(scope: InstitutionScope = Depends(require_teacher)):
    supabase = get_supabase()

    institutions = (
        supabase.table("institutions")
        .select("name, logo_url, speaking_sessions_per_month")
        .eq("id", scope.institution_id).execute()
    )
    institution = institutions.data[0]

    members = (
        supabase.table("institution_members")
        .select("role, status")
        .eq("institution_id", scope.institution_id).execute()
    ).data or []
    member_counts: dict = {}
    for m in members:
        key = f"{m['role']}_{m['status']}"
        member_counts[key] = member_counts.get(key, 0) + 1

    modules = (
        supabase.table("institution_modules")
        .select("module")
        .eq("institution_id", scope.institution_id).eq("enabled", True).execute()
    ).data or []

    student_user_ids = [m["user_id"] for m in (
        supabase.table("institution_members")
        .select("user_id")
        .eq("institution_id", scope.institution_id)
        .eq("role", "student").eq("status", "active").execute()
    ).data or []]

    month_start = get_month_start_utc()
    sessions_used_total = 0
    if student_user_ids:
        profiles = (
            supabase.table("user_profiles")
            .select("user_id, plan, sessions_used_this_month, sessions_reset_date, bonus_sessions")
            .in_("user_id", student_user_ids).execute()
        ).data or []
        sessions_used_total = sum(
            _usage_payload(p, month_start, plan_limit=0)["sessions_used"] for p in profiles
        )

    return {
        "name": institution["name"],
        "logo_url": institution.get("logo_url"),
        "member_counts": member_counts,
        "modules": sorted(m["module"] for m in modules),
        "sessions_used_this_month": sessions_used_total,
        "speaking_sessions_per_month": institution.get("speaking_sessions_per_month"),
        "active_student_count": len(student_user_ids),
        # Caller's own resolved role (teacher/institution_admin) -- frontend
        # nav-visibility gating (e.g. hide Invitations from teachers) has no
        # other source for this; the backend authorization boundary in
        # require_active_institution_role is unaffected either way.
        "role": scope.role,
    }


@router.get("/students")
def get_institution_students(scope: InstitutionScope = Depends(require_teacher)):
    """Read-only roster. Fixed query pattern regardless of student count --
    one membership query, one users query, one profiles query, one
    submissions query, plus the institution's own speaking-quota lookup
    (institutions + institution_modules) -- never a per-student query. See
    docs/superpowers/specs/2026-08-28-institution-phase4-admin.md Section 10.

    Deliberately omits user_id/plan/subscription/bonus_sessions/
    institution_id from the response (data-minimization, spec Section 2) --
    the frontend roster has no use for them."""
    supabase = get_supabase()

    members = (
        supabase.table("institution_members")
        .select("user_id, status, joined_at")
        .eq("institution_id", scope.institution_id)
        .eq("role", "student").execute()
    ).data or []
    if not members:
        return []
    members.sort(key=lambda m: m.get("joined_at") or "", reverse=True)

    user_ids = [m["user_id"] for m in members]
    users = {
        u["id"]: u for u in (
            supabase.table("users").select("id, email, name").in_("id", user_ids).execute()
        ).data or []
    }
    profiles = {
        p["user_id"]: p for p in (
            supabase.table("user_profiles")
            .select("user_id, plan, sessions_used_this_month, sessions_reset_date, bonus_sessions")
            .in_("user_id", user_ids).execute()
        ).data or []
    }

    institution = (
        supabase.table("institutions")
        .select("speaking_sessions_per_month")
        .eq("id", scope.institution_id).execute()
    ).data[0]
    quota = institution.get("speaking_sessions_per_month")
    speaking_enabled = bool((
        supabase.table("institution_modules")
        .select("enabled")
        .eq("institution_id", scope.institution_id).eq("module", "speaking").eq("enabled", True).execute()
    ).data)

    latest_scores = _latest_speaking_scores(supabase, user_ids)

    month_start = get_month_start_utc()
    roster = []
    for m in members:
        user = users.get(m["user_id"], {})
        profile = profiles.get(m["user_id"], {})
        sessions_used = _usage_payload(profile, month_start, plan_limit=0)["sessions_used"]

        sessions_remaining = None
        if speaking_enabled and quota is not None:
            sessions_remaining = max(quota - sessions_used, 0)

        roster.append({
            "name": user.get("name") or None,
            "email": user.get("email") or "",
            "status": m["status"],
            "joined_at": m.get("joined_at"),
            "sessions_used_this_month": sessions_used,
            "sessions_remaining": sessions_remaining,
            "latest_speaking_score": latest_scores.get(m["user_id"]),
        })
    return roster


def _latest_speaking_scores(supabase, user_ids: list) -> dict:
    """user_id -> score of that user's most recent speaking submission
    (None if they have none). Reduced in Python from one batched query --
    never one submission query per student."""
    if not user_ids:
        return {}
    submissions = (
        supabase.table("submissions")
        .select("user_id, score, created_at")
        .eq("module", "speaking").in_("user_id", user_ids).execute()
    ).data or []
    latest: dict = {}
    for s in submissions:
        current = latest.get(s["user_id"])
        if current is None or (s.get("created_at") or "") > (current.get("created_at") or ""):
            latest[s["user_id"]] = s
    return {uid: row["score"] for uid, row in latest.items()}


@router.get("/invites")
def list_institution_invites(scope: InstitutionScope = Depends(require_institution_admin)):
    """Lifecycle/management view only -- never the raw token, role, or
    institution_id (all already implied by the caller's own scope). The
    token is returned exactly once, by create_institution_invite below."""
    supabase = get_supabase()
    invites = (
        supabase.table("institution_invites")
        .select("id, status, max_uses, use_count, expires_at, created_at")
        .eq("institution_id", scope.institution_id).execute()
    )
    return [_invite_summary(row) for row in (invites.data or [])]


def _invite_summary(row: dict) -> dict:
    max_uses = row.get("max_uses")
    use_count = row.get("use_count") or 0
    remaining_uses = None if max_uses is None else max(max_uses - use_count, 0)
    return {
        "id": row["id"],
        "status": row["status"],
        "max_uses": max_uses,
        "use_count": use_count,
        "remaining_uses": remaining_uses,
        "expires_at": row.get("expires_at"),
        "created_at": row.get("created_at"),
    }


class InviteCreate(BaseModel):
    """No `role` field, deliberately -- Phase 4 institution admins may only
    create student invitations (spec Section 0b). The endpoint below always
    writes role="student"; there is nothing here for a client to override
    it with. No `institution_id` field either -- scope is server-resolved,
    never client-supplied."""
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


@router.post("/invites", status_code=201)
def create_institution_invite(
    req: InviteCreate,
    scope: InstitutionScope = Depends(require_institution_admin),
    current_user: UserInfo = Depends(get_current_user),
):
    if invite_create_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many requests. Try again shortly.")

    supabase = get_supabase()
    token = secrets.token_urlsafe(24)
    row = {
        "institution_id": scope.institution_id,
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
        target_id=created["id"], target_label=scope.institution_id,
    )

    # Server-constructed from the configured FRONTEND_URL (per-environment --
    # see app/core/config.py) -- never a client-supplied origin, so this
    # can't be turned into an open redirect / phishing link.
    return {
        "id": created["id"],
        "token": created["token"],
        "join_url": f"{settings.FRONTEND_URL}/join/{created['token']}",
        "role": "student",
        "max_uses": created.get("max_uses"),
        "expires_at": created.get("expires_at"),
    }


@router.post("/invites/{invite_id}/revoke")
def revoke_institution_invite(
    invite_id: str,
    scope: InstitutionScope = Depends(require_institution_admin),
    current_user: UserInfo = Depends(get_current_user),
):
    """Ownership-filtered by scope.institution_id, not just invite_id -- an
    admin of Institution A must not be able to revoke Institution B's
    invite by guessing/enumerating {invite_id}. Generic 404 (not 403) so a
    mismatch can't be distinguished from "doesn't exist" (spec 5.5/8)."""
    supabase = get_supabase()
    invites = (
        supabase.table("institution_invites")
        .select("id")
        .eq("id", invite_id).eq("institution_id", scope.institution_id).execute()
    )
    if not invites.data:
        raise HTTPException(status_code=404, detail="Invitation not found")

    supabase.table("institution_invites").update({"status": "revoked"}).eq("id", invite_id).execute()

    _write_audit_log(
        supabase, current_user, "institution_invite_revoked", "institution_invite",
        target_id=invite_id, target_label=scope.institution_id,
    )

    return {"status": "revoked"}
