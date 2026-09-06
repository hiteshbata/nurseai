"""Pure read-only HTTP checks: GET/HEAD only, no mutation, no auth needed.

Covers: backend /health, frontend route existence (institution area, join,
auth/confirm), and production bundle isolation (the deployed frontend must
not ship the QA Supabase URL).
"""
from __future__ import annotations

import re

import httpx

from .. import config
from ..models import CheckResult, Status

_BUNDLE_CHUNK_LIMIT = 12
_BUNDLE_BYTES_LIMIT = 3_000_000


def _get(client: httpx.Client, url: str, **kw) -> httpx.Response | None:
    try:
        return client.get(url, **kw)
    except httpx.HTTPError:
        return None


def check_backend_health() -> CheckResult:
    url = f"{config.EXPECTED_BACKEND_URL}/health"
    try:
        with httpx.Client(timeout=config.HTTP_TIMEOUT_SECONDS) as client:
            resp = client.get(url)
    except httpx.HTTPError as exc:
        return CheckResult(
            name="Backend health",
            status=Status.UNKNOWN,
            summary=f"Could not reach {url}",
            details=[str(exc)],
            remediation="Verify EXPECTED_BACKEND_URL is reachable from this machine/CI runner.",
        )

    if resp.status_code != 200:
        return CheckResult(
            name="Backend health",
            status=Status.FAIL,
            summary=f"{url} returned HTTP {resp.status_code}",
            details=[resp.text[:500]],
        )

    try:
        body = resp.json()
    except ValueError:
        return CheckResult(name="Backend health", status=Status.FAIL, summary="Health response was not JSON", details=[resp.text[:500]])

    status_field = body.get("status")
    if status_field != "ok":
        return CheckResult(
            name="Backend health",
            status=Status.FAIL,
            summary=f"Backend reports status={status_field!r}",
            details=[str(body)],
        )

    return CheckResult(name="Backend health", status=Status.PASS, summary="Backend /health reports ok", details=[str(body)])


def check_frontend_routes() -> CheckResult:
    details: list[str] = []
    fail_reasons: list[str] = []

    with httpx.Client(timeout=config.HTTP_TIMEOUT_SECONDS, follow_redirects=False) as client:
        for path in config.FRONTEND_ROUTES_MUST_NOT_404:
            url = f"{config.EXPECTED_FRONTEND_URL}{path}"
            resp = _get(client, url)
            if resp is None:
                fail_reasons.append(f"{path}: unreachable")
                continue
            details.append(f"{path} -> {resp.status_code}")
            if resp.status_code == 404:
                fail_reasons.append(f"{path} returned 404 (should be protected, not missing)")

        join_url = f"{config.EXPECTED_FRONTEND_URL}/join/nonexistent-token"
        resp = _get(client, join_url)
        if resp is None:
            fail_reasons.append("/join/nonexistent-token: unreachable")
        else:
            details.append(f"/join/nonexistent-token -> {resp.status_code}")
            if resp.status_code == 404 or resp.status_code >= 500:
                fail_reasons.append(f"/join/nonexistent-token returned {resp.status_code} (expected an invalid-invitation page)")

        confirm_url = f"{config.EXPECTED_FRONTEND_URL}/auth/confirm"
        resp = _get(client, confirm_url)
        if resp is None:
            fail_reasons.append("/auth/confirm: unreachable")
        else:
            details.append(f"/auth/confirm (no token) -> {resp.status_code}")
            if resp.status_code >= 500 or resp.status_code == 404:
                fail_reasons.append(f"/auth/confirm returned {resp.status_code} on a missing/invalid token (should redirect safely)")

    if fail_reasons:
        return CheckResult(
            name="HTTP routes",
            status=Status.FAIL,
            summary="; ".join(fail_reasons),
            details=details,
            remediation="Check the frontend deployment routing for the institution/join/auth-confirm pages.",
        )
    return CheckResult(name="HTTP routes", status=Status.PASS, summary="All expected routes reachable and not 404/500", details=details)


def check_bundle_isolation() -> CheckResult:
    try:
        with httpx.Client(timeout=config.HTTP_TIMEOUT_SECONDS, follow_redirects=True) as client:
            home = client.get(config.EXPECTED_FRONTEND_URL)
            if home.status_code != 200:
                return CheckResult(
                    name="Bundle isolation",
                    status=Status.UNKNOWN,
                    summary=f"Could not load {config.EXPECTED_FRONTEND_URL} (HTTP {home.status_code})",
                )
            html = home.text
            chunk_urls = sorted(set(re.findall(r'(/_next/static/[^"\'\s]+\.js)', html)))[:_BUNDLE_CHUNK_LIMIT]

            combined = html
            total_bytes = len(html.encode("utf-8"))
            for chunk in chunk_urls:
                if total_bytes >= _BUNDLE_BYTES_LIMIT:
                    break
                resp = _get(client, f"{config.EXPECTED_FRONTEND_URL}{chunk}")
                if resp is None or resp.status_code != 200:
                    continue
                combined += resp.text
                total_bytes += len(resp.text.encode("utf-8"))
    except httpx.HTTPError as exc:
        return CheckResult(
            name="Bundle isolation",
            status=Status.UNKNOWN,
            summary="Could not fetch production frontend bundle",
            details=[str(exc)],
        )

    has_qa_ref = config.QA_SUPABASE_PROJECT_REF in combined
    has_prod_ref = config.PRODUCTION_SUPABASE_PROJECT_REF in combined

    if has_qa_ref:
        return CheckResult(
            name="Bundle isolation",
            status=Status.FAIL,
            summary="Production frontend bundle references the QA Supabase project ref",
            details=[f"scanned {len(chunk_urls)} chunk(s), {total_bytes} bytes"],
            remediation="Rebuild/redeploy production with NEXT_PUBLIC_SUPABASE_URL pointed at the production project.",
        )

    if not has_prod_ref:
        return CheckResult(
            name="Bundle isolation",
            status=Status.UNKNOWN,
            summary="Could not confirm the production Supabase ref appears in the deployed bundle (may be behind more chunks than scanned)",
            details=[f"scanned {len(chunk_urls)} chunk(s), {total_bytes} bytes"],
            remediation="Increase chunk scan coverage or verify manually via browser devtools network tab.",
        )

    return CheckResult(
        name="Bundle isolation",
        status=Status.PASS,
        summary="Production bundle references the production Supabase project and not QA",
        details=[f"scanned {len(chunk_urls)} chunk(s), {total_bytes} bytes"],
    )
