import logging
import secrets
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from app.core.config import settings
from app.core.supabase import get_supabase, get_auth_client
from app.core.plans import GRACE_PERIOD_DAYS, PLAN_PERIOD_DAYS, PLAN_PRICE_INR
from app.routers.payments import get_current_plan, grant_subscription_period, get_razorpay_client, _process_refund
from app.services.plan_gating import get_plan_from_profile
from app.services.founder_metrics import get_founder_metrics
from app.services.ai_cost_metrics import get_ai_cost_metrics
from app.core import cost_circuit_breaker
from app.services.email import send_email, render_expiry_reminder, render_failed_payment_reminder
from app.services.reminders import rows_due_for_expiry_reminder, rows_due_for_failed_payment_reminder
from app.routers.profile import _USER_OWNED_TABLES
from app.routers.auth import get_current_user, UserInfo
from app.core.feature_flags import FEATURE_FLAGS, is_feature_enabled

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


# ── RBAC ──────────────────────────────────────────────────────────────
# An ordered tier, not a permissions matrix: each role satisfies every
# floor at or below its own rank. Sufficient until a contract demands
# per-permission grants -- don't build that table until then.
ROLE_RANK = {"user": 0, "support": 1, "analyst": 2, "admin": 3, "owner": 4}
ALLOWED_ROLES = set(ROLE_RANK)


def _get_role(supabase, user_id: str) -> str:
    row = supabase.table("user_roles").select("role").eq("user_id", user_id).execute()
    return row.data[0]["role"] if row.data else "user"


def _target_is_staff(supabase, user_id: str) -> bool:
    """True for any staff tier (support and up) -- used to stop one staff
    member from moderating, deleting, or impersonating another."""
    return ROLE_RANK.get(_get_role(supabase, user_id), 0) >= ROLE_RANK["support"]


def require_role(minimum: str):
    """FastAPI dependency factory: gate an endpoint behind a minimum role
    tier. Call once per tier (see the named deps below) rather than inline
    at each endpoint, so there's one object per floor, not one per call site."""
    minimum_rank = ROLE_RANK[minimum]

    def _dep(current_user: UserInfo = Depends(get_current_user)) -> UserInfo:
        role = _get_role(get_supabase(), current_user.id)
        if ROLE_RANK.get(role, 0) < minimum_rank:
            raise HTTPException(status_code=403, detail=f"Requires {minimum}+ access")
        return current_user

    return _dep


require_support = require_role("support")
require_analyst = require_role("analyst")
# Name/behavior unchanged from the old plain-admin check -- speaking.py and
# scenario_generator.py import this directly.
require_admin = require_role("admin")
require_owner = require_role("owner")


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


# ── AUDIT LOG ─────────────────────────────────────────────────────────
# Ban/suspend/delete write to moderation_log (richer, action-specific
# fields); impersonation writes to impersonation_log. This is for
# everything else an admin changes -- role, plan, content, settings.

def _write_audit_log(
    supabase,
    admin: UserInfo,
    action: str,
    target_type: str,
    target_id: Optional[str] = None,
    target_label: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        supabase.table("audit_log").insert({
            "admin_id": admin.id,
            "admin_email": admin.email,
            "action": action,
            "target_type": target_type,
            "target_id": str(target_id) if target_id is not None else None,
            "target_label": target_label,
            "detail": detail,
        }).execute()
    except Exception:
        # Never let audit logging break the action it's recording.
        logger.exception("audit_log write failed | action=%s target_type=%s target_id=%s", action, target_type, target_id)


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
    try:
        data = supabase.table("scenarios").insert({
            "module": scenario.module,
            "title": scenario.title,
            "setting": scenario.setting,
            "difficulty": scenario.difficulty,
            "interlocutor_card": scenario.interlocutor_card,
            "nurse_card": scenario.nurse_card,
            "scoring_criteria": scenario.scoring_criteria,
        }).execute()
    except Exception as e:
        if "duplicate key" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"A {scenario.module} scenario titled \"{scenario.title}\" already exists")
        raise
    created = data.data[0]
    _write_audit_log(
        supabase, current_user, "scenario_created", "scenario",
        target_id=created["id"], target_label=scenario.title,
        detail={"module": scenario.module, "difficulty": scenario.difficulty},
    )
    return created


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
    updated = data.data[0]
    _write_audit_log(
        supabase, current_user, "scenario_updated", "scenario",
        target_id=scenario_id, target_label=updated.get("title"),
        detail={k: v for k, v in update_data.items() if k != "updated_at"},
    )
    return updated


@router.delete("/scenarios/{scenario_id}")
def admin_delete_scenario(
    scenario_id: int,
    hard: bool = False,
    current_user: UserInfo = Depends(require_admin),
):
    """Delete a scenario. Default is a soft delete (is_active=False), preserving
    the historical default. With hard=true, remove the row entirely — but scenarios
    with practice history are referenced by submissions/session_transcripts (FK with
    no ON DELETE), so a hard delete there raises; fall back to deactivating so the
    admin's intent (get it out of the active list) still succeeds without data loss."""
    supabase = get_supabase()
    if hard:
        try:
            supabase.table("scenarios").delete().eq("id", scenario_id).execute()
            _write_audit_log(supabase, current_user, "scenario_deleted", "scenario", target_id=scenario_id)
            return {"success": True, "deleted": True, "message": f"Scenario {scenario_id} deleted"}
        except Exception:
            supabase.table("scenarios").update({"is_active": False}).eq("id", scenario_id).execute()
            _write_audit_log(supabase, current_user, "scenario_deactivated", "scenario", target_id=scenario_id)
            return {"success": True, "deleted": False, "message": "This scenario has practice history, so it was kept as inactive instead of deleted."}

    supabase.table("scenarios").update({"is_active": False}).eq("id", scenario_id).execute()
    _write_audit_log(supabase, current_user, "scenario_deactivated", "scenario", target_id=scenario_id)
    return {"success": True, "deleted": False, "message": f"Scenario {scenario_id} deactivated"}


