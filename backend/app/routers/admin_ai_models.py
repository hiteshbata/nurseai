"""Admin API for the AI Model Management registry: CRUD on ai_models,
purpose mapping, health checks (saved-row + test-before-save), and change
history/rollback.

History/rollback deliberately reuse the existing `audit_log` table (see
admin.py's _write_audit_log) instead of a bespoke versioning table --
every mutation here writes {"before": ..., "after": ...} into its `detail`
column, so "show history for this model" is just a query on
(target_type, target_id) (already indexed) and "rollback" is just
restoring a past `before` snapshot and logging that as a new change too
(so a rollback is itself reversible, no special undo-stack needed).
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.supabase import get_supabase
from app.routers.admin import require_admin, _write_audit_log
from app.routers.auth import UserInfo
from app.services import ai_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/ai-models", tags=["admin"])

MODEL_COLUMNS = (
    "id, provider, model_name, display_name, api_base, enabled, is_default, "
    "priority, fallback_model_id, last_health_status, last_health_latency_ms, "
    "last_health_checked_at, last_health_error, created_at, updated_at"
)
HISTORY_TARGET_TYPES = {"ai_model", "ai_model_purpose"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ModelCreate(BaseModel):
    provider: str = Field(min_length=1, max_length=50)
    model_name: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    api_base: Optional[str] = None
    enabled: bool = True
    is_default: bool = False
    priority: int = 0
    fallback_model_id: Optional[int] = None


class ModelUpdate(BaseModel):
    provider: Optional[str] = None
    model_name: Optional[str] = None
    display_name: Optional[str] = None
    api_base: Optional[str] = None
    enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    priority: Optional[int] = None
    fallback_model_id: Optional[int] = None


class TestConnectionRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=50)
    model_name: str = Field(min_length=1, max_length=200)
    api_base: Optional[str] = None


class PurposeMapUpdate(BaseModel):
    model_id: int


# ── MODEL REGISTRY ───────────────────────────────────────────────────

@router.get("")
def list_models(current_user: UserInfo = Depends(require_admin)):
    supabase = get_supabase()
    models = (
        supabase.table("ai_models").select(MODEL_COLUMNS)
        .order("provider").order("model_name").execute().data
    )
    purpose_rows = supabase.table("ai_model_purposes").select("purpose, model_id").execute().data
    purposes_by_model: Dict[int, List[str]] = {}
    for p in purpose_rows:
        purposes_by_model.setdefault(p["model_id"], []).append(p["purpose"])
    for m in models:
        m["purposes"] = purposes_by_model.get(m["id"], [])
    return models


@router.post("")
def create_model(body: ModelCreate, current_user: UserInfo = Depends(require_admin)):
    supabase = get_supabase()
    row = body.model_dump()
    try:
        result = supabase.table("ai_models").insert(row).execute()
    except Exception as e:
        raise HTTPException(status_code=409, detail=f"Could not create model: {str(e)[:300]}")
    created = result.data[0]
    _write_audit_log(
        supabase, current_user, "create", "ai_model", created["id"], created["display_name"],
        {"before": None, "after": created},
    )
    ai_registry.invalidate_cache()
    return created


@router.put("/{model_id}")
def update_model(model_id: int, body: ModelUpdate, current_user: UserInfo = Depends(require_admin)):
    supabase = get_supabase()
    existing = supabase.table("ai_models").select(MODEL_COLUMNS).eq("id", model_id).execute().data
    if not existing:
        raise HTTPException(status_code=404, detail="Model not found")
    before = existing[0]

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return before
    if updates.get("fallback_model_id") == model_id:
        raise HTTPException(status_code=400, detail="A model cannot be its own fallback")
    updates["updated_at"] = _now_iso()

    try:
        result = supabase.table("ai_models").update(updates).eq("id", model_id).execute()
    except Exception as e:
        raise HTTPException(status_code=409, detail=f"Could not update model: {str(e)[:300]}")
    after = result.data[0]
    _write_audit_log(
        supabase, current_user, "update", "ai_model", model_id, after["display_name"],
        {"before": before, "after": after},
    )
    ai_registry.invalidate_cache()
    return after


@router.delete("/{model_id}")
def delete_model(model_id: int, current_user: UserInfo = Depends(require_admin)):
    supabase = get_supabase()
    existing = supabase.table("ai_models").select(MODEL_COLUMNS).eq("id", model_id).execute().data
    if not existing:
        raise HTTPException(status_code=404, detail="Model not found")
    before = existing[0]

    in_use = supabase.table("ai_model_purposes").select("purpose").eq("model_id", model_id).execute().data
    if in_use:
        purposes = ", ".join(p["purpose"] for p in in_use)
        raise HTTPException(
            status_code=409,
            detail=f"Reassign these purposes to a different model first: {purposes}",
        )
    fallback_users = supabase.table("ai_models").select("display_name").eq("fallback_model_id", model_id).execute().data
    if fallback_users:
        names = ", ".join(m["display_name"] for m in fallback_users)
        raise HTTPException(
            status_code=409,
            detail=f"Other models still use this as their fallback, update them first: {names}",
        )

    try:
        supabase.table("ai_models").delete().eq("id", model_id).execute()
    except Exception as e:
        raise HTTPException(status_code=409, detail=f"Could not delete model: {str(e)[:300]}")
    _write_audit_log(
        supabase, current_user, "delete", "ai_model", model_id, before["display_name"],
        {"before": before, "after": None},
    )
    ai_registry.invalidate_cache()
    return {"success": True}


# ── HEALTH CHECK ──────────────────────────────────────────────────────

@router.post("/{model_id}/test")
async def test_saved_model(model_id: int, current_user: UserInfo = Depends(require_admin)):
    """Test an already-saved model row."""
    try:
        return await ai_registry.run_health_check_for_model(model_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Model not found")


@router.post("/test-connection")
async def test_connection(body: TestConnectionRequest, current_user: UserInfo = Depends(require_admin)):
    """Test a provider/model combo before it's saved -- backs the "Test
    Before Save" button on the add/edit form. Does not persist anything."""
    return await ai_registry.run_health_check(body.provider, body.model_name, body.api_base)


