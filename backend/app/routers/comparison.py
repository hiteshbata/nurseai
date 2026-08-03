from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.supabase import get_supabase
from app.core.threading import run_sync
from app.core.rate_limit import SlidingWindowRateLimiter
from app.routers.auth import get_current_user, UserInfo
from app.services.ai_scoring import compare_attempts
from app.services.plan_gating import get_plan_from_profile, get_history_limit
import json

router = APIRouter(prefix="/compare", tags=["progress"])

_compare_rate_limiter = SlidingWindowRateLimiter(20, 600, name="compare:attempts")


class CompareRequest(BaseModel):
    scenario_id: int
    attempt1_id: int
    attempt2_id: int


@router.post("/attempts")
async def compare_attempts_endpoint(
    request: CompareRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """Compare two attempts of the same scenario. Comparison itself isn't
    plan-gated, but which attempts are eligible is capped the same way
    history is (get_history_limit) -- Free/Basic can only compare within
    their most recent N attempts of this scenario, Pro/Elite (limit 999)
    can compare any two of their own attempts."""
    if _compare_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many requests -- please try again in a while.")
    supabase = get_supabase()

    profile_data = await run_sync(
        supabase.table("user_profiles").select("plan, plan_expires_at")
        .eq("user_id", current_user.id).execute
    )
    profile = profile_data.data[0] if profile_data.data else {}
    plan = get_plan_from_profile(profile)

    eligible = await run_sync(
        supabase.table("submissions").select("id")
        .eq("user_id", current_user.id).eq("scenario_id", request.scenario_id)
        .order("created_at", desc=True).limit(get_history_limit(plan)).execute
    )
    eligible_ids = {s["id"] for s in eligible.data}
    if request.attempt1_id not in eligible_ids or request.attempt2_id not in eligible_ids:
        raise HTTPException(
            status_code=403,
            detail="One or both attempts are outside your plan's comparison window — upgrade to compare older attempts.",
        )

    # Fetch both submissions
    s1 = await run_sync(
        supabase.table("submissions").select("*")
        .eq("id", request.attempt1_id).eq("user_id", current_user.id).execute
    )
    s2 = await run_sync(
        supabase.table("submissions").select("*")
        .eq("id", request.attempt2_id).eq("user_id", current_user.id).execute
    )

    if not s1.data or not s2.data:
        raise HTTPException(status_code=404, detail="One or both attempts not found")

    sub1 = s1.data[0]
    sub2 = s2.data[0]

    feedback1 = json.loads(sub1.get("feedback") or "{}")
    feedback2 = json.loads(sub2.get("feedback") or "{}")

    result = await compare_attempts(
        attempt1_feedback=feedback1,
        attempt2_feedback=feedback2,
        attempt1_transcript=sub1.get("answer", ""),
        attempt2_transcript=sub2.get("answer", ""),
        supabase=supabase,
    )

    return result