# ── COUPON CODES ──────────────────────────────────────────────────────
# Annual (order) checkout: discount_type/discount_value are applied by our
# own backend -- see apply_coupon in app/routers/payments.py.
# Monthly (subscription) checkout: Razorpay only discounts a subscription
# via an Offer entity, and Offers can only be created from the Razorpay
# Dashboard (no API for it) -- see the comment on coupon_codes in
# backend/migrations/2026-07-18_coupon_codes.sql for the manual setup
# steps. razorpay_offer_id links this coupon to that dashboard-created
# Offer; leave it blank if the coupon is annual-only.

class CouponCreate(BaseModel):
    code: str
    discount_type: str  # "percent" | "flat_paise"
    discount_value: int
    max_redemptions: Optional[int] = None
    expires_at: Optional[str] = None
    razorpay_offer_id: Optional[str] = None


class CouponUpdate(BaseModel):
    active: Optional[bool] = None
    max_redemptions: Optional[int] = None
    expires_at: Optional[str] = None
    razorpay_offer_id: Optional[str] = None


@router.get("/coupons")
def admin_list_coupons(current_user: UserInfo = Depends(require_admin)):
    supabase = get_supabase()
    return supabase.table("coupon_codes").select("*").order("created_at", desc=True).execute().data


@router.post("/coupons")
def admin_create_coupon(
    coupon: CouponCreate,
    current_user: UserInfo = Depends(require_admin),
):
    if coupon.discount_type not in ("percent", "flat_paise"):
        raise HTTPException(status_code=400, detail="discount_type must be 'percent' or 'flat_paise'")
    if coupon.discount_value <= 0:
        raise HTTPException(status_code=400, detail="discount_value must be positive")
    if coupon.discount_type == "percent" and coupon.discount_value > 100:
        raise HTTPException(status_code=400, detail="Percent discount can't exceed 100")

    supabase = get_supabase()
    try:
        data = supabase.table("coupon_codes").insert({
            "code": coupon.code.strip().upper(),
            "discount_type": coupon.discount_type,
            "discount_value": coupon.discount_value,
            "max_redemptions": coupon.max_redemptions,
            "expires_at": coupon.expires_at,
            "razorpay_offer_id": coupon.razorpay_offer_id,
            "created_by": current_user.id,
        }).execute()
    except Exception as e:
        if "duplicate key" in str(e).lower():
            raise HTTPException(status_code=400, detail="A coupon with this code already exists")
        raise
    created = data.data[0]
    _write_audit_log(
        supabase, current_user, "coupon_created", "coupon",
        target_id=created["id"], target_label=created["code"],
        detail={"discount_type": coupon.discount_type, "discount_value": coupon.discount_value},
    )
    return created


@router.patch("/coupons/{coupon_id}")
def admin_update_coupon(
    coupon_id: str,
    coupon: CouponUpdate,
    current_user: UserInfo = Depends(require_admin),
):
    update_data: Dict[str, Any] = {}
    if coupon.active is not None:
        update_data["active"] = coupon.active
    if coupon.max_redemptions is not None:
        update_data["max_redemptions"] = coupon.max_redemptions
    if coupon.expires_at is not None:
        update_data["expires_at"] = coupon.expires_at
    if coupon.razorpay_offer_id is not None:
        update_data["razorpay_offer_id"] = coupon.razorpay_offer_id

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    supabase = get_supabase()
    data = supabase.table("coupon_codes").update(update_data).eq("id", coupon_id).execute()
    if not data.data:
        raise HTTPException(status_code=404, detail="Coupon not found")
    updated = data.data[0]
    _write_audit_log(
        supabase, current_user, "coupon_updated", "coupon",
        target_id=coupon_id, target_label=updated.get("code"), detail=update_data,
    )
    return updated


