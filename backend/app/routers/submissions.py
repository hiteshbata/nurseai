import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.supabase import get_supabase
from app.routers.auth import get_current_user, get_user_supabase, UserInfo
from supabase import Client
from app.services.plan_gating import get_plan_from_profile, get_history_limit

router = APIRouter(prefix="/submissions", tags=["submissions"])


def _parse_feedback(raw):
    """Split a stored feedback value into (scored_dict, plain_text).

    Feedback is normally a JSON object written by the scoring services, but
    older rows hold plain text and unscored ones hold the literal string
    "No feedback". Exactly one of the two returned values is populated (both
    are None when there is nothing stored), so the caller never has to guess
    which shape it got.
    """
    if not raw:
        return None, None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None, raw
    if isinstance(parsed, dict):
        return parsed, None
    return None, str(parsed)


@router.get("/")
def get_submissions(
    module: Optional[str] = Query(None),
    scenario_id: Optional[int] = Query(None),
    current_user: UserInfo = Depends(get_current_user),
    user_db: Client = Depends(get_user_supabase),
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

    # RLS-scoped: "Users can read own submissions" already restricts this to
    # current_user's own rows even without the .eq() below (defense in depth).
    query = user_db.table("submissions").select(
        "id, scenario_id, module, score, created_at"
    ).eq("user_id", current_user.id)
    if module:
        query = query.eq("module", module)
    if scenario_id is not None:
        query = query.eq("scenario_id", scenario_id)
    data = query.order("created_at", desc=True).limit(get_history_limit(plan)).execute()
    return data.data


@router.get("/{submission_id}")
def get_submission(
    submission_id: int,
    current_user: UserInfo = Depends(get_current_user),
    user_db: Client = Depends(get_user_supabase),
):
    """One of the current user's own submissions, with its full feedback --
    powers the dashboard's Recent Sessions "View" link.

    /progress/stats truncates feedback to 100 chars for the list view, which
    is unusable here because feedback is stored as a JSON blob.

    The .eq("user_id") filter is the authorization boundary: a submission
    belonging to someone else returns the same 404 as one that doesn't exist,
    so this endpoint can't be used to probe for valid submission ids. RLS
    ("Users can read own submissions") backs this up at the DB level too.
    """
    supabase = get_supabase()

    data = user_db.table("submissions").select(
        "id, scenario_id, module, score, feedback, created_at"
    ).eq("id", submission_id).eq("user_id", current_user.id).execute()

    if not data.data:
        raise HTTPException(status_code=404, detail="Submission not found")

    row = data.data[0]

    feedback, feedback_text = _parse_feedback(row.get("feedback"))

    scenario_title = None
    if row.get("scenario_id") is not None:
        scenario = supabase.table("scenarios").select("title").eq(
            "id", row["scenario_id"]
        ).execute()
        if scenario.data:
            scenario_title = scenario.data[0].get("title")

    return {
        "id": row["id"],
        "module": row.get("module"),
        "score": row.get("score"),
        "created_at": row.get("created_at"),
        "scenario_id": row.get("scenario_id"),
        "scenario_title": scenario_title,
        "feedback": feedback,
        "feedback_text": feedback_text,
    }
