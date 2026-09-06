"""Supabase Auth configuration check via the read-only Management API
config endpoint (GET /v1/projects/{ref}/config/auth). No PUT/PATCH is ever
issued -- this module only reads and compares.
"""
from __future__ import annotations

import fnmatch

import httpx

from .. import config
from ..models import CheckResult, Status

_BASE = "https://api.supabase.com/v1"

_LEGACY_TEMPLATE_MARKER = "{{ .ConfirmationURL }}"
_EXPECTED_TEMPLATE_MARKERS = ("token_hash={{ .TokenHash }}", "/auth/confirm")


def _get_auth_config(token: str) -> tuple[dict | None, str | None]:
    try:
        resp = httpx.get(
            f"{_BASE}/projects/{config.PRODUCTION_SUPABASE_PROJECT_REF}/config/auth",
            headers={"Authorization": f"Bearer {token}"},
            timeout=config.HTTP_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        return None, str(exc)
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}"
    return resp.json(), None


def _redirect_allowed(url: str, allow_list) -> bool:
    if isinstance(allow_list, str):
        patterns = [p.strip() for p in allow_list.split(",") if p.strip()]
    else:
        patterns = list(allow_list or [])
    for pattern in patterns:
        glob_pattern = pattern.replace("**", "*")
        if url == pattern or fnmatch.fnmatch(url, glob_pattern):
            return True
    return False


def check_auth_config(token: str | None) -> CheckResult:
    name = "Auth configuration"
    if not token:
        return CheckResult(
            name=name,
            status=Status.UNKNOWN,
            summary="SUPABASE_ACCESS_TOKEN not set",
            remediation="Set SUPABASE_ACCESS_TOKEN (with project auth-config read scope) as an environment variable.",
        )

    auth_cfg, err = _get_auth_config(token)
    if auth_cfg is None:
        return CheckResult(name=name, status=Status.UNKNOWN, summary=f"Could not read Supabase auth config: {err}",
                            remediation="Verify SUPABASE_ACCESS_TOKEN has permission to read this project's auth configuration.")

    details: list[str] = []
    fail_reasons: list[str] = []

    site_url = auth_cfg.get("site_url", "")
    details.append(f"site_url={site_url}")
    if site_url.rstrip("/") != config.EXPECTED_FRONTEND_URL.rstrip("/"):
        fail_reasons.append(f"site_url {site_url!r} != expected {config.EXPECTED_FRONTEND_URL!r}")

    allow_list = auth_cfg.get("uri_allow_list", "")
    details.append(f"uri_allow_list={allow_list}")
    if not _redirect_allowed(config.EXPECTED_AUTH_CALLBACK_URL, allow_list):
        fail_reasons.append(f"{config.EXPECTED_AUTH_CALLBACK_URL} is not covered by uri_allow_list")

    confirm_template = auth_cfg.get("mailer_templates_confirmation_content", "") or ""
    if _LEGACY_TEMPLATE_MARKER in confirm_template:
        fail_reasons.append("confirm-signup template still uses the legacy {{ .ConfirmationURL }} pattern, incompatible with the PKCE/SSR /auth/confirm flow")
    elif not confirm_template:
        fail_reasons.append("confirm-signup template is empty/default -- cannot verify it uses the token-hash flow")
    elif not all(marker in confirm_template for marker in _EXPECTED_TEMPLATE_MARKERS):
        fail_reasons.append("confirm-signup template does not contain the expected token_hash + /auth/confirm pattern")
    else:
        details.append("confirm-signup template uses the token-hash /auth/confirm flow")

    google_enabled = auth_cfg.get("external_google_enabled", False)
    azure_enabled = auth_cfg.get("external_azure_enabled", False)
    details.append(f"OAuth (informational, not a blocker): google={google_enabled} microsoft={azure_enabled}")

    if fail_reasons:
        return CheckResult(name=name, status=Status.FAIL, summary="; ".join(fail_reasons), details=details,
                            remediation="Update Supabase Auth settings (Site URL / Redirect URLs / confirm-signup email template) to match the deployed PKCE/SSR flow.")
    return CheckResult(name=name, status=Status.PASS, summary="Site URL, callback allow-list, and confirm-signup template match the deployed auth flow", details=details)


def check_smtp(token: str | None) -> CheckResult:
    name = "SMTP"
    if not token:
        return CheckResult(name=name, status=Status.UNKNOWN, summary="SUPABASE_ACCESS_TOKEN not set",
                            remediation="Set SUPABASE_ACCESS_TOKEN as an environment variable.")

    auth_cfg, err = _get_auth_config(token)
    if auth_cfg is None:
        return CheckResult(name=name, status=Status.UNKNOWN, summary=f"Could not read Supabase auth config: {err}")

    smtp_host = auth_cfg.get("smtp_host", "")
    smtp_sender_name = auth_cfg.get("smtp_sender_name", "")
    configured = bool(smtp_host)
    details = [f"smtp configured={configured}", f"sender_name_set={bool(smtp_sender_name)}"]

    if not configured:
        return CheckResult(name=name, status=Status.FAIL, summary="Custom SMTP is not configured (Supabase's built-in mailer has strict rate limits)",
                            details=details, remediation="Configure a custom SMTP provider in Supabase Auth settings.")
    return CheckResult(name=name, status=Status.PASS, summary="Custom SMTP is configured", details=details)