@router.delete("/coupons/{coupon_id}")
def admin_delete_coupon(
    coupon_id: str,
    current_user: UserInfo = Depends(require_admin),
):
    supabase = get_supabase()
    existing = supabase.table("coupon_codes").select("code").eq("id", coupon_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Coupon not found")
    supabase.table("coupon_codes").delete().eq("id", coupon_id).execute()
    _write_audit_log(
        supabase, current_user, "coupon_deleted", "coupon",
        target_id=coupon_id, target_label=existing.data[0]["code"],
    )
    return {"success": True, "message": "Coupon deleted"}


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
    _write_audit_log(
        supabase, current_user, "setting_updated", "setting",
        target_id=key, target_label=key, detail={"value": setting.value},
    )
    return data.data[0]


# ── AI SPEND CIRCUIT BREAKER ─────────────────────────────────────────
# See app/core/cost_circuit_breaker.py -- global daily cap on AI provider
# spend (LLM + STT + TTS + realtime), resets at UTC midnight.

class SpendCapUpdate(BaseModel):
    cap_usd: Optional[float] = Field(
        default=None, description="null restores the MAX_DAILY_AI_SPEND_USD env default"
    )


@router.get("/spend-cap")
def admin_get_spend_cap(current_user: UserInfo = Depends(require_admin)):
    return {
        "cap_usd": cost_circuit_breaker.get_cap(),
        "spent_today_usd": cost_circuit_breaker.get_daily_total(),
        "tripped": cost_circuit_breaker.is_tripped(),
    }


@router.put("/spend-cap")
def admin_set_spend_cap(
    req: SpendCapUpdate,
    current_user: UserInfo = Depends(require_owner),
):
    if req.cap_usd is not None and req.cap_usd <= 0:
        raise HTTPException(status_code=400, detail="cap_usd must be positive")
    cost_circuit_breaker.set_cap_override(req.cap_usd)
    _write_audit_log(
        get_supabase(), current_user, "spend_cap_updated", "spend_cap",
        detail={"cap_usd": req.cap_usd},
    )
    return {
        "cap_usd": cost_circuit_breaker.get_cap(),
        "spent_today_usd": cost_circuit_breaker.get_daily_total(),
        "tripped": cost_circuit_breaker.is_tripped(),
    }


# ── FEATURE FLAGS / KILL SWITCHES ────────────────────────────────────
# Stored as ordinary rows in the same `settings` table (key=feature_<x>_enabled,
# value="true"/"false"), read fresh on every request by app.core.feature_flags
# -- so flipping one off here takes effect immediately, no deploy needed.

class FeatureFlagUpdate(BaseModel):
    enabled: bool


@router.get("/feature-flags")
def admin_get_feature_flags(current_user: UserInfo = Depends(require_admin)):
    return [
        {"key": key, "label": label, "enabled": is_feature_enabled(key)}
        for key, label in FEATURE_FLAGS.items()
    ]


@router.put("/feature-flags/{key}")
def admin_set_feature_flag(
    key: str,
    req: FeatureFlagUpdate,
    current_user: UserInfo = Depends(require_admin),
):
    if key not in FEATURE_FLAGS:
        raise HTTPException(status_code=404, detail="Unknown feature flag")
    supabase = get_supabase()
    supabase.table("settings").upsert({
        "key": f"feature_{key}_enabled",
        "value": "true" if req.enabled else "false",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    _write_audit_log(
        supabase, current_user, "feature_flag_toggled", "feature_flag",
        target_id=key, target_label=FEATURE_FLAGS[key], detail={"enabled": req.enabled},
    )
    return {"key": key, "enabled": req.enabled}


# ── USER MANAGEMENT ─────────────────────────────────────────────────

@router.get("/users")
def admin_list_users(current_user: UserInfo = Depends(require_support)):
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
    """Set a user's role. A caller can never grant a role ranked above
    their own -- an admin can create support/analyst/admin staff but not
    another owner; only an owner can create owners."""
    if req.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {sorted(ALLOWED_ROLES)}")
    supabase = get_supabase()
    caller_role = _get_role(supabase, current_user.id)
    if ROLE_RANK[req.role] > ROLE_RANK.get(caller_role, 0):
        raise HTTPException(status_code=403, detail="Cannot grant a role higher than your own")
    supabase.table("user_roles").upsert({
        "user_id": req.user_id,
        "role": req.role,
    }).execute()
    _write_audit_log(
        supabase, current_user, "role_changed", "user",
        target_id=req.user_id, detail={"role": req.role},
    )
    return {"success": True}


# ── USER LOOKUP (User 360) ───────────────────────────────────────────

def _unwrap_auth_users(resp: Any) -> List[Any]:
    """supabase-py's admin.list_users() has returned either a bare list or an
    object with a `.users` attribute across versions -- handle both."""
    return resp if isinstance(resp, list) else getattr(resp, "users", resp)


def _user_display_name(user: Any) -> str:
    meta = getattr(user, "user_metadata", None) or {}
    return meta.get("name") or meta.get("full_name") or ""


def _emails_by_user_id(supabase, user_ids: set) -> Dict[str, str]:
    """Bulk id->email lookup via the users mirror table (public.users, kept
    in sync by auth.py's lazy per-request upsert -- see
    backend/migrations/2026-07-18_users_mirror.sql) instead of a Supabase
    Auth list_users() call, which caps at 1000 rows."""
    if not user_ids:
        return {}
    rows = supabase.table("users").select("id, email").in_("id", list(user_ids)).execute().data
    return {r["id"]: (r.get("email") or "") for r in rows}


@router.get("/users/list")
def admin_search_users(
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: UserInfo = Depends(require_support),
):
    """Searchable user list with plan, role, and activity -- the real
    lookup table the plain /admin/users endpoint doesn't provide.

    Reads the users mirror table (public.users) instead of Supabase Auth's
    list_users(), which capped at 1000 rows and forced search/sort/paginate
    to happen in Python on every request regardless of page size. Search
    and pagination now push down to Postgres; profile/role/submission
    lookups are scoped to just the current page's user_ids, not every user.
    See backend/migrations/2026-07-18_users_mirror.sql and
    POST /admin/users/backfill-mirror for how the mirror gets populated.
    """
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    supabase = get_supabase()

    query = supabase.table("users").select("id, email, name, created_at", count="exact")
    if search:
        needle = search.strip().replace(",", "")
        if needle:
            pattern = f"%{needle}%"
            query = query.or_(f"email.ilike.{pattern},name.ilike.{pattern}")
    result = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()

    page_users = result.data
    total = result.count or 0
    user_ids = [u["id"] for u in page_users]

    profiles = (
        {p["user_id"]: p for p in supabase.table("user_profiles").select("*").in_("user_id", user_ids).execute().data}
        if user_ids else {}
    )
    roles = (
        {r["user_id"]: r["role"] for r in supabase.table("user_roles").select("user_id, role").in_("user_id", user_ids).execute().data}
        if user_ids else {}
    )
    submissions = (
        supabase.table("submissions").select("user_id, score").in_("user_id", user_ids).execute().data
        if user_ids else []
    )
    stats: Dict[str, Dict[str, float]] = {}
    for s in submissions:
        st = stats.setdefault(s["user_id"], {"count": 0, "total_score": 0.0, "scored": 0})
        st["count"] += 1
        if s.get("score") is not None:
            st["total_score"] += s["score"]
            st["scored"] += 1

    page = []
    for u in page_users:
        profile = profiles.get(u["id"], {})
        st = stats.get(u["id"], {"count": 0, "total_score": 0.0, "scored": 0})
        page.append({
            "user_id": u["id"],
            "email": u.get("email") or "",
            "name": u.get("name") or "",
            "created_at": u["created_at"],
            "role": roles.get(u["id"], "user"),
            "plan": profile.get("plan", "free"),
            "subscription_status": profile.get("subscription_status", "none"),
            "plan_expires_at": profile.get("plan_expires_at"),
            "sessions": int(st["count"]),
            "avg_score": round(st["total_score"] / st["scored"], 1) if st["scored"] else None,
        })

    return {"total": total, "users": page}


@router.post("/users/backfill-mirror")
def admin_backfill_users_mirror(_=Depends(require_admin_or_cron)):
    """Syncs every Supabase Auth user into the public.users mirror table
    that admin_search_users and _emails_by_user_id read from. Ordinary
    signups keep the mirror fresh via auth.py's lazy per-request upsert;
    this exists to (1) backfill users who signed up before the mirror
    existed and (2) correct drift -- e.g. an email changed but that user
    hasn't made an authenticated request since. Safe to re-run: upserts
    by id, and a repeat run just re-writes the same rows.

    Paginates through the full Auth user list rather than the 1000-row cap
    admin_search_users used to hit -- fine here since nothing is waiting on
    this synchronously; wire it to run periodically via cron (same
    require_admin_or_cron pattern as sweep-expired/logs-prune) or trigger
    it once by hand after the migration lands.
    """
    supabase = get_supabase()
    page = 1
    per_page = 1000
    synced = 0

    while True:
        auth_users = _unwrap_auth_users(supabase.auth.admin.list_users(page=page, per_page=per_page))
        if not auth_users:
            break
        rows = [
            {
                "id": u.id,
                "email": u.email or None,
                "name": _user_display_name(u),
                "created_at": u.created_at,
            }
            for u in auth_users
        ]
        supabase.table("users").upsert(rows, on_conflict="id").execute()
        synced += len(rows)
        if len(auth_users) < per_page:
            break
        page += 1

    logger.info("users/backfill-mirror synced %d users", synced)
    return {"synced": synced}


@router.get("/users/{user_id}")
def admin_get_user_detail(
    user_id: str,
    current_user: UserInfo = Depends(require_support),
):
    """Full detail for one user -- identity, plan, and recent activity."""
    supabase = get_supabase()

    try:
        auth_resp = supabase.auth.admin.get_user_by_id(user_id)
    except Exception:
        raise HTTPException(status_code=404, detail="User not found")
    u = getattr(auth_resp, "user", auth_resp)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    profile_rows = supabase.table("user_profiles").select("*").eq("user_id", user_id).execute().data
    role_rows = supabase.table("user_roles").select("role").eq("user_id", user_id).execute().data
    submissions = (
        supabase.table("submissions")
        .select("id, scenario_id, module, score, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
        .data
    )

    return {
        "user_id": user_id,
        "email": u.email,
        "name": _user_display_name(u),
        "created_at": u.created_at,
        "last_sign_in_at": getattr(u, "last_sign_in_at", None),
        "role": role_rows[0]["role"] if role_rows else "user",
        "profile": profile_rows[0] if profile_rows else {},
        "recent_submissions": submissions,
        "moderation": _get_moderation_status(supabase, user_id),
    }


# ── IMPERSONATION ─────────────────────────────────────────────────────

class ImpersonateResponse(BaseModel):
    access_token: str
    refresh_token: str
    target_email: str
    target_name: str
    log_id: str


@router.post("/users/{user_id}/impersonate", response_model=ImpersonateResponse)
def admin_impersonate_user(
    user_id: str,
    current_user: UserInfo = Depends(require_admin),
):
    """Mint a real session for the target user so an admin can 'log in as'
    them for support/debugging. Uses Supabase's admin generate_link +
    verify_otp trick -- no email is sent, no password is touched or known.
    Every session is recorded in impersonation_log (who, whom, when)."""
    supabase = get_supabase()

    try:
        target = supabase.auth.admin.get_user_by_id(user_id)
    except Exception:
        raise HTTPException(status_code=404, detail="User not found")
    target_user = getattr(target, "user", target)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    if _target_is_staff(supabase, user_id):
        raise HTTPException(status_code=400, detail="Cannot impersonate another staff member")

    try:
        link = supabase.auth.admin.generate_link({"type": "magiclink", "email": target_user.email})
        auth_resp = get_auth_client().auth.verify_otp({
            "token_hash": link.properties.hashed_token,
            "type": "magiclink",
        })
    except Exception:
        logger.exception("impersonate: failed to mint session | target=%s", user_id)
        raise HTTPException(status_code=502, detail="Could not start impersonation session")

    session = auth_resp.session
    if not session:
        raise HTTPException(status_code=502, detail="Could not start impersonation session")

    meta = target_user.user_metadata or {}
    target_name = meta.get("name") or meta.get("full_name") or ""

    log = supabase.table("impersonation_log").insert({
        "admin_id": current_user.id,
        "admin_email": current_user.email,
        "target_user_id": user_id,
        "target_email": target_user.email,
    }).execute()

    logger.info("impersonate started | admin=%s target=%s", current_user.id, user_id)

    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "target_email": target_user.email,
        "target_name": target_name,
        "log_id": log.data[0]["id"],
    }


@router.post("/impersonation/{log_id}/end")
def admin_end_impersonation(
    log_id: str,
    current_user: UserInfo = Depends(require_admin),
):
    """Close out an impersonation session's log entry once the admin exits."""
    supabase = get_supabase()
    supabase.table("impersonation_log").update({
        "ended_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", log_id).execute()
    return {"success": True}


# ── MANUAL PLAN CHANGES ──────────────────────────────────────────────

ALLOWED_PLANS = {"free", "basic", "pro", "elite"}


class GrantPlanRequest(BaseModel):
    plan: str
    period_days: Optional[int] = None  # ignored when plan == "free"


@router.post("/users/{user_id}/plan")
def admin_set_user_plan(
    user_id: str,
    req: GrantPlanRequest,
    current_user: UserInfo = Depends(require_support),
):
    """Manually change a user's plan -- comp a free period, extend a
    subscription, or upgrade/downgrade by hand (refunds, support cases).

    Reuses grant_subscription_period, the same atomic RPC a real payment
    goes through (payments.py) -- a comped period behaves identically to
    a paid one for expiry/renewal purposes. Only the free-plan reset path
    skips it, since 'free' has no expiry period to grant. Existing
    razorpay_subscription_id/auto_renew_enabled are left untouched: this
    action is orthogonal to whatever auto-renew state already exists.
    """
    if req.plan not in ALLOWED_PLANS:
        raise HTTPException(status_code=400, detail=f"Invalid plan. Must be one of: {sorted(ALLOWED_PLANS)}")

    supabase = get_supabase()
    existing = supabase.table("user_profiles").select("user_id").eq("user_id", user_id).execute().data
    if not existing:
        raise HTTPException(status_code=404, detail="User profile not found")

    if req.plan == "free":
        supabase.table("user_profiles").update({
            "plan": "free",
            "subscription_status": "none",
            "plan_expires_at": None,
        }).eq("user_id", user_id).execute()
        _write_audit_log(supabase, current_user, "plan_changed", "user", target_id=user_id, detail={"plan": "free"})
        logger.info("admin plan change | admin=%s target=%s -> free", current_user.id, user_id)
        return {"success": True, "plan": "free"}

    period_days = req.period_days or PLAN_PERIOD_DAYS
    previous_plan = get_current_plan(user_id)
    supabase.table("user_profiles").update({"plan": req.plan}).eq("user_id", user_id).execute()
    grant_subscription_period(user_id, req.plan, previous_plan, period_days=period_days)

    _write_audit_log(
        supabase, current_user, "plan_changed", "user", target_id=user_id,
        detail={"plan": req.plan, "period_days": period_days, "previous_plan": previous_plan},
    )
    logger.info(
        "admin plan change | admin=%s target=%s -> %s (%d days)",
        current_user.id, user_id, req.plan, period_days,
    )
    return {"success": True, "plan": req.plan}


# ── MANUAL BONUS SESSIONS (bug reports, goodwill credits) ────────────

class GrantBonusSessionsRequest(BaseModel):
    amount: int = Field(..., description="Sessions to add; use a negative number to correct an over-grant")
    reason: str


@router.post("/users/{user_id}/bonus-sessions")
def admin_grant_bonus_sessions(
    user_id: str,
    req: GrantBonusSessionsRequest,
    current_user: UserInfo = Depends(require_support),
):
    """Manually top up a user's bonus-session wallet -- the same wallet
    referrals credit (see reward_referral in the referrals migration), used
    here for things a referral can't detect: a valid bug report, a content
    mistake flagged by a student, or a support goodwill gesture. Rare,
    human-judged action, so a plain read-then-write is fine -- no need for
    the atomic RPC referrals uses for its high-frequency, unattended path.
    """
    supabase = get_supabase()
    existing = supabase.table("user_profiles").select("bonus_sessions").eq("user_id", user_id).execute().data
    if not existing:
        raise HTTPException(status_code=404, detail="User profile not found")

    new_total = max(0, existing[0].get("bonus_sessions", 0) + req.amount)
    supabase.table("user_profiles").update({"bonus_sessions": new_total}).eq("user_id", user_id).execute()

    _write_audit_log(
        supabase, current_user, "bonus_sessions_granted", "user", target_id=user_id,
        detail={"amount": req.amount, "new_total": new_total, "reason": req.reason},
    )
    logger.info(
        "admin bonus sessions | admin=%s target=%s amount=%+d reason=%s",
        current_user.id, user_id, req.amount, req.reason,
    )
    return {"success": True, "bonus_sessions": new_total}


# ── MODERATION: SUSPEND / BAN / REINSTATE / DELETE ───────────────────

# Supabase's admin-native lockout: ban_duration blocks new sign-ins and
# refresh-token exchanges at the GoTrue server itself, no schema of our
# own needed for the block. It cannot revoke an already-issued access
# token before it naturally expires (~1hr) -- there is no server-side
# JWT revocation short of that; this is a known, accepted limit of
# stateless JWTs, not something we can close without a per-request
# revocation check we don't otherwise need.
SUSPEND_BAN_DURATION = "720h"   # 30 days, self-expiring
PERMANENT_BAN_DURATION = "876000h"  # ~100 years -- Supabase's documented "permanent" convention

MODERATION_ACTIONS = {"suspend", "ban", "reinstate"}


class ModerateRequest(BaseModel):
    action: str
    reason: str


def _get_moderation_status(supabase, user_id: str) -> Dict[str, Any]:
    """Derives current suspend/ban state from the most recent log entry --
    there's nowhere else to read it back from (see note on gotrue's User
    model above the ban-duration constants)."""
    rows = (
        supabase.table("moderation_log")
        .select("action, reason, expires_at, created_at")
        .eq("target_user_id", user_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        return {"status": "active"}
    latest = rows[0]
    if latest["action"] == "ban":
        return {"status": "banned", "reason": latest["reason"], "since": latest["created_at"]}
    if latest["action"] == "suspend":
        expires_at = latest.get("expires_at")
        if expires_at and datetime.fromisoformat(expires_at) > datetime.now(timezone.utc):
            return {"status": "suspended", "reason": latest["reason"], "until": expires_at}
    return {"status": "active"}


@router.post("/users/{user_id}/moderate")
def admin_moderate_user(
    user_id: str,
    req: ModerateRequest,
    current_user: UserInfo = Depends(require_support),
):
    """Suspend (30-day, self-expiring), ban (indefinite), or reinstate a
    user. Blocks new logins and token refreshes via Supabase's own
    ban_duration -- see the constants above for what this can't do."""
    if req.action not in MODERATION_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid action. Must be one of: {sorted(MODERATION_ACTIONS)}")
    if not req.reason.strip():
        raise HTTPException(status_code=400, detail="A reason is required")

    supabase = get_supabase()

    if _target_is_staff(supabase, user_id):
        raise HTTPException(status_code=400, detail="Cannot moderate another staff member")

    try:
        target = supabase.auth.admin.get_user_by_id(user_id)
    except Exception:
        raise HTTPException(status_code=404, detail="User not found")
    target_user = getattr(target, "user", target)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    expires_at = None
    if req.action == "suspend":
        ban_duration = SUSPEND_BAN_DURATION
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=720)).isoformat()
    elif req.action == "ban":
        ban_duration = PERMANENT_BAN_DURATION
    else:
        ban_duration = "none"

    try:
        supabase.auth.admin.update_user_by_id(user_id, {"ban_duration": ban_duration})
    except Exception:
        logger.exception("moderate: failed to set ban_duration | target=%s action=%s", user_id, req.action)
        raise HTTPException(status_code=502, detail="Could not update user's access")

    supabase.table("moderation_log").insert({
        "admin_id": current_user.id,
        "admin_email": current_user.email,
        "target_user_id": user_id,
        "target_email": target_user.email,
        "action": req.action,
        "reason": req.reason.strip(),
        "expires_at": expires_at,
    }).execute()

    logger.info("moderate | admin=%s target=%s action=%s", current_user.id, user_id, req.action)
    return {"success": True, **_get_moderation_status(supabase, user_id)}


class DeleteUserRequest(BaseModel):
    reason: str


@router.post("/users/{user_id}/delete")
def admin_delete_user(
    user_id: str,
    req: DeleteUserRequest,
    current_user: UserInfo = Depends(require_owner),
):
    """Permanently delete a user's account and data. Logged before the
    delete runs, so the record survives even though target_user_id can
    no longer be looked up afterward (see the migration's note on why
    that column isn't a foreign key)."""
    if not req.reason.strip():
        raise HTTPException(status_code=400, detail="A reason is required")

    supabase = get_supabase()

    if _target_is_staff(supabase, user_id):
        raise HTTPException(status_code=400, detail="Cannot delete another staff member")

    try:
        target = supabase.auth.admin.get_user_by_id(user_id)
    except Exception:
        raise HTTPException(status_code=404, detail="User not found")
    target_user = getattr(target, "user", target)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    supabase.table("moderation_log").insert({
        "admin_id": current_user.id,
        "admin_email": current_user.email,
        "target_user_id": user_id,
        "target_email": target_user.email,
        "action": "delete",
        "reason": req.reason.strip(),
    }).execute()

    for table in _USER_OWNED_TABLES:
        supabase.table(table).delete().eq("user_id", user_id).execute()

    try:
        supabase.auth.admin.delete_user(user_id)
    except Exception:
        logger.exception("admin delete_user failed | admin=%s target=%s", current_user.id, user_id)
        raise HTTPException(status_code=500, detail="User data was cleared but the auth account could not be deleted. Contact support.")

    logger.info("admin delete | admin=%s target=%s", current_user.id, user_id)
    return {"success": True}


@router.get("/audit-log")
def admin_get_audit_log(
    limit: int = 100,
    offset: int = 0,
    current_user: UserInfo = Depends(require_analyst),
):
    """Unified action history: audit_log (role/plan/content/settings
    changes), moderation_log (suspend/ban/reinstate/delete), and
    impersonation_log (log-in-as-user sessions) combined into one
    chronological timeline -- since that's what an admin actually wants to
    see, not three separate pages.

    Reads admin_audit_timeline, a UNION ALL view over the three tables
    (see backend/migrations/2026-07-18_audit_timeline_view.sql), so this
    is one indexed, paginated query instead of three REST round-trips
    merged/sorted in Python -- the old version had no offset support at
    all, so the panel could only ever see the most recent page.

    Fetches one extra row past `limit` to detect "is there a next page"
    without a separate COUNT(*) over the union.
    """
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    supabase = get_supabase()

    rows = (
        supabase.table("admin_audit_timeline")
        .select("*")
        .order("created_at", desc=True)
        .range(offset, offset + limit)
        .execute()
        .data
    )
    return {"entries": rows[:limit], "has_more": len(rows) > limit}


# ── ANALYTICS ───────────────────────────────────────────────────────

@router.get("/stats")
def admin_get_stats(current_user: UserInfo = Depends(require_analyst)):
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

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    signups_today = supabase.table("user_roles").select("user_id", count="exact").gte("created_at", today_start).execute().count or 0

    active_user_ids = {
        row["user_id"]
        for row in supabase.table("submissions").select("user_id").gte("created_at", today_start).execute().data
    }

    # Real MRR: every user whose subscription is currently active (or in
    # its grace window, per get_plan_from_profile) times that plan's
    # monthly price -- not "money that happened to land this month".
    paid_profiles = supabase.table("user_profiles").select("plan, plan_expires_at").neq("plan", "free").execute().data
    mrr_inr = sum(
        PLAN_PRICE_INR.get(get_plan_from_profile(row, now=now), 0)
        for row in paid_profiles
    )

    ai_cost_today_rows = supabase.table("ai_usage_events").select("cost_usd").gte("created_at", today_start).execute().data
    ai_cost_today_usd = sum(row["cost_usd"] for row in ai_cost_today_rows)

    return {
        "total_users": total_users,
        "total_submissions": total_submissions,
        "total_active_scenarios": total_scenarios,
        "submissions_by_module": module_counts,
        "unresolved_logs": unresolved_count or 0,
        "signups_today": signups_today,
        "active_today": len(active_user_ids),
        "mrr_inr": mrr_inr,
        "ai_cost_today_usd": ai_cost_today_usd,
    }


@router.get("/analytics")
def admin_get_founder_analytics(
    months: int = 6,
    current_user: UserInfo = Depends(require_analyst),
):
    """Founder-dashboard SaaS metrics: MRR/ARR, subscribers, revenue,
    churn, plan distribution, monthly trend series, and insights. See
    app/services/founder_metrics.py for the calculation -- kept separate
    from /stats so that endpoint's existing response shape never changes.
    """
    return get_founder_metrics(get_supabase(), months=months)


@router.get("/ai-costs")
def admin_get_ai_costs(current_user: UserInfo = Depends(require_analyst)):
    """AI cost/margin dashboard: cost by call type/provider/model, gross
    margin per plan tier (price minus cost-to-serve), top spenders, and a
    30-day daily cost trend. See app/services/ai_cost_metrics.py for the
    calculation -- reads ai_usage_events, the per-call cost log that
    module's docstring already designates for margin reporting.
    """
    supabase = get_supabase()
    metrics = get_ai_cost_metrics(supabase)

    # Overall margin needs both sides -- this month's cash collected
    # (founder_metrics) against this month's AI spend, same currency.
    revenue_this_month_inr = get_founder_metrics(supabase, months=2)["revenue_this_month_inr"]
    cost_this_month_inr = metrics["cost_this_month_usd"] * metrics["usd_to_inr_rate"]
    metrics["revenue_this_month_inr"] = revenue_this_month_inr
    metrics["overall_gross_margin_pct"] = (
        round((revenue_this_month_inr - cost_this_month_inr) / revenue_this_month_inr * 100, 1)
        if revenue_this_month_inr else None
    )
    return metrics


# ── FAILED PAYMENTS ───────────────────────────────────────────────────

@router.get("/failed-payments")
def admin_get_failed_payments(
    limit: int = 100,
    current_user: UserInfo = Depends(require_support),
):
    """Declined/failed Razorpay charges (payment.failed webhook, see
    payments.py) so a human can follow up before the user silently loses
    access at renewal. user_id can be null -- a failed attempt doesn't
    always carry one -- so email is best-effort, not guaranteed.
    """
    limit = max(1, min(limit, 500))
    supabase = get_supabase()
    rows = (
        supabase.table("failed_payments").select("*")
        .order("created_at", desc=True).limit(limit).execute().data
    )

    emails = _emails_by_user_id(supabase, {r["user_id"] for r in rows if r.get("user_id")})
    return [{**row, "email": emails.get(row.get("user_id"), "")} for row in rows]


FAILED_PAYMENT_REMINDER_LOOKBACK_DAYS = 3


@router.post("/failed-payments/send-reminders")
def admin_send_failed_payment_reminders(_=Depends(require_admin_or_cron)):
    """Emails users whose payment failed recently and haven't been reminded
    yet (see rows_due_for_failed_payment_reminder). Bounded lookback so a
    decline from weeks ago doesn't surface a stale email today. Wired to
    run daily via external cron, same as the other reminder crons."""
    supabase = get_supabase()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=FAILED_PAYMENT_REMINDER_LOOKBACK_DAYS)).isoformat()

    rows = (
        supabase.table("failed_payments").select("*")
        .is_("reminder_sent_at", "null")
        .gte("created_at", cutoff)
        .execute().data
    )
    due = rows_due_for_failed_payment_reminder(rows)
    if not due:
        return {"sent": 0, "eligible": 0}

    emails = _emails_by_user_id(supabase, {r["user_id"] for r in due})

    sent = 0
    for row in due:
        email = emails.get(row["user_id"])
        if not email:
            continue
        html = render_failed_payment_reminder(row.get("plan_id"), row.get("reason"))
        if send_email(email, "We couldn't process your SpeakOET payment", html):
            supabase.table("failed_payments").update({
                "reminder_sent_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", row["id"]).execute()
            sent += 1

    logger.info("failed-payment reminders sent: %d/%d", sent, len(due))
    return {"sent": sent, "eligible": len(due)}


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


TRANSCRIPT_RETENTION_DAYS = 90


@router.post("/transcripts/prune")
def admin_prune_transcripts(_=Depends(require_admin_or_cron)):
    """Delete session transcripts older than TRANSCRIPT_RETENTION_DAYS. Wired
    to run weekly via external cron, same as logs/prune -- caps storage growth
    and narrows privacy exposure per the retention disclosed in the privacy
    policy. Safe to re-run: deletes by cutoff."""
    supabase = get_supabase()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=TRANSCRIPT_RETENTION_DAYS)).isoformat()
    try:
        deleted = supabase.table("session_transcripts").delete().lt("created_at", cutoff).execute()
    except Exception:
        logger.exception("transcripts/prune failed")
        raise HTTPException(status_code=502, detail="Transcript prune failed")
    count = len(deleted.data or [])
    logger.info("transcripts/prune deleted %d rows older than %s", count, cutoff)
    return {"deleted": count}


# ── SUBSCRIPTION MANAGEMENT ─────────────────────────────────────────

@router.get("/subscriptions/expiring-soon")
def admin_get_expiring_soon(
    days: int = 7,
    current_user: UserInfo = Depends(require_support),
):
    """Paid users whose plan_expires_at falls within the next `days` days --
    a heads-up list to reach out before they silently drop to free. Same
    subscription_status="active" + plan_expires_at filter convention as
    admin_sweep_expired_subscriptions below, just the near side of expiry
    instead of the past side. Included regardless of auto_renew_enabled --
    an auto-charge can still fail (see failed_payments), so "will renew
    itself" isn't a reason to skip someone here.
    """
    days = max(1, min(days, 30))
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)
    supabase = get_supabase()

    rows = (
        supabase.table("user_profiles")
        .select("user_id, plan, plan_expires_at, subscription_status, auto_renew_enabled, expiry_reminder_sent_for")
        .eq("subscription_status", "active")
        .gte("plan_expires_at", now.isoformat())
        .lte("plan_expires_at", cutoff.isoformat())
        .order("plan_expires_at")
        .execute().data
    )

    emails = _emails_by_user_id(supabase, {r["user_id"] for r in rows})
    return [{**row, "email": emails.get(row["user_id"], "")} for row in rows]