# ── PURPOSE MAPPING ───────────────────────────────────────────────────

@router.get("/purposes")
def list_purposes(current_user: UserInfo = Depends(require_admin)):
    supabase = get_supabase()
    rows = supabase.table("ai_model_purposes").select("purpose, model_id, updated_at").order("purpose").execute().data
    models = {m["id"]: m for m in supabase.table("ai_models").select(MODEL_COLUMNS).execute().data}
    for r in rows:
        r["model"] = models.get(r["model_id"])
    return rows


@router.put("/purposes/{purpose}")
def set_purpose_mapping(purpose: str, body: PurposeMapUpdate, current_user: UserInfo = Depends(require_admin)):
    supabase = get_supabase()
    model = supabase.table("ai_models").select("id, display_name").eq("id", body.model_id).execute().data
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    before_rows = supabase.table("ai_model_purposes").select("purpose, model_id").eq("purpose", purpose).execute().data
    before = before_rows[0] if before_rows else None

    result = supabase.table("ai_model_purposes").upsert({
        "purpose": purpose, "model_id": body.model_id, "updated_at": _now_iso(),
    }).execute()
    after = result.data[0]
    _write_audit_log(
        supabase, current_user, "update" if before else "create", "ai_model_purpose", purpose, purpose,
        {"before": before, "after": after},
    )
    ai_registry.invalidate_cache(purpose)
    return after


@router.delete("/purposes/{purpose}")
def delete_purpose_mapping(purpose: str, current_user: UserInfo = Depends(require_admin)):
    supabase = get_supabase()
    before_rows = supabase.table("ai_model_purposes").select("purpose, model_id").eq("purpose", purpose).execute().data
    if not before_rows:
        raise HTTPException(status_code=404, detail="Purpose mapping not found")

    supabase.table("ai_model_purposes").delete().eq("purpose", purpose).execute()
    _write_audit_log(
        supabase, current_user, "delete", "ai_model_purpose", purpose, purpose,
        {"before": before_rows[0], "after": None},
    )
    ai_registry.invalidate_cache(purpose)
    return {"success": True}


# ── HISTORY + ROLLBACK ────────────────────────────────────────────────

@router.get("/{model_id}/history")
def model_history(model_id: int, current_user: UserInfo = Depends(require_admin)):
    supabase = get_supabase()
    return (
        supabase.table("audit_log").select("id, admin_email, action, detail, created_at")
        .eq("target_type", "ai_model").eq("target_id", str(model_id))
        .order("created_at", desc=True).limit(50).execute().data
    )


@router.get("/purposes/{purpose}/history")
def purpose_history(purpose: str, current_user: UserInfo = Depends(require_admin)):
    supabase = get_supabase()
    return (
        supabase.table("audit_log").select("id, admin_email, action, detail, created_at")
        .eq("target_type", "ai_model_purpose").eq("target_id", purpose)
        .order("created_at", desc=True).limit(50).execute().data
    )


@router.post("/history/{audit_log_id}/rollback")
def rollback_change(audit_log_id: str, current_user: UserInfo = Depends(require_admin)):
    supabase = get_supabase()
    rows = supabase.table("audit_log").select("*").eq("id", audit_log_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="History entry not found")
    entry = rows[0]
    if entry["target_type"] not in HISTORY_TARGET_TYPES:
        raise HTTPException(status_code=400, detail="Not an AI Models change")

    target_type = entry["target_type"]
    target_id = entry["target_id"]
    before_snapshot = (entry.get("detail") or {}).get("before")
    table = "ai_models" if target_type == "ai_model" else "ai_model_purposes"
    id_field = "id" if table == "ai_models" else "purpose"
    id_value = int(target_id) if table == "ai_models" else target_id

    current_rows = supabase.table(table).select("*").eq(id_field, id_value).execute().data
    current = current_rows[0] if current_rows else None

    try:
        if before_snapshot is None:
            # Rolling back a "create" -- delete the row if it's still there.
            if current:
                supabase.table(table).delete().eq(id_field, id_value).execute()
        else:
            restore = {k: v for k, v in before_snapshot.items() if k != "created_at"}
            supabase.table(table).upsert(restore).execute()
    except Exception as e:
        raise HTTPException(status_code=409, detail=f"Could not roll back: {str(e)[:300]}")

    _write_audit_log(
        supabase, current_user, "rollback", target_type, target_id, entry.get("target_label"),
        {"before": current, "after": before_snapshot},
    )
    if table == "ai_models":
        ai_registry.invalidate_cache()
    else:
        ai_registry.invalidate_cache(target_id)
    return {"success": True, "restored": before_snapshot}
