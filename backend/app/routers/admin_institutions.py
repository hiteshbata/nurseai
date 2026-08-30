"""Phase 5.1/5.2: internal staff institution management.

A staff-facing layer over the existing institution tables (institutions,
institution_members, institution_modules, institution_invites) and existing
institution services -- it does not replace or modify institution.py,
institutions.py, institution_access.py, or institution_admin.py. See
docs/PHASE5_INSTITUTION_ADMIN_SPEC.md.

Two role systems stay fully isolated: staff access here is gated purely by
require_analyst/require_admin (public.user_roles, admin.py) -- never by
require_active_institution_role (institution_members.role,
institution_admin.py). Staff routes are cross-tenant BY DESIGN (that is the
point of an internal admin tool); the per-route `institution_id` existence
check below is a target-validation check, not an authorization check.

Phase 5.2 adds create (POST) and configuration update (PATCH). Phase 5.3b
(see docs/superpowers/specs/2026-08-29-institution-phase5.3-admin-assignment.md)
adds staff role assignment (POST .../staff) -- teacher/institution_admin
only, resolved by email against Supabase Auth per that spec's Section 4.
Still not implemented: institution status-toggle endpoint, invite wrappers,
frontend create/assign UI, POST /institution/activate (membership
activation on sign-in stays out of scope for this endpoint -- see spec
Section 2/3).
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field

from app.core.config import settings
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.supabase import get_supabase
from app.routers.admin import _write_audit_log, require_admin, require_analyst
from app.routers.auth import UserInfo
from app.routers.institution import _invite_summary, _latest_speaking_scores
from app.routers.sessions import _usage_payload, get_month_start_utc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/institutions", tags=["admin"])

# Mirrors the institution_modules.module CHECK constraint
# (20260826000000_institution_foundation.sql) -- the single source of truth
# for which module values are valid, referenced by both request models below.
ModuleName = Literal["speaking", "reading", "listening", "writing", "mock_tests"]
MODULE_VALUES: tuple = ("speaking", "reading", "listening", "writing", "mock_tests")


def _get_institution_or_404(supabase, institution_id: str) -> dict:
    """Server-side existence check reused by every path-scoped route below.
    Not an authorization check -- staff can act on any institution by
    design -- only confirms the client-supplied id refers to a real row
    before any child-table read runs. 404 (not 403) on a miss, matching the
    convention already used by institution.py's revoke_institution_invite."""
    rows = (
        supabase.table("institutions")
        .select("id, name, slug, logo_url, status, contact_email, speaking_sessions_per_month, created_at")
        .eq("id", institution_id).execute()
    ).data
    if not rows:
        raise HTTPException(status_code=404, detail="Institution not found")
    return rows[0]


def _active_student_ids_by_institution(supabase, institution_ids: List[str]) -> Dict[str, List[str]]:
    """One grouped query, never one per institution."""
    if not institution_ids:
        return {}
    members = (
        supabase.table("institution_members")
        .select("institution_id, user_id")
        .in_("institution_id", institution_ids)
        .eq("role", "student").eq("status", "active").execute()
    ).data or []
    out: Dict[str, List[str]] = {}
    for m in members:
        out.setdefault(m["institution_id"], []).append(m["user_id"])
    return out


def _sessions_used_this_month_by_user(supabase, user_ids: List[str]) -> Dict[str, int]:
    """user_id -> sessions_used_this_month, reconciled the same way
    institution.py's overview does (stale reset_date -> 0, no write)."""
    if not user_ids:
        return {}
    profiles = (
        supabase.table("user_profiles")
        .select("user_id, plan, sessions_used_this_month, sessions_reset_date, bonus_sessions")
        .in_("user_id", user_ids).execute()
    ).data or []
    month_start = get_month_start_utc()
    return {
        p["user_id"]: _usage_payload(p, month_start, plan_limit=0)["sessions_used"]
        for p in profiles
    }


def _enabled_modules_by_institution(supabase, institution_ids: List[str]) -> Dict[str, List[str]]:
    if not institution_ids:
        return {}
    rows = (
        supabase.table("institution_modules")
        .select("institution_id, module")
        .in_("institution_id", institution_ids).eq("enabled", True).execute()
    ).data or []
    out: Dict[str, List[str]] = {}
    for r in rows:
        out.setdefault(r["institution_id"], []).append(r["module"])
    return {k: sorted(v) for k, v in out.items()}