@router.post("/subscriptions/expiring-soon/send-reminders")
def admin_send_expiring_reminders(days: int = 7, _=Depends(require_admin_or_cron)):
    """Emails every paid user expiring within `days` days who hasn't already
    been reminded for this expiry cycle (see rows_due_for_expiry_reminder),
    then stamps expiry_reminder_sent_for so tomorrow's run skips them.
    Wired to run daily via external cron, same as sweep-expired below."""
    days = max(1, min(days, 30))
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)
    supabase = get_supabase()

    rows = (
        supabase.table("user_profiles")
        .select("user_id, plan, plan_expires_at, subscription_status, expiry_reminder_sent_for")
        .eq("subscription_status", "active")
        .gte("plan_expires_at", now.isoformat())
        .lte("plan_expires_at", cutoff.isoformat())
        .execute().data
    )
    due = rows_due_for_expiry_reminder(rows)
    if not due:
        return {"sent": 0, "eligible": 0}

    emails = _emails_by_user_id(supabase, {r["user_id"] for r in due})

    sent = 0
    for row in due:
        email = emails.get(row["user_id"])
        if not email:
            continue
        html = render_expiry_reminder(row["plan"], row["plan_expires_at"])
        if send_email(email, "Your SpeakOET plan is expiring soon", html):
            supabase.table("user_profiles").update({
                "expiry_reminder_sent_for": row["plan_expires_at"],
            }).eq("user_id", row["user_id"]).execute()
            sent += 1

    logger.info("expiring-soon reminders sent: %d/%d", sent, len(due))
    return {"sent": sent, "eligible": len(due)}


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


