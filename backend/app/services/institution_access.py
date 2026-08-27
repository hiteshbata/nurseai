"""Phase 1 institutional access foundation.

Effective module access = B2C plan access OR active institution grant.
An institution grant is valid only when:
  institution_members.status = 'active'
  AND institutions.status = 'active'
  AND institution_modules.enabled = true

This is the single read path for institution grants -- has_effective_module_access
in plan_gating.py (the actual enforcement point used by routers) calls
has_institution_module_access below rather than re-deriving this join anywhere
else. A user with no institution membership gets the B2C-only result untouched.
"""
from typing import Optional

from app.core.plans import PLAN_LIMITS

INSTITUTION_MODULES = ("speaking", "reading", "listening", "writing", "mock_tests")


def get_active_institution_module_access(supabase, user_id: str) -> dict:
    """Aggregated (OR'd) module grants + speaking quota across every
    institution `user_id` has an ACTIVE membership in, where the institution
    itself is ACTIVE. A normal B2C user with no membership gets
    {"modules": set(), "speaking_sessions_per_month": None} -- effective
    access then reduces to plan access alone."""
    memberships = (
        supabase.table("institution_members")
        .select("institution_id")
        .eq("user_id", user_id)
        .eq("status", "active")
        .execute()
    )
    institution_ids = {m["institution_id"] for m in (memberships.data or [])}
    if not institution_ids:
        return {"modules": set(), "speaking_sessions_per_month": None}

    institutions = (
        supabase.table("institutions")
        .select("id, speaking_sessions_per_month")
        .in_("id", institution_ids)
        .eq("status", "active")
        .execute()
    )
    active_institutions = institutions.data or []
    active_institution_ids = {row["id"] for row in active_institutions}
    if not active_institution_ids:
        return {"modules": set(), "speaking_sessions_per_month": None}

    modules = (
        supabase.table("institution_modules")
        .select("institution_id, module")
        .in_("institution_id", active_institution_ids)
        .eq("enabled", True)
        .execute()
    )
    enabled_modules = {row["module"] for row in (modules.data or [])}

    # Most generous quota wins if a user somehow holds more than one active
    # grant -- never silently pick an arbitrary one.
    speaking_quota: Optional[int] = None
    for row in active_institutions:
        q = row.get("speaking_sessions_per_month")
        if q is not None:
            speaking_quota = q if speaking_quota is None else max(speaking_quota, q)

    return {"modules": enabled_modules, "speaking_sessions_per_month": speaking_quota}


def has_institution_module_access(supabase, user_id: str, module: str) -> bool:
    access = get_active_institution_module_access(supabase, user_id)
    return module in access["modules"]


def get_effective_speaking_limit(supabase, user_id: str, plan: str) -> int:
    """Institution students must not inherit the B2C plan's speaking quota
    (e.g. Free's 3/month) -- an active institution grant that includes
    "speaking" replaces the plan limit entirely with the institution's own
    monthly quota. No institution grant (or one that excludes speaking):
    unchanged B2C behavior."""
    access = get_active_institution_module_access(supabase, user_id)
    if "speaking" in access["modules"] and access["speaking_sessions_per_month"] is not None:
        return access["speaking_sessions_per_month"]
    return PLAN_LIMITS.get(plan, 3)
