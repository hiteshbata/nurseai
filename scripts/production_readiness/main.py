"""Orchestrator: runs every check, prints a report, and exits 0 (READY) or
1 (HOLD). Every check is wrapped so an unexpected exception becomes an
UNKNOWN result instead of crashing the whole audit or silently vanishing.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Callable

from . import config, verdict
from .checks import auth, git, http, redirect, render, supabase, vercel
from .models import CheckResult, Status, redact

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_safely(name: str, fn: Callable[[], CheckResult], secrets: list[str], debug: bool) -> CheckResult:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 -- a crashed check must degrade to UNKNOWN, never disappear
        tb = traceback.format_exc() if debug else ""
        message = redact(f"{type(exc).__name__}: {exc}", secrets)
        details = [redact(tb, secrets)] if debug else []
        return CheckResult(
            name=name,
            status=Status.UNKNOWN,
            summary=f"Check crashed: {message}",
            details=details,
            remediation="Re-run with --debug for a traceback, or investigate the check implementation.",
        )


def run_all(creds: config.Credentials, debug: bool = False) -> list[CheckResult]:
    secrets = creds.secret_values()
    checks: list[tuple[str, Callable[[], CheckResult]]] = [
        ("Git", lambda: git.check_git(REPO_ROOT)),
        ("Vercel", lambda: vercel.check_vercel(creds.vercel_token, creds.vercel_team_id)),
        ("Render", lambda: render.check_render(creds.render_api_key, creds.render_service_id)),
        ("Supabase project", lambda: supabase.check_supabase_project(creds.supabase_access_token)),
        ("Institution schema", lambda: supabase.check_institution_schema(creds.supabase_access_token)),
        ("RPC security", lambda: supabase.check_rpc_security(creds.supabase_access_token)),
        ("Database state", lambda: supabase.check_database_state(creds.supabase_access_token)),
        ("Migration safety", lambda: supabase.check_migration_safety(creds.supabase_access_token, REPO_ROOT)),
        ("Backend health", lambda: http.check_backend_health()),
        ("HTTP routes", lambda: http.check_frontend_routes()),
        ("Bundle isolation", lambda: http.check_bundle_isolation()),
        ("Open redirect", lambda: redirect.check_open_redirect(REPO_ROOT)),
        ("Auth configuration", lambda: auth.check_auth_config(creds.supabase_access_token)),
        ("SMTP", lambda: auth.check_smtp(creds.supabase_access_token)),
    ]

    results: list[CheckResult] = []
    for name, fn in checks:
        result = _run_safely(name, fn, secrets, debug)
        result.summary = redact(result.summary, secrets)
        result.details = [redact(d, secrets) for d in result.details]
        if result.remediation:
            result.remediation = redact(result.remediation, secrets)
        results.append(result)
    return results


def _print_human(results: list[CheckResult], final: str) -> None:
    print("PRODUCTION READINESS")
    print("=" * 21)
    print()
    width = max(len(r.name) for r in results) + 4
    for r in results:
        note = "" if r.severity.value == "mandatory" else "  (optional)"
        print(f"{r.name.ljust(width)}{r.status.value}{note}")
        if r.status in (Status.FAIL, Status.UNKNOWN):
            print(f"{' ' * width}  -> {r.summary}")
            if r.remediation:
                print(f"{' ' * width}  fix: {r.remediation}")
    print()
    print(f"FINAL: {final}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="production-readiness-audit", description="Read-only production readiness audit.")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON instead of the human report")
    parser.add_argument("--debug", action="store_true", help="include exception details on crashed checks (secrets still redacted)")
    args = parser.parse_args(argv)

    creds = config.Credentials.from_env()
    results = run_all(creds, debug=args.debug)
    final, exit_code = verdict.compute_verdict(results)

    if args.json:
        payload = {
            "final": final,
            "exit_code": exit_code,
            "checks": [r.to_dict() for r in results],
        }
        print(json.dumps(payload, indent=2))
    else:
        _print_human(results, final)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