@router.get("/users/{user_id}/payments")
def admin_get_user_payments(
    user_id: str,
    current_user: UserInfo = Depends(require_support),
):
    """Billing history for one user -- so support can check what was
    actually paid before touching a plan or issuing a refund, instead of
    trusting user_profiles.plan alone. payments.user_id is already
    indexed (see 2026-07-13_security_perf_hardening.sql), and one user's
    history is small, so no pagination.
    """
    supabase = get_supabase()
    rows = (
        supabase.table("payments")
        .select("id, order_id, payment_id, plan_id, amount, currency, status, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
        .data
    )
    return {"payments": rows}


@router.get("/users/{user_id}/transcripts")
def admin_get_user_transcripts(
    user_id: str,
    current_user: UserInfo = Depends(require_admin),
):
    """Voice roleplay session transcripts for one user, for background-check
    and account-safety review. Admin-only (not support) since transcripts are
    the full conversation content, not just metadata -- see
    2026-07-21_session_transcripts.sql. Retained 90 days (transcripts/prune)."""
    rows = (
        get_supabase().table("session_transcripts")
        .select("id, session_usage_id, scenario_id, transcript, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
        .data
    )
    return {"transcripts": rows}


@router.post("/users/{user_id}/subscription/cancel")
def admin_cancel_user_subscription(
    user_id: str,
    current_user: UserInfo = Depends(require_support),
):
    """Admin-side equivalent of payments.cancel_subscription -- for
    support cases where the user calls or emails in asking to cancel
    instead of clicking it themselves. Turns off auto-renew only; the
    current plan stays active until plan_expires_at, same as self-serve.
    """
    supabase = get_supabase()
    profile = (
        supabase.table("user_profiles")
        .select("razorpay_subscription_id, auto_renew_enabled")
        .eq("user_id", user_id)
        .execute()
    )
    if not profile.data or not profile.data[0].get("razorpay_subscription_id"):
        raise HTTPException(status_code=400, detail="No auto-renewing subscription to cancel")

    subscription_id = profile.data[0]["razorpay_subscription_id"]

    client = get_razorpay_client()
    try:
        client.subscription.cancel(subscription_id, {"cancel_at_cycle_end": 1})
    except Exception:
        logger.exception(
            "admin cancel-subscription failed | admin=%s target=%s subscription_id=%s",
            current_user.id, user_id, subscription_id,
        )
        raise HTTPException(status_code=500, detail="Could not cancel subscription. Please try again.")

    supabase.table("user_profiles").update({"auto_renew_enabled": False}).eq("user_id", user_id).execute()

    _write_audit_log(
        supabase, current_user, "subscription_cancelled", "user", target_id=user_id,
        detail={"subscription_id": subscription_id},
    )
    logger.info("admin cancel-subscription | admin=%s target=%s", current_user.id, user_id)
    return {"success": True, "message": "Auto-renew turned off. Plan stays active until it expires."}


# ── REFUNDS ───────────────────────────────────────────────────────────

class RefundRequest(BaseModel):
    amount: Optional[int] = None  # paise; defaults to the full original payment
    reason: str = Field(..., min_length=1, max_length=500)


@router.post("/payments/{payment_id}/refund")
def admin_refund_payment(
    payment_id: str,
    req: RefundRequest,
    current_user: UserInfo = Depends(require_admin),
):
    """Issue a real Razorpay refund for one payment and roll back the plan
    it granted. Admin-tier (not support) since this moves real money,
    unlike the free-plan comp path in admin_set_user_plan.

    Downgrade/audit-log/idempotency all live in payments._process_refund,
    shared with the refund.created webhook -- that webhook is what catches
    a refund issued directly from the Razorpay dashboard instead of here.
    """
    supabase = get_supabase()
    payment_row = (
        supabase.table("payments")
        .select("amount, currency")
        .eq("payment_id", payment_id)
        .limit(1)
        .execute()
    )
    if not payment_row.data:
        raise HTTPException(status_code=404, detail="Payment not found")

    amount = req.amount if req.amount is not None else payment_row.data[0]["amount"]
    if amount <= 0 or amount > payment_row.data[0]["amount"]:
        raise HTTPException(status_code=400, detail="Invalid refund amount")

    client = get_razorpay_client()
    try:
        refund = client.payment.refund(payment_id, {
            "amount": amount,
            "speed": "normal",
            "notes": {"reason": req.reason, "admin_id": current_user.id},
        })
    except Exception:
        logger.exception(
            "admin refund failed | admin=%s payment_id=%s amount=%s", current_user.id, payment_id, amount,
        )
        raise HTTPException(status_code=500, detail="Could not process refund with Razorpay. Please try again.")

    result = _process_refund(
        razorpay_refund_id=refund["id"],
        payment_id=payment_id,
        amount=refund["amount"],
        reason=req.reason,
        initiated_by="admin",
        admin=current_user,
    )

    logger.info(
        "admin refund | admin=%s payment_id=%s razorpay_refund_id=%s amount=%s",
        current_user.id, payment_id, refund["id"], amount,
    )
    return {
        "success": True,
        "razorpay_refund_id": refund["id"],
        "amount": refund["amount"],
        "downgraded": result.get("downgraded", False),
    }
