from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from app.core.supabase import get_supabase
from app.routers.auth import get_current_user, UserInfo
import json

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(current_user: UserInfo = Depends(get_current_user)):
    """Verify the current user is an admin."""
    supabase = get_supabase()
    role_data = supabase.table("user_roles").select("role").eq("user_id", current_user.id).execute()
    if not role_data.data or role_data.data[0]["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ── SCENARIO MANAGEMENT ─────────────────────────────────────────────

class ScenarioCreate(BaseModel):
    module: str
    title: str
    setting: str = "Hospital"
    difficulty: str = "medium"
    interlocutor_card: Dict[str, Any] = {}
    nurse_card: Dict[str, Any] = {}
    scoring_criteria: Dict[str, Any] = {}


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
        "interlocutor_card": json.dumps(scenario.interlocutor_card),
        "nurse_card": json.dumps(scenario.nurse_card),
        "scoring_criteria": json.dumps(scenario.scoring_criteria),
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
        update_data["interlocutor_card"] = json.dumps(scenario.interlocutor_card)
    if scenario.nurse_card is not None:
        update_data["nurse_card"] = json.dumps(scenario.nurse_card)
    if scenario.scoring_criteria is not None:
        update_data["scoring_criteria"] = json.dumps(scenario.scoring_criteria)
    if scenario.is_active is not None:
        update_data["is_active"] = scenario.is_active

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    update_data["updated_at"] = "now()"
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
        "updated_at": "now()",
    }).execute()
    return data.data[0]


# ── USER MANAGEMENT ─────────────────────────────────────────────────

@router.get("/users")
def admin_list_users(current_user: UserInfo = Depends(require_admin)):
    """List all users with their roles."""
    supabase = get_supabase()
    roles = supabase.table("user_roles").select("*").execute().data
    return roles


class SetRoleRequest(BaseModel):
    user_id: str
    role: str


@router.post("/users/role")
def admin_set_user_role(
    req: SetRoleRequest,
    current_user: UserInfo = Depends(require_admin),
):
    """Set a user's role."""
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
        query = query.gte("timestamp", datetime.utcnow().isoformat()[:10])
    elif filter == "week":
        week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
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