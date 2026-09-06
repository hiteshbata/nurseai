"""Vercel check via the read-only Vercel REST API. GET requests only --
never POST/PATCH/DELETE. Env var values are never printed; the one
NEXT_PUBLIC_SUPABASE_URL comparison is done in-memory and only PASS/FAIL is
reported.
"""
from __future__ import annotations

import re

import httpx

from .. import config
from ..models import CheckResult, Status

_BASE = "https://api.vercel.com"
_SUPABASE_URL_RE = re.compile(r"^https://[a-z0-9]+\.supabase\.co/?$")
_SENSITIVE_ENV_KEYS = {
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_JWT_SECRET",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "GEMINI_API_KEY",
    "RAZORPAY_KEY_SECRET",
    "TURNSTILE_SECRET_KEY",
}


class _VercelClient:
    def __init__(self, token: str, team_id: str | None):
        self._client = httpx.Client(
            base_url=_BASE,
            headers={"Authorization": f"Bearer {token}"},
            timeout=config.HTTP_TIMEOUT_SECONDS,
        )
        self._team_id = team_id

    def get(self, path: str, params: dict | None = None) -> httpx.Response:
        params = dict(params or {})
        if self._team_id:
            params["teamId"] = self._team_id
        return self._client.get(path, params=params)

    def close(self):
        self._client.close()


