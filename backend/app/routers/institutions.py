from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.supabase import get_supabase
from app.routers.auth import UserInfo, _client_ip, get_current_user

router = APIRouter(prefix="/institutions", tags=["institutions"])

# NOTE: staff-facing invite *creation* used to live here too (POST
# /institutions/invites, body-scoped institution_id). It independently
# reimplemented the same insert now centralized in institution.py's
# _create_invite_row helper, had zero frontend/QA callers (confirmed by
# repo-wide grep 2026-09-06), and has been superseded by
# POST /admin/institutions/{institution_id}/invites (admin_institutions.py,
# same require_admin staff auth, path-scoped institution_id, uses the shared
# helper). Removed rather than migrated onto the helper to avoid maintaining
# a second staff create route with identical semantics.

preview_rate_limiter = SlidingWindowRateLimiter(
    max_calls=30, window_seconds=60, name="institution_invite_preview"
)

_INVITE_NOT_FOUND = HTTPException(
    status_code=404, detail="Invitation not found or no longer valid"
)


@router.get("/invites/{token}")
def get_invite_preview(token: str, request: Request):
    """Public, token-gated. Never returns the raw token or any internal id --
    see spec 2026-08-26 §5.2 for the exact allow-list."""
    if preview_rate_limiter.is_rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many requests. Try again shortly.")

    supabase = get_supabase()
    # Explicit, minimal column lists -- not select("*") -- even though the
    # response below is already allow-listed. Keeps the DB read itself from
    # ever pulling token/id/role/created_by/created_at or institution
    # contact_email/speaking_sessions_per_month/created_at, regardless of
    # what the response-building code does later.
    invites = (
        supabase.table("institution_invites")
        .select("institution_id, status, expires_at, max_uses, use_count")
        .eq("token", token).eq("status", "active").execute()
    )
    if not invites.data:
        raise _INVITE_NOT_FOUND
    invite = invites.data[0]

    if invite.get("expires_at"):
        expires_at = datetime.fromisoformat(invite["expires_at"].replace("Z", "+00:00"))
        if expires_at <= datetime.now(timezone.utc):
            raise _INVITE_NOT_FOUND

    max_uses = invite.get("max_uses")
    if max_uses is not None and invite.get("use_count", 0) >= max_uses:
        raise _INVITE_NOT_FOUND

    institutions = (
        supabase.table("institutions")
        .select("name, logo_url, status")
        .eq("id", invite["institution_id"]).eq("status", "active").execute()
    )
    if not institutions.data:
        raise _INVITE_NOT_FOUND
    institution = institutions.data[0]

    modules = (
        supabase.table("institution_modules")
        .select("module")
        .eq("institution_id", invite["institution_id"]).eq("enabled", True).execute()
    )

    return {
        "institution_name": institution["name"],
        "logo_url": institution.get("logo_url"),
        "modules": [m["module"] for m in modules.data],
        "expires_at": invite.get("expires_at"),
    }


@router.post("/invites/{token}/accept")
def accept_institution_invite_endpoint(
    token: str,
    current_user: UserInfo = Depends(get_current_user),
):
    """Authenticated. institution/role/status are entirely server-derived --
    see spec 2026-08-26 §5.3/§6. Delegates the atomic check-and-write to the
    accept_institution_invite Postgres function (Task 1)."""
    if current_user.is_anonymous:
        # Authorization boundary, not a UX rule -- get_current_user returns
        # a valid UserInfo for an anonymous/guest Supabase session, so this
        # must be checked explicitly before the RPC is ever reached. The
        # frontend already hides the Accept button for an anonymous
        # session, but that alone does not stop a direct POST.
        raise HTTPException(
            status_code=401,
            detail="A registered account is required to accept this invitation",
        )

    supabase = get_supabase()
    result = supabase.rpc(
        "accept_institution_invite",
        {"p_token": token, "p_user_id": current_user.id},
    ).execute()

    row = result.data[0] if result.data else {"result_status": "invalid"}
    if row["result_status"] not in ("joined", "already_member"):
        raise HTTPException(status_code=400, detail="This invitation cannot be used")

    return {
        "status": row["result_status"],
        "institution_name": row["institution_name"],
        "modules": row["modules"] or [],
    }
