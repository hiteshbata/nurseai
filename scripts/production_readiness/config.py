"""Hard-coded expected production identifiers and credential lookup.

This is the single source of truth for "what production is supposed to look
like." Every check compares live state against these constants -- nothing
here is fetched or inferred, so a value can only be wrong if someone edits
this file.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

PRODUCTION_SUPABASE_PROJECT_REF = "lgwaiwasnjjohqkeizdz"
QA_SUPABASE_PROJECT_REF = "wpowzyyzhrxdqujrvxdq"

EXPECTED_VERCEL_PROJECT = "nurseai"
EXPECTED_VERCEL_PROJECT_ID = "prj_4CGDydLpnaoJnGIftNSoJbSWLcMU"

EXPECTED_PRODUCTION_BRANCH = "main"
EXPECTED_PRODUCTION_COMMIT = "2606cfd8"

EXPECTED_FRONTEND_URL = "https://www.speakoet.com"
EXPECTED_BACKEND_URL = "https://api.speakoet.com"

EXPECTED_PRODUCTION_SUPABASE_URL = f"https://{PRODUCTION_SUPABASE_PROJECT_REF}.supabase.co"
EXPECTED_QA_SUPABASE_URL = f"https://{QA_SUPABASE_PROJECT_REF}.supabase.co"

EXPECTED_AUTH_CALLBACK_URL = f"{EXPECTED_FRONTEND_URL}/auth/callback"

INSTITUTION_MIGRATIONS = (
    "20260826000000_institution_foundation.sql",
    "20260827000000_institution_invite_accept.sql",
)

INSTITUTION_TABLES = (
    "institutions",
    "institution_members",
    "institution_modules",
    "institution_invites",
)

INSTITUTION_RPC = "accept_institution_invite"

REQUIRED_RENDER_ENV_VARS = (
    "ENVIRONMENT",
    "SUPABASE_URL",
    "FRONTEND_URL",
    "PRODUCTION_SUPABASE_PROJECT_REF",
)

FRONTEND_ROUTES_MUST_NOT_404 = (
    "/institution",
    "/institution/students",
    "/institution/invites",
)

MALICIOUS_REDIRECT_TARGETS = (
    "https://evil.example",
    "//evil.example",
    "javascript:alert(1)",
)

HTTP_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class Credentials:
    """Credentials read once from the environment. Values are never logged;
    only presence/absence is ever reported by callers."""

    vercel_token: str | None = field(default=None, repr=False)
    supabase_access_token: str | None = field(default=None, repr=False)
    render_api_key: str | None = field(default=None, repr=False)
    vercel_team_id: str | None = field(default=None, repr=False)
    render_service_id: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls) -> "Credentials":
        return cls(
            vercel_token=os.environ.get("VERCEL_TOKEN") or None,
            supabase_access_token=os.environ.get("SUPABASE_ACCESS_TOKEN") or None,
            render_api_key=os.environ.get("RENDER_API_KEY") or None,
            vercel_team_id=os.environ.get("VERCEL_TEAM_ID") or None,
            render_service_id=os.environ.get("RENDER_SERVICE_ID") or None,
        )

    def secret_values(self) -> list[str]:
        """Every raw secret value currently loaded, for redaction. Never
        printed -- only used to scrub accidental leaks out of error text."""
        return [v for v in (self.vercel_token, self.supabase_access_token, self.render_api_key) if v]
