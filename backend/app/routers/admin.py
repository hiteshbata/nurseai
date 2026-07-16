import logging
import secrets
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from app.core.config import settings
from app.core.supabase import get_supabase
from app.core.plans import GRACE_PERIOD_DAYS
from app.routers.auth import get_current_user, UserInfo

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


def require_admin(current_user: UserInfo = Depends(get_current_user)):
    """Verify the current user is an admin."""
    supabase = get_supabase()
    role_data = supabase.table("user_roles").select("role").eq("user_id", current_user.id).execute()
    if not role_data.data or role_data.data[0]["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def require_admin_or_cron(
    x_cron_secret: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
):
    """Allow either an admin JWT (manual/dashboard use) or the shared
    CRON_SECRET (external scheduler use, no human session available).
    Falls back to admin-JWT-only if CRON_SECRET is unset."""
    if settings.CRON_SECRET and x_cron_secret and secrets.compare_digest(x_cron_secret, settings.CRON_SECRET):
        return None
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.removeprefix("Bearer ").strip()
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    current_user = get_current_user(credentials=creds)
    return require_admin(current_user)


# ── SCENARIO MANAGEMENT ─────────────────────────────────────────────

class ScenarioCreate(BaseModel):
    module: str
    title: str
    setting: str = "Hospital"
    difficulty: str = "intermediate"
    interlocutor_card: Dict[str, Any] = Field(default_factory=dict)
    nurse_card: Dict[str, Any] = Field(default_factory=dict)
    scoring_criteria: Dict[str, Any] = Field(default_factory=dict)


class ScenarioUpdate(BaseModel):
    title: Optional[str] = None
    setting: Optional[str] = None
    difficulty: Optional[str] = None
    interlocutor_card: Optional[Dict[str, Any]] = None
    nurse_card: Optional[Dict[str, Any]] = None
    scoring_criteria: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


@router.get("/scenarios")
def admin_list_scenarios(
    module: Optional[str] = None,
    current_user: UserInfo = Depends(require_admin),
):
    """List all scenarios (including inactive)."""
    supabase = get_supabase()
    query = supabase.table("scenarios").select("*").order("created_at", desc=True)
    if module:
        query = query.eq("module", module)
    return query.execute().data


@router.post("/scenarios")
def admin_create_scenario(
    scenario: ScenarioCreate,
    current_user: UserInfo = Depends(require_admin),
):
    """Create a new scenario with interlocutor + nurse cards."""
    supabase = get_supabase()
    data = supabase.table("scenarios").insert({
        "module": scenario.module,
        "title": scenario.title,
        "setting": scenario.setting,
        "difficulty": scenario.difficulty,
        "interlocutor_card": scenario.interlocutor_card,
        "nurse_card": scenario.nurse_card,
        "scoring_criteria": scenario.scoring_criteria,
    }).execute()
    return data.data[0]


@router.put("/scenarios/{scenario_id}")
def admin_update_scenario(
    scenario_id: int,
    scenario: ScenarioUpdate,
    current_user: UserInfo = Depends(require_admin),
):
    """Update a scenario."""
    supabase = get_supabase()
    update_data: Dict[str, Any] = {}
    if scenario.title is not None:
        update_data["title"] = scenario.title
    if scenario.setting is not None:
        update_data["setting"] = scenario.setting
    if scenario.difficulty is not None:
        update_data["difficulty"] = scenario.difficulty
    if scenario.interlocutor_card is not None:
        update_data["interlocutor_card"] = scenario.interlocutor_card
    if scenario.nurse_card is not None:
        update_data["nurse_card"] = scenario.nurse_card
    if scenario.scoring_criteria is not None:
        update_data["scoring_criteria"] = scenario.scoring_criteria
    if scenario.is_active is not None:
        update_data["is_active"] = scenario.is_active

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data = supabase.table("scenarios").update(update_data).eq("id", scenario_id).execute()
    return data.data[0]


@router.delete("/scenarios/{scenario_id}")
def admin_delete_scenario(
    scenario_id: int,
    current_user: UserInfo = Depends(require_admin),
):
    """Soft-delete a scenario (set is_active=False)."""
    supabase = get_supabase()
    supabase.table("scenarios").update({"is_active": False}).eq("id", scenario_id).execute()
    return {"success": True, "message": f"Scenario {scenario_id} deactivated"}


# ── SETTINGS MANAGEMENT ─────────────────────────────────────────────

class SettingUpdate(BaseModel):
    value: str


@router.get("/settings")
def admin_get_settings(current_user: UserInfo = Depends(require_admin)):
    """Get all settings."""
    supabase = get_supabase()
    data = supabase.table("settings").select("*").execute()
    return data.data


