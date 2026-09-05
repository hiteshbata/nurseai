from fastapi import APIRouter, Depends
from supabase import Client

from app.core.plans import PLANS, is_strict_upgrade
from app.core.supabase import get_supabase
from app.routers.auth import UserInfo, get_current_user
from app.services.institution_access import (
    get_active_institution_module_access,
    get_institution_onboarding_context,
    is_active_institution_member,
)
from app.services.institution_admin import get_qualifying_memberships
from app.services.plan_gating import (
    get_plan_from_profile,
    has_effective_module_access,
    has_pronunciation_access,
)

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("/")
def get_plans():
    return {"plans": PLANS}


@router.get("/me")
def get_my_plan(
    current_user: UserInfo = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Read-only entitlement summary: reconciles the B2C plan
    (user_profiles.plan) with any active institution grant, so the frontend
    never has to guess whether a user is a self-serve customer, an
    institution student, or an institution admin. Everything here is
    derived from has_effective_module_access / institution_access -- no
    access rule is duplicated, this endpoint only reports what those
    already decide."""
    profile_rows = (
        supabase.table("user_profiles")
        .select("plan, plan_expires_at, subscription_status")
        .eq("user_id", current_user.id)
        .execute()
    )
    profile = profile_rows.data[0] if profile_rows.data else {}
    self_serve_plan = get_plan_from_profile(profile)

    is_member = is_active_institution_member(supabase, current_user.id)
    module_access = get_active_institution_module_access(supabase, current_user.id)
    context = get_institution_onboarding_context(supabase, current_user.id)

    # Role is read straight off the caller's own active membership -- an
    # institution_admin/teacher sees the admin framing, an ordinary student
    # sees the student framing. Two+ active memberships with mixed roles
    # (unsupported by Phase 3/4 today) default to the higher-privilege view.
    roles = {
        m["role"]
        for m in get_qualifying_memberships(supabase, current_user.id, "student")
    }
    if not is_member:
        user_type = "self_serve"
    elif roles & {"institution_admin", "teacher"}:
        user_type = "institution_admin"
    else:
        user_type = "institution_student"

    effective_access = {
        "speaking": True,  # every plan/institution grant includes some speaking quota
        "reading": has_effective_module_access(supabase, current_user.id, self_serve_plan, "reading"),
        "listening": has_effective_module_access(supabase, current_user.id, self_serve_plan, "listening"),
        "writing": has_effective_module_access(supabase, current_user.id, self_serve_plan, "writing"),
        "mock": has_effective_module_access(supabase, current_user.id, self_serve_plan, "mock_tests"),
        "pronunciation": has_pronunciation_access(self_serve_plan),
    }

    return {
        "user_type": user_type,
        "self_serve_plan": self_serve_plan,
        "institution": {
            "is_member": is_member,
            "status": "active" if is_member else "none",
            "name": context["name"] if context else None,
            "enabled_modules": sorted(module_access["modules"]),
            "speaking_sessions_per_month": module_access["speaking_sessions_per_month"],
        },
        "effective_access": effective_access,
        "plans": [
            {
                "id": p["id"],
                "is_current": p["id"] == self_serve_plan,
                # Upgrade-only: a target only counts as purchasable when it
                # strictly outranks the caller's B2C plan (Free < Basic <
                # Pro < Elite) -- see PLAN_RANK. Deliberately compared
                # against self_serve_plan, never effective_access -- an
                # institution grant must never make a B2C plan look
                # artificially "higher" and block an otherwise-legitimate
                # personal upgrade.
                "is_purchasable": is_strict_upgrade(self_serve_plan, p["id"]),
            }
            for p in PLANS
        ],
    }
