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


def _active_institutions(supabase, user_id: str) -> list:
    """Institution rows (id, speaking_sessions_per_month) for every
    institution `user_id` has an ACTIVE membership in AND that is itself
    ACTIVE. Single query pair reused by get_active_institution_module_access
    and is_active_institution_member so the membership+institution join
    isn't re-derived at each call site."""
    memberships = (
        supabase.table("institution_members")
        .select("institution_id")
        .eq("user_id", user_id)
        .eq("status", "active")
        .execute()
    )
    institution_ids = {m["institution_id"] for m in (memberships.data or [])}
    if not institution_ids:
        return []

    institutions = (
        supabase.table("institutions")
        .select("id, name, logo_url, speaking_sessions_per_month, created_at")
        .in_("id", institution_ids)
        .eq("status", "active")
        .execute()
    )
    return institutions.data or []


def is_active_institution_member(supabase, user_id: str) -> bool:
    """True if `user_id` has at least one active institution_members row
    whose institution is itself active. Used to suppress the generic B2C
    free-trial/lifetime-attempt bypass for institution students -- their
    module access is governed entirely by their institution's module grants
    (see get_active_institution_module_access), not by the free-tier taste
    given to ordinary B2C free users. A suspended institution or a
    revoked/pending membership does NOT count -- those users fall back to
    normal B2C free-trial behavior, same as has_institution_module_access."""
    return bool(_active_institutions(supabase, user_id))


def get_active_institution_module_access(supabase, user_id: str) -> dict:
    """Aggregated (OR'd) module grants + speaking quota across every
    institution `user_id` has an ACTIVE membership in, where the institution
    itself is ACTIVE. A normal B2C user with no membership gets
    {"modules": set(), "speaking_sessions_per_month": None} -- effective
    access then reduces to plan access alone."""
    active_institutions = _active_institutions(supabase, user_id)
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


def get_institution_onboarding_context(supabase, user_id: str) -> Optional[dict]:
    """Server-derived institution display context for onboarding (name,
    logo_url, enabled modules). Returns None for a normal B2C user or a
    user with no active institution grant.

    A user can only join via a single invite token today (Phase 2 join
    flow), but the schema allows more than one active membership -- if that
    ever happens, the OLDEST active institution (by institutions.created_at)
    is shown, matching "the institution you joined first" rather than an
    arbitrary row order. Phase 3 does not build any UI for switching
    between multiple institutions."""
    active_institutions = _active_institutions(supabase, user_id)
    if not active_institutions:
        return None

    institution = min(active_institutions, key=lambda row: row.get("created_at") or "")

    modules = (
        supabase.table("institution_modules")
        .select("module")
        .eq("institution_id", institution["id"])
        .eq("enabled", True)
        .execute()
    )
    enabled_modules = sorted({row["module"] for row in (modules.data or [])})

    return {
        "name": institution["name"],
        "logo_url": institution.get("logo_url"),
        "modules": enabled_modules,
    }


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
