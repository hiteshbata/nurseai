import time
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.supabase import get_supabase, get_auth_client
from app.schemas.user import UserCreate, UserLogin
from app.services.plan_gating import get_plan_from_profile, get_effective_subscription_status
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict

class UserInfo(BaseModel):
    id: str
    email: Optional[str] = None
    name: Optional[str] = None

_user_role_cache: dict[str, float] = {}
USER_ROLE_CACHE_TTL = 900  # 15 minutes

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserInfo:
    supabase = get_supabase()
    auth_client = get_auth_client()
    try:
        resp = auth_client.auth.get_user(credentials.credentials)
        user = resp.user
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        metadata = user.user_metadata or {}
        name = metadata.get("name") or metadata.get("full_name") or user.email or ""

        now = time.time()
        last_upsert = _user_role_cache.get(user.id, 0)
        if now - last_upsert > USER_ROLE_CACHE_TTL:
            # ignore_duplicates=True -> INSERT ... ON CONFLICT DO NOTHING.
            # Only creates the row for brand-new users; never overwrites an
            # existing role (e.g. admin) back to the default.
            supabase.table("user_roles").upsert({
                "user_id": user.id,
                "role": "user",
            }, on_conflict="user_id", ignore_duplicates=True).execute()
            # Opportunistically prune stale entries so the dict never grows
            # unbounded across the process lifetime.
            expired_keys = [
                key for key, ts in _user_role_cache.items()
                if now - ts > USER_ROLE_CACHE_TTL
            ]
            for key in expired_keys:
                del _user_role_cache[key]
            _user_role_cache[user.id] = now

        return UserInfo(
            id=user.id,
            email=user.email,
            name=name,
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

@router.post("/register")
def register(user: UserCreate):
    auth_client = get_auth_client()
    resp = auth_client.auth.sign_up({
        "email": user.email,
        "password": user.password,
        "options": {"data": {"name": user.name}},
    })
    if not resp.user:
        raise HTTPException(status_code=400, detail="Registration failed")
    return {
        "id": resp.user.id,
        "email": resp.user.email,
        "name": user.name,
    }

@router.post("/login", response_model=LoginResponse)
def login(user: UserLogin):
    auth_client = get_auth_client()
    try:
        resp = auth_client.auth.sign_in_with_password({
            "email": user.email,
            "password": user.password,
        })
        session = resp.session
        metadata = resp.user.user_metadata or {}
        return LoginResponse(
            access_token=session.access_token,
            token_type="bearer",
            user={
                "id": resp.user.id,
                "email": resp.user.email,
                "name": metadata.get("name", resp.user.email),
            },
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid credentials: {str(e)}")

@router.get("/me")
def get_current_user_info(
    current_user: UserInfo = Depends(get_current_user),
):
    supabase = get_supabase()
    profile = supabase.table("user_profiles").select(
        "onboarding_completed, plan, plan_expires_at, subscription_status"
    ).eq("user_id", current_user.id).execute()

    onboarding_completed = False
    plan = "free"
    plan_expires_at = None
    subscription_status = "none"
    if profile.data:
        profile_row = profile.data[0]
        onboarding_completed = profile_row.get("onboarding_completed", False)
        plan = get_plan_from_profile(profile_row)
        plan_expires_at = profile_row.get("plan_expires_at")
        subscription_status = get_effective_subscription_status(profile_row)

    role_data = supabase.table("user_roles").select("role").eq("user_id", current_user.id).execute()
    role = role_data.data[0]["role"] if role_data.data else "user"

    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "onboarding_completed": onboarding_completed,
        "role": role,
        "plan": plan,
        "plan_expires_at": plan_expires_at,
        "subscription_status": subscription_status,
    }