def _admin_emails_by_institution(supabase, institution_ids: List[str]) -> Dict[str, List[str]]:
    """institution_id -> sorted list of active institution_admin emails.
    Two grouped queries (membership rows, then a single users lookup for
    every admin user_id found) -- never one users query per institution."""
    if not institution_ids:
        return {}
    rows = (
        supabase.table("institution_members")
        .select("institution_id, user_id")
        .in_("institution_id", institution_ids)
        .eq("role", "institution_admin").eq("status", "active").execute()
    ).data or []
    if not rows:
        return {}
    user_ids = sorted({r["user_id"] for r in rows})
    users = {
        u["id"]: u for u in (
            supabase.table("users").select("id, email").in_("id", user_ids).execute()
        ).data or []
    }
    out: Dict[str, List[str]] = {}
    for r in rows:
        email = users.get(r["user_id"], {}).get("email")
        if email:
            out.setdefault(r["institution_id"], []).append(email)
    return {k: sorted(v) for k, v in out.items()}


@router.get("")
def list_institutions(current_user: UserInfo = Depends(require_analyst)):
    """List page (spec Section 5). 5 grouped queries total for the whole
    list, each merged in Python by institution_id -- never one query per
    row."""
    supabase = get_supabase()
    institutions = (
        supabase.table("institutions")
        .select("id, name, slug, logo_url, status, speaking_sessions_per_month, created_at")
        .order("created_at", desc=True).execute()
    ).data or []
    if not institutions:
        return []

    institution_ids = [i["id"] for i in institutions]
    students_by_inst = _active_student_ids_by_institution(supabase, institution_ids)
    all_student_ids = [uid for ids in students_by_inst.values() for uid in ids]
    sessions_by_user = _sessions_used_this_month_by_user(supabase, all_student_ids)
    modules_by_inst = _enabled_modules_by_institution(supabase, institution_ids)
    admins_by_inst = _admin_emails_by_institution(supabase, institution_ids)

    result = []
    for inst in institutions:
        student_ids = students_by_inst.get(inst["id"], [])
        result.append({
            "id": inst["id"],
            "name": inst["name"],
            "slug": inst["slug"],
            "logo_url": inst.get("logo_url"),
            "status": inst["status"],
            "active_students": len(student_ids),
            "enabled_modules": modules_by_inst.get(inst["id"], []),
            "speaking_sessions_per_month": inst.get("speaking_sessions_per_month"),
            "sessions_this_month": sum(sessions_by_user.get(uid, 0) for uid in student_ids),
            "admin_emails": admins_by_inst.get(inst["id"], []),
            "created_at": inst.get("created_at"),
        })
    return result


@router.get("/{institution_id}")
def get_institution_detail(institution_id: str, current_user: UserInfo = Depends(require_analyst)):
    """Overview section of the detail page."""
    supabase = get_supabase()
    inst = _get_institution_or_404(supabase, institution_id)

    student_ids = _active_student_ids_by_institution(supabase, [institution_id]).get(institution_id, [])
    modules = _enabled_modules_by_institution(supabase, [institution_id]).get(institution_id, [])
    admin_emails = _admin_emails_by_institution(supabase, [institution_id]).get(institution_id, [])

    return {
        "id": inst["id"],
        "name": inst["name"],
        "slug": inst["slug"],
        "logo_url": inst.get("logo_url"),
        "status": inst["status"],
        "contact_email": inst.get("contact_email"),
        "speaking_sessions_per_month": inst.get("speaking_sessions_per_month"),
        "enabled_modules": modules,
        "active_student_count": len(student_ids),
        "admin_emails": admin_emails,
        "created_at": inst.get("created_at"),
    }


