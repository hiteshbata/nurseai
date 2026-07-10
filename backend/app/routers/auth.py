import logging
import time
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from gotrue.errors import AuthApiError
from app.core.config import settings
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.redis_client import get_redis
from app.core.supabase import get_supabase, get_auth_client
from app.schemas.user import UserCreate, UserLogin
from app.services.plan_gating import get_plan_from_profile, get_effective_subscription_status
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()
logger = logging.getLogger(__name__)

# Supabase now signs access tokens asymmetrically (ES256/RS256) by default;
# older projects may still use the shared HS256 JWT secret. Fetch/cache the
# JWKS lazily so we verify against whichever key kind is actually in use.
_jwks_client: Optional["jwt.PyJWKClient"] = None


def _get_jwks_client() -> "jwt.PyJWKClient":
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(
            f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json",
            cache_keys=True,
        )
    return _jwks_client

# ponytail: keyed by IP, not per-account -- stops single-source brute force
# and mass fake-account creation without needing a Depends/decorator layer.
_login_rate_limiter = SlidingWindowRateLimiter(10, 300, name="auth:login")
_register_rate_limiter = SlidingWindowRateLimiter(5, 3600, name="auth:register")


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict

class UserInfo(BaseModel):
    id: str
    email: Optional[str] = None
    name: Optional[str] = None

_user_role_cache: dict[str, float] = {}  # local fallback only; used when REDIS_URL is unset
USER_ROLE_CACHE_TTL = 900  # 15 minutes


def _role_recently_upserted(user_id: str) -> bool:
    """True if a user_roles row was already ensured for this user within the
    TTL. Backed by Redis (shared across instances/workers) when REDIS_URL is
    set; falls back to a per-process dict for local dev otherwise.
    """
    client = get_redis()
    if client is not None:
        return client.exists(f"role_upserted:{user_id}") == 1
    return time.time() - _user_role_cache.get(user_id, 0) <= USER_ROLE_CACHE_TTL


def _mark_role_upserted(user_id: str) -> None:
    client = get_redis()
    if client is not None:
        client.set(f"role_upserted:{user_id}", "1", ex=USER_ROLE_CACHE_TTL)
        return
    now = time.time()
    # Opportunistically prune stale entries so the dict never grows
    # unbounded across the process lifetime.
    expired_keys = [k for k, ts in _user_role_cache.items() if now - ts > USER_ROLE_CACHE_TTL]
    for k in expired_keys:
        del _user_role_cache[k]
    _user_role_cache[user_id] = now


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserInfo:
    supabase = get_supabase()
    try:
        # Verify the access token's signature/expiry locally instead of
        # calling Supabase Auth over the network on every request.
        token = credentials.credentials
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "")
        if alg.startswith("HS"):
            # Legacy Supabase projects: shared JWT secret (Project Settings -> API -> JWT Secret).
            signing_key = settings.SUPABASE_JWT_SECRET
        else:
            # Current Supabase default: asymmetric signing (ES256/RS256) verified via JWKS.
            signing_key = _get_jwks_client().get_signing_key_from_jwt(token).key
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=[alg],
            audience="authenticated",
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        metadata = payload.get("user_metadata") or {}
        email = payload.get("email")
        name = metadata.get("name") or metadata.get("full_name") or email or ""

        if not _role_recently_upserted(user_id):
            # ignore_duplicates=True -> INSERT ... ON CONFLICT DO NOTHING.
            # Only creates the row for brand-new users; never overwrites an
            # existing role (e.g. admin) back to the default.
            supabase.table("user_roles").upsert({
                "user_id": user_id,
                "role": "user",
            }, on_conflict="user_id", ignore_duplicates=True).execute()
            _mark_role_upserted(user_id)

        return UserInfo(
            id=user_id,
            email=email,
            name=name,
        )
    except HTTPException:
        raise
    except jwt.PyJWTError as e:
        logger.warning("JWT verification failed: %s", e)
        raise HTTPException(status_code=401, detail="Authentication failed")

@router.post("/register")
def register(user: UserCreate, request: Request):
    if _register_rate_limiter.is_rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many registration attempts — please try again later.")
    auth_client = get_auth_client()
    try:
        resp = auth_client.auth.sign_up({
            "email": user.email,
            "password": user.password,
            "options": {"data": {"name": user.name}},
        })
    except AuthApiError as e:
        logger.warning("Registration failed for %s: %s", user.email, e.message)
        msg = e.message.lower()
        if "already registered" in msg or "already exists" in msg:
            detail = "An account with this email already exists."
        elif "password" in msg:
            detail = "Password does not meet requirements (minimum 6 characters)."
        elif "rate limit" in msg:
            detail = "Too many signup attempts — please try again later."
        elif "sending" in msg or "confirmation" in msg:
            detail = "We couldn't send the confirmation email. Please try again shortly."
        else:
            detail = "Registration failed."
        raise HTTPException(status_code=400, detail=detail)
    except Exception as e:
        logger.warning("Registration failed for %s: %s", user.email, e)
        raise HTTPException(status_code=400, detail="Registration failed")
    if not resp.user:
        raise HTTPException(status_code=400, detail="Registration failed")
    return {
        "id": resp.user.id,
        "email": resp.user.email,
        "name": user.name,
    }

@router.post("/login", response_model=LoginResponse)
def login(user: UserLogin, request: Request):
    if _login_rate_limiter.is_rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many login attempts — please try again later.")
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
        logger.warning("Login failed for %s: %s", user.email, e)
        raise HTTPException(status_code=401, detail="Invalid credentials")

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
