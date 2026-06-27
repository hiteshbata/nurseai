from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.supabase import get_supabase
from app.schemas.user import UserCreate, UserLogin, UserResponse
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

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserInfo:
    supabase = get_supabase()
    try:
        resp = supabase.auth.get_user(credentials.credentials)
        user = resp.user
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        metadata = user.user_metadata or {}
        name = metadata.get("name") or metadata.get("full_name") or user.email or ""
        return UserInfo(
            id=user.id,
            email=user.email,
            name=name,
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

@router.post("/register")
async def register(user: UserCreate):
    supabase = get_supabase()
    resp = supabase.auth.sign_up({
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
async def login(user: UserLogin):
    supabase = get_supabase()
    try:
        resp = supabase.auth.sign_in_with_password({
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
async def get_current_user_info(
    current_user: UserInfo = Depends(get_current_user),
):
    supabase = get_supabase()
    profile = supabase.table("user_profiles").select("onboarding_completed").eq("user_id", current_user.id).execute()
    onboarding_completed = False
    if profile.data:
        onboarding_completed = profile.data[0].get("onboarding_completed", False)
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "onboarding_completed": onboarding_completed,
    }
