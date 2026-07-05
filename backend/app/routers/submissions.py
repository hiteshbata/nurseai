from typing import Optional
from fastapi import APIRouter, Depends, Query
from app.core.supabase import get_supabase
from app.routers.auth import get_current_user, UserInfo
from app.services.plan_gating import get_plan_from_profile, get_history_limit

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.get("/")
def get_submissions(
    module: Optional[str] = Query(None),
    scenario_id: Optional[int] = Query(None),
    current_user: UserInfo = Depends(get_current_user),
):
    """List the current user's own submissions, optionally filtered by
    module and scenario_id. Used by the speaking/writing practice pages
    to list past attempts of the same scenario for comparison.
    Capped by plan (get_history_limit) -- Free/Basic only ever see their
    most recent N attempts, Pro/Elite see everything."""
    supabase = get_supabase()

    profile_data = supabase.table("user_profiles").select(
        "plan, plan_expires_at"
    ).eq("user_id", current_user.id).execute()
    profile = profile_data.data[0] if profile_data.data else {}
    plan = get_plan_from_profile(profile)

    query = supabase.table("submissions").select(
        "id, scenario_id, module, score, created_at"
    ).eq("user_id", current_user.id)
    if module:
        query = query.eq("module", module)
    if scenario_id is not None:
        query = query.eq("scenario_id", scenario_id)
    data = query.order("created_at", desc=True).limit(get_history_limit(plan)).execute()
    return data.data