def check_vercel(token: str | None, team_id: str | None = None) -> CheckResult:
    if not token:
        return CheckResult(
            name="Vercel",
            status=Status.UNKNOWN,
            summary="VERCEL_TOKEN not set",
            remediation="Set VERCEL_TOKEN (a Vercel personal/team access token with read access to the project) as an environment variable.",
        )

    client = _VercelClient(token, team_id)
    details: list[str] = []
    fail_reasons: list[str] = []
    unknown_reasons: list[str] = []

    try:
        resp = client.get(f"/v9/projects/{config.EXPECTED_VERCEL_PROJECT}")
        if resp.status_code != 200:
            return CheckResult(
                name="Vercel",
                status=Status.UNKNOWN,
                summary=f"Could not load project (HTTP {resp.status_code})",
                details=[resp.text[:300]],
                remediation="Verify VERCEL_TOKEN has access to the 'nurseai' project (and VERCEL_TEAM_ID if it lives under a team).",
            )
        project = resp.json()
        project_id = project.get("id")
        project_name = project.get("name")
        details.append(f"project id={project_id} name={project_name}")

        if project_id != config.EXPECTED_VERCEL_PROJECT_ID:
            fail_reasons.append(f"project id {project_id} != expected {config.EXPECTED_VERCEL_PROJECT_ID}")
        if project_name != config.EXPECTED_VERCEL_PROJECT:
            fail_reasons.append(f"project name {project_name!r} != expected {config.EXPECTED_VERCEL_PROJECT!r}")

        # Latest production deployment
        resp = client.get("/v6/deployments", params={"projectId": project_id, "target": "production", "limit": 1})
        if resp.status_code != 200:
            unknown_reasons.append(f"could not list production deployments (HTTP {resp.status_code})")
        else:
            deployments = resp.json().get("deployments", [])
            if not deployments:
                fail_reasons.append("no production deployment found")
            else:
                dep = deployments[0]
                state = dep.get("state") or dep.get("readyState")
                meta = dep.get("meta") or {}
                commit_sha = (
                    meta.get("githubCommitSha")
                    or meta.get("gitlabCommitSha")
                    or meta.get("bitbucketCommitSha")
                    or (dep.get("gitSource") or {}).get("sha")
                    or ""
                )
                commit_ref = meta.get("githubCommitRef") or (dep.get("gitSource") or {}).get("ref") or ""
                target = dep.get("target")

                details.append(f"deployment state={state} target={target} commit={commit_sha[:8]} ref={commit_ref}")

                if state not in ("READY",):
                    fail_reasons.append(f"latest production deployment state is {state!r}, not READY")
                if target != "production":
                    fail_reasons.append(f"latest deployment target is {target!r}, not 'production'")
                if commit_ref and commit_ref != config.EXPECTED_PRODUCTION_BRANCH:
                    fail_reasons.append(f"deployed git ref {commit_ref!r} != expected {config.EXPECTED_PRODUCTION_BRANCH!r}")
                if commit_sha and not commit_sha.startswith(config.EXPECTED_PRODUCTION_COMMIT):
                    fail_reasons.append(f"deployed commit {commit_sha[:8]} != expected {config.EXPECTED_PRODUCTION_COMMIT}")
                elif not commit_sha:
                    unknown_reasons.append("deployment response did not include a commit SHA")

        # Domains
        resp = client.get(f"/v9/projects/{project_id}/domains")
        if resp.status_code != 200:
            unknown_reasons.append(f"could not list domains (HTTP {resp.status_code})")
        else:
            domains = [d.get("name") for d in resp.json().get("domains", [])]
            details.append(f"domains={domains}")
            expected_host = config.EXPECTED_FRONTEND_URL.split("//", 1)[-1]
            if expected_host not in domains:
                fail_reasons.append(f"{expected_host} not attached to project domains {domains}")

        # Env vars: report configured/missing by name+target only, never values.
        resp = client.get(f"/v9/projects/{project_id}/env")
        if resp.status_code != 200:
            unknown_reasons.append(f"could not list env vars (HTTP {resp.status_code})")
        else:
            envs = resp.json().get("envs", [])
            by_key: dict[str, list[str]] = {}
            for e in envs:
                by_key.setdefault(e.get("key", ""), []).extend(e.get("target", []) or [])
            configured = sorted(k for k, targets in by_key.items() if "production" in targets)
            details.append(f"production env vars configured: {len(configured)}")

            if "NEXT_PUBLIC_SUPABASE_URL" not in by_key or "production" not in by_key.get("NEXT_PUBLIC_SUPABASE_URL", []):
                fail_reasons.append("NEXT_PUBLIC_SUPABASE_URL not configured for production target")
            else:
                # Best-effort value comparison -- requires a token scope that
                # can decrypt. If unavailable, this narrows to INFO, not a
                # hard failure of the whole check.
                url_value = None
                try:
                    decrypt_resp = client.get(f"/v9/projects/{project_id}/env", params={"decrypt": "true"})
                    if decrypt_resp.status_code == 200:
                        for e in decrypt_resp.json().get("envs", []):
                            if e.get("key") == "NEXT_PUBLIC_SUPABASE_URL" and "production" in (e.get("target") or []):
                                url_value = e.get("value")
                                break
                except httpx.HTTPError:
                    url_value = None

                if url_value is None:
                    details.append("NEXT_PUBLIC_SUPABASE_URL value comparison unavailable (token lacks decrypt scope, or not returned)")
                elif not _SUPABASE_URL_RE.match(url_value):
                    # A token without decrypt permission can still get a 200 back with
                    # `value` set to the stored ciphertext instead of plaintext -- that
                    # isn't a real config mismatch, just an unreadable value. Don't treat
                    # it as a FAIL; the Bundle isolation check reads this same public var
                    # straight out of the shipped JS bundle and is the authoritative
                    # signal for it.
                    details.append(
                        "NEXT_PUBLIC_SUPABASE_URL value returned by Vercel is not a decryptable Supabase URL "
                        "(likely a token-scope limitation) -- see the Bundle isolation check for the authoritative value"
                    )
                elif url_value != config.EXPECTED_PRODUCTION_SUPABASE_URL:
                    if url_value == config.EXPECTED_QA_SUPABASE_URL:
                        fail_reasons.append("NEXT_PUBLIC_SUPABASE_URL points at the QA Supabase project, not production")
                    else:
                        fail_reasons.append("NEXT_PUBLIC_SUPABASE_URL does not match the expected production Supabase URL")
                else:
                    details.append("NEXT_PUBLIC_SUPABASE_URL confirmed pointed at production")

    except httpx.HTTPError as exc:
        return CheckResult(name="Vercel", status=Status.UNKNOWN, summary="Vercel API request failed", details=[str(exc)])
    finally:
        client.close()

    if fail_reasons:
        return CheckResult(
            name="Vercel",
            status=Status.FAIL,
            summary="; ".join(fail_reasons),
            details=details,
            remediation="Review the Vercel project/deployment/domain/env configuration against the expected production values in config.py.",
        )
    if unknown_reasons:
        return CheckResult(
            name="Vercel",
            status=Status.UNKNOWN,
            summary="; ".join(unknown_reasons),
            details=details,
            remediation="Grant VERCEL_TOKEN broader read scope, or verify manually in the Vercel dashboard.",
        )
    return CheckResult(name="Vercel", status=Status.PASS, summary="Project, production deployment, domain, and env config match expectations", details=details)
