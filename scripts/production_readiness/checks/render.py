"""Render check via the read-only Render REST API. GET requests only.

Render's env-vars endpoint returns raw values (unlike Vercel), so this
module is careful to read `value` only for internal comparison and never
put it in a summary/details/remediation string.
"""
from __future__ import annotations

import httpx

from .. import config
from ..models import CheckResult, Status

_BASE = "https://api.render.com/v1"
_DISCOVERY_SCAN_LIMIT = 20


class _RenderClient:
    def __init__(self, api_key: str):
        self._client = httpx.Client(
            base_url=_BASE,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            timeout=config.HTTP_TIMEOUT_SECONDS,
        )

    def get(self, path: str, params: dict | None = None) -> httpx.Response:
        return self._client.get(path, params=params or {})

    def close(self):
        self._client.close()


def _discover_service_id(client: _RenderClient) -> tuple[str | None, str | None]:
    """Find the service whose custom domain is the expected backend host.
    Returns (service_id, error_message)."""
    resp = client.get("/services", params={"limit": 100, "type": "web_service"})
    if resp.status_code != 200:
        return None, f"could not list services (HTTP {resp.status_code})"

    expected_host = config.EXPECTED_BACKEND_URL.split("//", 1)[-1]
    services = resp.json()
    for entry in services[:_DISCOVERY_SCAN_LIMIT]:
        svc = entry.get("service", entry)
        svc_id = svc.get("id")
        if not svc_id:
            continue
        domains_resp = client.get(f"/services/{svc_id}/custom-domains")
        if domains_resp.status_code != 200:
            continue
        names = [d.get("name") for d in domains_resp.json()]
        if expected_host in names:
            return svc_id, None

    return None, f"no service found with custom domain {expected_host} (scanned {min(len(services), _DISCOVERY_SCAN_LIMIT)} service(s))"


def check_render(api_key: str | None, service_id: str | None = None) -> CheckResult:
    if not api_key:
        return CheckResult(
            name="Render",
            status=Status.UNKNOWN,
            summary="RENDER_API_KEY not set",
            remediation="Set RENDER_API_KEY (a Render API key with read access to the backend service) as an environment variable.",
        )

    client = _RenderClient(api_key)
    details: list[str] = []
    fail_reasons: list[str] = []
    unknown_reasons: list[str] = []

    try:
        if not service_id:
            service_id, err = _discover_service_id(client)
            if err:
                unknown_reasons.append(err)

        if not service_id:
            return CheckResult(
                name="Render",
                status=Status.UNKNOWN,
                summary="; ".join(unknown_reasons) or "could not identify the Render service",
                remediation="Set RENDER_SERVICE_ID explicitly, or grant RENDER_API_KEY access to the backend service.",
            )

        resp = client.get(f"/services/{service_id}")
        if resp.status_code != 200:
            return CheckResult(name="Render", status=Status.UNKNOWN, summary=f"could not load service {service_id} (HTTP {resp.status_code})")
        service = resp.json()
        branch = service.get("branch")
        suspended = service.get("suspended")
        details.append(f"service id={service_id} name={service.get('name')} branch={branch} suspended={suspended}")

        if branch and branch != config.EXPECTED_PRODUCTION_BRANCH:
            fail_reasons.append(f"deploy branch {branch!r} != expected {config.EXPECTED_PRODUCTION_BRANCH!r}")
        if suspended and suspended != "not_suspended":
            fail_reasons.append(f"service is suspended ({suspended})")

        resp = client.get(f"/services/{service_id}/deploys", params={"limit": 1})
        if resp.status_code != 200:
            unknown_reasons.append(f"could not list deploys (HTTP {resp.status_code})")
        else:
            deploys = resp.json()
            if not deploys:
                fail_reasons.append("no deploys found")
            else:
                deploy = deploys[0].get("deploy", deploys[0])
                dep_status = deploy.get("status")
                commit = (deploy.get("commit") or {}).get("id", "")
                details.append(f"latest deploy status={dep_status} commit={commit[:8]}")

                if dep_status != "live":
                    fail_reasons.append(f"latest deploy status is {dep_status!r}, not 'live'")
                if commit and not commit.startswith(config.EXPECTED_PRODUCTION_COMMIT):
                    fail_reasons.append(f"deployed commit {commit[:8]} != expected {config.EXPECTED_PRODUCTION_COMMIT}")

        resp = client.get(f"/services/{service_id}/env-vars", params={"limit": 100})
        if resp.status_code != 200:
            unknown_reasons.append(f"could not list env vars (HTTP {resp.status_code})")
        else:
            raw = resp.json()
            values: dict[str, str] = {}
            for entry in raw:
                ev = entry.get("envVar", entry)
                key = ev.get("key")
                if key:
                    values[key] = ev.get("value", "")

            missing = [k for k in config.REQUIRED_RENDER_ENV_VARS if k not in values]
            details.append(f"env vars present: {sorted(k for k in config.REQUIRED_RENDER_ENV_VARS if k in values)}")
            if missing:
                fail_reasons.append(f"missing required env var(s): {missing}")

            if "ENVIRONMENT" in values and values["ENVIRONMENT"] != "production":
                fail_reasons.append("ENVIRONMENT env var is not 'production'")
            if "SUPABASE_URL" in values and config.PRODUCTION_SUPABASE_PROJECT_REF not in values["SUPABASE_URL"]:
                fail_reasons.append("SUPABASE_URL does not point at the production Supabase project")
            if "FRONTEND_URL" in values and values["FRONTEND_URL"].rstrip("/") != config.EXPECTED_FRONTEND_URL.rstrip("/"):
                fail_reasons.append("FRONTEND_URL does not match the expected production frontend URL")
            if "PRODUCTION_SUPABASE_PROJECT_REF" in values and values["PRODUCTION_SUPABASE_PROJECT_REF"] != config.PRODUCTION_SUPABASE_PROJECT_REF:
                fail_reasons.append("PRODUCTION_SUPABASE_PROJECT_REF env var does not match the expected production project ref")

    except httpx.HTTPError as exc:
        return CheckResult(name="Render", status=Status.UNKNOWN, summary="Render API request failed", details=[str(exc)])
    finally:
        client.close()

    if fail_reasons:
        return CheckResult(
            name="Render",
            status=Status.FAIL,
            summary="; ".join(fail_reasons),
            details=details,
            remediation="Review the Render service branch/deploy/env configuration against the expected production values.",
        )
    if unknown_reasons:
        return CheckResult(name="Render", status=Status.UNKNOWN, summary="; ".join(unknown_reasons), details=details)
    return CheckResult(name="Render", status=Status.PASS, summary="Service, latest deploy, and required env vars match expectations", details=details)