@router.put("/settings/{key}")
def admin_update_setting(
    key: str,
    setting: SettingUpdate,
    current_user: UserInfo = Depends(require_admin),
):
    """Update a setting (e.g., AI model, pricing)."""
    supabase = get_supabase()
    data = supabase.table("settings").upsert({
        "key": key,
        "value": setting.value,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    return data.data[0]


# ── USER MANAGEMENT ─────────────────────────────────────────────────

@router.get("/users")
def admin_list_users(current_user: UserInfo = Depends(require_admin)):
    """List all users with their roles."""
    supabase = get_supabase()
    roles = supabase.table("user_roles").select("*").execute().data
    return roles


ALLOWED_ROLES = {"user", "admin"}


class SetRoleRequest(BaseModel):
    user_id: str
    role: str


@router.post("/users/role")
def admin_set_user_role(
    req: SetRoleRequest,
    current_user: UserInfo = Depends(require_admin),
):
    """Set a user's role."""
    if req.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {sorted(ALLOWED_ROLES)}")
    supabase = get_supabase()
    supabase.table("user_roles").upsert({
        "user_id": req.user_id,
        "role": req.role,
    }).execute()
    return {"success": True}


# ── ANALYTICS ───────────────────────────────────────────────────────

@router.get("/stats")
def admin_get_stats(current_user: UserInfo = Depends(require_admin)):
    """Get app-wide statistics."""
    supabase = get_supabase()

    total_users = supabase.table("user_roles").select("user_id", count="exact").execute().count or 0
    total_submissions = supabase.table("submissions").select("id", count="exact").execute().count or 0
    total_scenarios = supabase.table("scenarios").select("id", count="exact").eq("is_active", True).execute().count or 0

    modules = ["speaking", "writing", "reading", "listening"]
    module_counts: Dict[str, int] = {}
    for mod in modules:
        count = supabase.table("submissions").select("id", count="exact").eq("module", mod).execute().count
        module_counts[mod] = count or 0

    unresolved_count = supabase.table("logs").select("id", count="exact").eq("resolved", False).execute().count

    return {
        "total_users": total_users,
        "total_submissions": total_submissions,
        "total_active_scenarios": total_scenarios,
        "submissions_by_module": module_counts,
        "unresolved_logs": unresolved_count or 0,
    }


# ── LOGS MANAGEMENT ─────────────────────────────────────────────────

@router.get("/logs")
def admin_get_logs(
    filter: str = "all",
    current_user: UserInfo = Depends(require_admin),
):
    """Fetch logs with optional time/resolution filter."""
    supabase = get_supabase()
    query = supabase.table("logs").select("*").order("timestamp", desc=True)

    if filter == "unresolved":
        query = query.eq("resolved", False)
    elif filter == "today":
        query = query.gte("timestamp", datetime.now(timezone.utc).isoformat()[:10])
    elif filter == "week":
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        query = query.gte("timestamp", week_ago)

    return query.limit(100).execute().data


@router.put("/logs/{log_id}/resolve")
def admin_resolve_log(
    log_id: int,
    current_user: UserInfo = Depends(require_admin),
):
    """Mark a log entry as resolved."""
    supabase = get_supabase()
    supabase.table("logs").update({"resolved": True}).eq("id", log_id).execute()
    return {"success": True}


@router.get("/logs/unresolved-count")
def admin_unresolved_logs_count(current_user: UserInfo = Depends(require_admin)):
    """Return count of unresolved log entries."""
    supabase = get_supabase()
    count = supabase.table("logs").select("id", count="exact").eq("resolved", False).execute().count
    return {"count": count or 0}


LOG_RETENTION_DAYS = 90


@router.post("/logs/prune")
def admin_prune_logs(_=Depends(require_admin_or_cron)):
    """Delete log entries older than LOG_RETENTION_DAYS. Wired to run weekly
    via external cron (cron-job.org or Render Cron Job) -- the logs table has
    no other retention and grows unbounded otherwise. Safe to re-run: deletes
    by cutoff, so a repeat run just finds nothing older to delete."""
    supabase = get_supabase()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=LOG_RETENTION_DAYS)).isoformat()
    try:
        deleted = supabase.table("logs").delete().lt("timestamp", cutoff).execute()
    except Exception:
        logger.exception("logs/prune failed")
        raise HTTPException(status_code=502, detail="Log prune failed")
    count = len(deleted.data or [])
    logger.info("logs/prune deleted %d rows older than %s", count, cutoff)
    return {"deleted": count}


# ── SUBSCRIPTION MANAGEMENT ─────────────────────────────────────────

@router.post("/subscriptions/sweep-expired")
def admin_sweep_expired_subscriptions(_=Depends(require_admin_or_cron)):
    """Batch-downgrade profiles past plan_expires_at + grace period.

    Gating itself never depends on this having run — get_plan_from_profile
    checks expiry lazily on every request, so an expired user loses paid
    access immediately regardless of whether this sweep has executed.
    This endpoint exists purely to keep the *stored* plan/subscription_status
    columns accurate for admin dashboards, analytics, or any other code
    that reads user_profiles directly instead of through the gating helper.

    Wired to run daily via external cron -- expiry is date-based (grace
    period is in days), so hourly buys nothing an expired row will still be
    "active" for at most one extra day, and get_plan_from_profile already
    hides paid access from it in the meantime. Safe to re-run: the query
    only matches subscription_status="active", so already-downgraded rows
    (now "expired") are never touched twice.
    """
    supabase = get_supabase()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=GRACE_PERIOD_DAYS)).isoformat()

    try:
        expired = (
            supabase.table("user_profiles")
            .select("user_id")
            .eq("subscription_status", "active")
            .lt("plan_expires_at", cutoff)
            .execute()
        )

        if not expired.data:
            logger.info("subscriptions/sweep-expired: nothing to downgrade")
            return {"downgraded": 0}

        user_ids = [row["user_id"] for row in expired.data]
        supabase.table("user_profiles").update({
            "plan": "free",
            "subscription_status": "expired",
        }).in_("user_id", user_ids).execute()
    except Exception:
        logger.exception("subscriptions/sweep-expired failed")
        raise HTTPException(status_code=502, detail="Subscription sweep failed")

    logger.info("subscriptions/sweep-expired downgraded %d profiles", len(user_ids))
    return {"downgraded": len(user_ids)}