@router.get("/{institution_id}/students")
def get_institution_students(institution_id: str, current_user: UserInfo = Depends(require_analyst)):
    """Roster -- same fixed-query-shape/data-minimization contract as
    institution.py's self-service get_institution_students (one membership
    query, one users query, one profiles query, one submissions query, one
    quota lookup), staff-scoped from the path instead of the caller's own
    membership."""
    supabase = get_supabase()
    _get_institution_or_404(supabase, institution_id)

    members = (
        supabase.table("institution_members")
        .select("user_id, status, joined_at")
        .eq("institution_id", institution_id)
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
        .eq("id", institution_id).execute()
    ).data[0]
    quota = institution.get("speaking_sessions_per_month")
    speaking_enabled = bool((
        supabase.table("institution_modules")
        .select("enabled")
        .eq("institution_id", institution_id).eq("module", "speaking").eq("enabled", True).execute()
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


@router.get("/{institution_id}/usage")
def get_institution_usage(institution_id: str, current_user: UserInfo = Depends(require_analyst)):
    """Numbers only (spec Section 6/14) -- no charts/analytics in MVP."""
    supabase = get_supabase()
    inst = _get_institution_or_404(supabase, institution_id)

    student_ids = _active_student_ids_by_institution(supabase, [institution_id]).get(institution_id, [])
    sessions_by_user = _sessions_used_this_month_by_user(supabase, student_ids)
    modules = _enabled_modules_by_institution(supabase, [institution_id]).get(institution_id, [])

    return {
        "active_student_count": len(student_ids),
        "sessions_this_month": sum(sessions_by_user.values()),
        "speaking_sessions_per_month": inst.get("speaking_sessions_per_month"),
        "enabled_modules": modules,
    }


@router.get("/{institution_id}/admins")
def list_institution_admins(institution_id: str, current_user: UserInfo = Depends(require_analyst)):
    supabase = get_supabase()
    _get_institution_or_404(supabase, institution_id)

    rows = (
        supabase.table("institution_members")
        .select("user_id, status, joined_at")
        .eq("institution_id", institution_id).eq("role", "institution_admin").execute()
    ).data or []
    if not rows:
        return []

    user_ids = [r["user_id"] for r in rows]
    users = {
        u["id"]: u for u in (
            supabase.table("users").select("id, email, name").in_("id", user_ids).execute()
        ).data or []
    }
    return [
        {
            "email": users.get(r["user_id"], {}).get("email", ""),
            "name": users.get(r["user_id"], {}).get("name"),
            "status": r["status"],
            "joined_at": r.get("joined_at"),
        }
        for r in rows
    ]


@router.get("/{institution_id}/invites")
def list_institution_invites(institution_id: str, current_user: UserInfo = Depends(require_analyst)):
    """Staff view onto the same invite rows institutions.py/institution.py
    already manage -- reuses _invite_summary() verbatim so the "never the
    raw token" contract can't drift between the self-service and staff
    views."""
    supabase = get_supabase()
    _get_institution_or_404(supabase, institution_id)

    invites = (
        supabase.table("institution_invites")
        .select("id, status, max_uses, use_count, expires_at, created_at")
        .eq("institution_id", institution_id).execute()
    ).data or []
    return [_invite_summary(row) for row in invites]


# ── POST /admin/institutions, PATCH /admin/institutions/{id} (Phase 5.2) ──
# Configuration only: name/slug/logo_url/contact_email/status/modules/quota.
# No institution_admin assignment, no status-toggle endpoint, no invite
# wrappers -- those stay out of scope per spec Section 14/16.

class InstitutionCreate(BaseModel):
    name: str
    slug: str
    logo_url: Optional[str] = None
    contact_email: EmailStr
    status: Literal["active", "suspended"] = "active"
    modules: List[ModuleName] = Field(default_factory=list)
    speaking_sessions_per_month: int = Field(gt=0, default=20)


class InstitutionUpdate(BaseModel):
    """No `institution_id` field, deliberately -- the target institution
    comes only from the path parameter (see the route below), matching the
    InviteCreate convention in institutions.py of never declaring a field a
    client could use to smuggle in a value the server should own."""
    name: Optional[str] = None
    slug: Optional[str] = None
    logo_url: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    status: Optional[Literal["active", "suspended"]] = None
    modules: Optional[List[ModuleName]] = None
    speaking_sessions_per_month: Optional[int] = Field(gt=0, default=None)


def _sync_modules(
    supabase, institution_id: str, desired: List[str], current_user: UserInfo,
) -> None:
    """Full-replace: institution_modules ends up with enabled=true rows for
    exactly `desired` and no enabled=true row for anything else -- same
    "absent/disabled row == not enabled" convention list_institutions/
    get_institution_detail already read (_enabled_modules_by_institution
    filters WHERE enabled=True). Writes one institution_module_changed audit
    entry per module whose enabled state actually changes; a module already
    in its requested state is left untouched and unaudited (only mutations
    are logged, per spec Section 8)."""
    existing = {
        r["module"]: r["enabled"] for r in (
            supabase.table("institution_modules")
            .select("module, enabled")
            .eq("institution_id", institution_id).execute()
        ).data or []
    }
    desired_set = set(desired)
    for module in MODULE_VALUES:
        new_enabled = module in desired_set
        if existing.get(module, False) == new_enabled:
            continue
        supabase.table("institution_modules").upsert(
            {"institution_id": institution_id, "module": module, "enabled": new_enabled},
            on_conflict="institution_id,module",
        ).execute()
        _write_audit_log(
            supabase, current_user, "institution_module_changed", "institution",
            target_id=institution_id, detail={"module": module, "enabled": new_enabled},
        )


@router.post("", status_code=201)
def create_institution(req: InstitutionCreate, current_user: UserInfo = Depends(require_admin)):
    """Atomic institution + module-grant creation via the
    admin_create_institution Postgres function (Phase 5.2 migration) -- a
    plain INSERT into institutions followed by a separate INSERT per module
    is two supabase-py calls with no shared transaction; a module insert
    failing after the institutions row already committed would leave a
    half-configured institution behind. The RPC makes both inserts one
    statement/one transaction, matching the accept_institution_invite
    pattern already established in this codebase."""
    supabase = get_supabase()
    try:
        result = supabase.rpc("admin_create_institution", {
            "p_name": req.name,
            "p_slug": req.slug,
            "p_logo_url": req.logo_url,
            "p_contact_email": req.contact_email,
            "p_status": req.status,
            "p_quota": req.speaking_sessions_per_month,
            "p_modules": req.modules,
        }).execute()
    except Exception as e:
        # Same duplicate-key convention as reading.py's create_test and
        # admin.py's admin_create_scenario -- not a second error-handling style.
        if "duplicate key" in str(e).lower():
            raise HTTPException(status_code=409, detail=f'An institution with slug "{req.slug}" already exists')
        raise
    created = result.data[0]
    institution_id = created["id"]

    _write_audit_log(
        supabase, current_user, "institution_created", "institution",
        target_id=institution_id, target_label=req.name,
        detail={"slug": req.slug, "modules": req.modules, "speaking_sessions_per_month": req.speaking_sessions_per_month},
    )

    return {
        "id": institution_id,
        "name": req.name,
        "slug": req.slug,
        "logo_url": req.logo_url,
        "contact_email": req.contact_email,
        "status": req.status,
        "enabled_modules": sorted(req.modules),
        "speaking_sessions_per_month": req.speaking_sessions_per_month,
        "created_at": created["created_at"],
    }


@router.patch("/{institution_id}")
def update_institution(
    institution_id: str, req: InstitutionUpdate, current_user: UserInfo = Depends(require_admin),
):
    """Partial update. Only fields present in the request body change --
    unset (None) fields are left alone, same convention as
    admin.py:admin_update_scenario. `modules`, when present, is a full
    desired-enabled-set (see _sync_modules), not a delta."""
    supabase = get_supabase()
    before = _get_institution_or_404(supabase, institution_id)

    core_fields: Dict[str, Any] = {}
    if req.name is not None:
        core_fields["name"] = req.name
    if req.slug is not None:
        core_fields["slug"] = req.slug
    if req.logo_url is not None:
        core_fields["logo_url"] = req.logo_url
    if req.contact_email is not None:
        core_fields["contact_email"] = req.contact_email
    if req.status is not None:
        core_fields["status"] = req.status

    update_data = dict(core_fields)
    if req.speaking_sessions_per_month is not None:
        update_data["speaking_sessions_per_month"] = req.speaking_sessions_per_month

    if not update_data and req.modules is None:
        raise HTTPException(status_code=400, detail="No fields to update")

    if update_data:
        try:
            supabase.table("institutions").update(update_data).eq("id", institution_id).execute()
        except Exception as e:
            if "duplicate key" in str(e).lower():
                raise HTTPException(status_code=409, detail=f'An institution with slug "{req.slug}" already exists')
            raise

        if core_fields:
            _write_audit_log(
                supabase, current_user, "institution_updated", "institution",
                target_id=institution_id, target_label=core_fields.get("name", before["name"]),
                detail=core_fields,
            )
        if "speaking_sessions_per_month" in update_data and update_data["speaking_sessions_per_month"] != before.get("speaking_sessions_per_month"):
            _write_audit_log(
                supabase, current_user, "institution_quota_changed", "institution",
                target_id=institution_id,
                detail={"old_quota": before.get("speaking_sessions_per_month"), "new_quota": update_data["speaking_sessions_per_month"]},
            )

    if req.modules is not None:
        _sync_modules(supabase, institution_id, req.modules, current_user)

    return get_institution_detail(institution_id, current_user=current_user)


# ── POST /admin/institutions/{id}/staff (Phase 5.3b) ──────────────────────
# Staff-only teacher/institution_admin assignment by email. Never gated by
# require_active_institution_role, never reachable from /institution/* --
# same cross-tenant require_admin trust boundary as create_institution/
# update_institution above. "student" is not a valid role here; that stays
# on institution.py's token-invite flow (accept_institution_invite),
# unmodified by this endpoint.

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StaffAssign(BaseModel):
    email: EmailStr
    role: Literal["teacher", "institution_admin"]


staff_assign_rate_limiter = SlidingWindowRateLimiter(
    max_calls=20, window_seconds=3600, name="admin_institutions:staff_assign"
)


def _resolve_auth_user(supabase, email: str):
    """(user_id, auth_state) for `email`, auth_state in "not_found",
    "confirmed", "unconfirmed". Uses generate_link(type="recovery") as the
    non-mutating existence probe -- never sends an email, requires an
    existing user (errors "User with this email not found" otherwise) --
    verified against the live QA Supabase Auth API in Phase 5.3a. Any other
    exception is a genuine Auth-API failure, not a "doesn't exist" signal,
    and is re-raised for the caller to surface as a retryable error."""
    try:
        resp = supabase.auth.admin.generate_link({"type": "recovery", "email": email})
    except Exception as e:
        if "not found" in str(e).lower():
            return None, "not_found"
        raise
    user = resp.user
    if user.email_confirmed_at:
        return user.id, "confirmed"
    return user.id, "unconfirmed"


def _is_concurrent_account_creation_race(exc: Exception) -> bool:
    """True only for Supabase Auth's exact "Database error saving new user"
    signature -- the specific 500 GoTrue returns to the LOSING side of two
    concurrent invite_user_by_email calls for the same brand-new email, when
    its own users.email unique constraint fires (observed live in QA Phase
    5.3b). Narrow substring match, same convention as _resolve_auth_user's
    "not found" check above -- anything else (rate limit, network error,
    a genuine Auth outage) must keep surfacing as 502, not be reclassified."""
    return "database error saving new user" in str(exc).lower()


def _other_active_staff_institution(supabase, user_id: str, institution_id: str) -> Optional[str]:
    """id of another institution where `user_id` already holds an active
    teacher/institution_admin membership, or None. Best-effort, not
    row-locked (spec Section 6) -- exists to give the admin an earlier,
    clearer signal than require_active_institution_role's later 409."""
    rows = (
        supabase.table("institution_members")
        .select("institution_id")
        .eq("user_id", user_id).eq("status", "active")
        .in_("role", ["teacher", "institution_admin"])
        .execute()
    ).data or []
    for r in rows:
        if r["institution_id"] != institution_id:
            return r["institution_id"]
    return None


@router.post("/{institution_id}/staff", status_code=201)
def assign_institution_staff(
    institution_id: str, req: StaffAssign, http_response: Response, current_user: UserInfo = Depends(require_admin),
):
    if staff_assign_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many requests. Try again shortly.")

    supabase = get_supabase()
    _get_institution_or_404(supabase, institution_id)

    try:
        user_id, auth_state = _resolve_auth_user(supabase, req.email)
    except Exception:
        logger.exception("institution staff assignment: auth probe failed | email=%s", req.email)
        raise HTTPException(status_code=502, detail="Could not verify account status. Try again.")

    invite_warning = None
    if user_id is None:
        try:
            invite_resp = supabase.auth.admin.invite_user_by_email(
                req.email, {"redirect_to": f"{settings.FRONTEND_URL}/auth/callback"},
            )
        except Exception as e:
            if _is_concurrent_account_creation_race(e):
                # Two concurrent requests for the SAME brand-new email both
                # passed _resolve_auth_user's pre-invite existence check (no
                # Auth user yet), then raced inside Supabase Auth's own user
                # creation -- the loser hits Auth's users.email unique
                # constraint and GoTrue surfaces it as a generic 500 with
                # this exact message (observed live in QA Phase 5.3b), not
                # as a structured "already exists" error. No membership row
                # or Auth user is created on this path, so there is nothing
                # to roll back -- the client should simply retry, which will
                # now resolve the winner's Auth user via generate_link.
                logger.info(
                    "institution staff assignment: concurrent account creation race | email=%s", req.email,
                )
                raise HTTPException(status_code=409, detail={"error": "concurrent_account_creation"})
            logger.exception("institution staff assignment: invite_user_by_email failed | email=%s", req.email)
            raise HTTPException(status_code=502, detail="Could not create account. Try again.")
        user_id = invite_resp.user.id
        membership_status = "active"
        joined_at = _now_iso()
    elif auth_state == "confirmed":
        membership_status = "active"
        joined_at = _now_iso()
    else:
        # Existing, unconfirmed: resend is best-effort -- membership is
        # active regardless of whether the resend succeeds (spec Section 6).
        # The staff assignment itself is the authorization decision; Auth
        # invite state only controls the user's own login/password setup.
        try:
            supabase.auth.admin.invite_user_by_email(
                req.email, {"redirect_to": f"{settings.FRONTEND_URL}/auth/callback"},
            )
        except Exception:
            invite_warning = "invite_resend_failed"
        membership_status = "active"
        joined_at = _now_iso()

    existing = (
        supabase.table("institution_members")
        .select("role, status")
        .eq("institution_id", institution_id).eq("user_id", user_id).execute()
    ).data
    if existing:
        row = existing[0]
        if row["status"] == "revoked":
            raise HTTPException(status_code=409, detail={"error": "revoked_membership"})
        if row["status"] == "invited":
            raise HTTPException(status_code=409, detail={"error": "pending_membership"})
        if row["role"] == "institution_admin":
            http_response.status_code = 200
            return {
                "status": "already_assigned", "institution_id": institution_id,
                "email": req.email, "role": row["role"],
            }
        if row["role"] == "teacher":
            raise HTTPException(status_code=409, detail={"error": "already_teacher"})
        raise HTTPException(status_code=409, detail={"error": "already_student"})

    other = _other_active_staff_institution(supabase, user_id, institution_id)
    if other:
        raise HTTPException(status_code=409, detail={"error": "already_staff_elsewhere", "institution_id": other})

    insert_row = {
        "institution_id": institution_id,
        "user_id": user_id,
        "role": req.role,
        "status": membership_status,
        "invited_by": current_user.id,
        "joined_at": joined_at,
    }

    def _insert():
        return supabase.table("institution_members").insert(insert_row).execute()

    try:
        _insert()
    except Exception as e:
        if "duplicate key" in str(e).lower():
            raise HTTPException(status_code=409, detail={"error": "already_assigned"})
        try:
            _insert()
        except Exception:
            _write_audit_log(
                supabase, current_user, "institution_staff_assignment_failed", "institution_member",
                target_id=institution_id, target_label=req.email,
                detail={"email": req.email, "role": req.role, "auth_state": auth_state},
            )
            raise HTTPException(status_code=500, detail="Assignment could not be completed. Retry.")

    _write_audit_log(
        supabase, current_user, "institution_staff_assigned", "institution_member",
        target_id=institution_id, target_label=req.email,
        detail={"email": req.email, "role": req.role, "auth_state": auth_state, "membership_status": membership_status},
    )

    http_response.status_code = 201
    result = {
        "institution_id": institution_id, "email": req.email, "role": req.role,
        "auth_state": auth_state, "status": membership_status,
    }
    if invite_warning:
        result["warning"] = invite_warning
    return result
