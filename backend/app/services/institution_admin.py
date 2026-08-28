"""Phase 4 institution-admin authorization.

Resolves a single (institution_id, role) scope from the caller's OWN active
membership -- never from a client-supplied institution_id, and never from
Phase 3's "oldest institution" onboarding-display pick (that rule has no
concept of role and exists only to choose what to show, not what to
authorize). See docs/superpowers/specs/2026-08-28-institution-phase4-admin.md
Section 3 for the full design rationale.
"""
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from supabase import Client

from app.core.supabase import get_supabase
from app.routers.auth import UserInfo, get_current_user

ROLE_RANK = {"student": 0, "teacher": 1, "institution_admin": 2}


@dataclass
class InstitutionScope:
    institution_id: str
    role: str


def get_qualifying_memberships(supabase, user_id: str, min_role: str) -> list:
    """Active memberships in active institutions where role >= min_role.
    Returns [{"institution_id", "role"}, ...]. Same two-query shape as
    institution_access._active_institutions (membership rows, then filter
    to active institutions) -- not reused directly because that helper
    aggregates across every membership regardless of role, which is the
    wrong contract for authorization (see module docstring)."""
    min_rank = ROLE_RANK[min_role]
    memberships = (
        supabase.table("institution_members")
        .select("institution_id, role")
        .eq("user_id", user_id)
        .eq("status", "active")
        .execute()
    )
    candidates = [
        m for m in (memberships.data or [])
        if ROLE_RANK[m["role"]] >= min_rank
    ]
    if not candidates:
        return []

    institution_ids = {m["institution_id"] for m in candidates}
    active_institutions = (
        supabase.table("institutions")
        .select("id")
        .in_("id", list(institution_ids))
        .eq("status", "active")
        .execute()
    )
    active_ids = {row["id"] for row in (active_institutions.data or [])}

    return [
        {"institution_id": m["institution_id"], "role": m["role"]}
        for m in candidates
        if m["institution_id"] in active_ids
    ]


def require_active_institution_role(min_role: str):
    """FastAPI dependency factory. Zero qualifying memberships -> 403. Two
    or more -> 409 with the candidate institution ids (never a silent
    pick). Exactly one -> that scope."""
    def dependency(
        current_user: UserInfo = Depends(get_current_user),
        supabase: Client = Depends(get_supabase),
    ) -> InstitutionScope:
        matches = get_qualifying_memberships(supabase, current_user.id, min_role)
        if not matches:
            raise HTTPException(status_code=403, detail="No qualifying institution role.")
        if len(matches) > 1:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "multiple_qualifying_institutions",
                    "institutions": [m["institution_id"] for m in matches],
                },
            )
        m = matches[0]
        return InstitutionScope(institution_id=m["institution_id"], role=m["role"])
    return dependency
