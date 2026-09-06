"""Open-redirect check: exercises the REAL sanitizeNext() implementation
(frontend/src/lib/auth-redirect.ts) via Node's native TypeScript support,
rather than re-implementing the logic in Python and hoping it stays in sync.

No network calls, no writes -- just imports and calls a pure function.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .. import config
from ..models import CheckResult, Status

_MODULE_REL_PATH = "frontend/src/lib/auth-redirect.ts"

_NODE_SCRIPT = """
import {{ pathToFileURL }} from 'node:url';
import(pathToFileURL(process.argv[2]).href).then(async (m) => {{
  const origin = {origin!r};
  const cases = {cases};
  const out = [];
  for (const c of cases) {{
    out.push({{ input: c, result: m.sanitizeNext(c, origin) }});
  }}
  process.stdout.write(JSON.stringify(out));
}}).catch((e) => {{
  process.stderr.write(String(e && e.message || e));
  process.exit(1);
}});
"""


def check_open_redirect(repo_root: Path | None = None) -> CheckResult:
    repo_root = repo_root or Path.cwd()
    module_path = repo_root / _MODULE_REL_PATH

    if not module_path.exists():
        return CheckResult(
            name="Open redirect",
            status=Status.FAIL,
            summary=f"{_MODULE_REL_PATH} not found",
            remediation="The shared sanitizeNext() helper is missing; restore it before shipping the institution invite flow.",
        )

    node = shutil.which("node")
    if not node:
        return CheckResult(
            name="Open redirect",
            status=Status.UNKNOWN,
            summary="node executable not found on PATH",
            remediation="Install Node.js so this check can exercise the real sanitizeNext() implementation.",
        )

    malicious = list(config.MALICIOUS_REDIRECT_TARGETS)
    safe = [f"/join/{config.QA_SUPABASE_PROJECT_REF[:8]}-token"]
    cases = malicious + safe

    script = _NODE_SCRIPT.format(origin=config.EXPECTED_FRONTEND_URL, cases=json.dumps(cases))
    script_path = repo_root / "scripts" / "production_readiness" / "_redirect_probe.mjs"
    script_path.write_text(script, encoding="utf-8")

    try:
        proc = subprocess.run(
            [node, str(script_path), str(module_path)],
            cwd=str(repo_root / "frontend"),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(name="Open redirect", status=Status.UNKNOWN, summary="sanitizeNext() probe timed out")
    finally:
        script_path.unlink(missing_ok=True)

    if proc.returncode != 0:
        return CheckResult(
            name="Open redirect",
            status=Status.UNKNOWN,
            summary="Could not execute sanitizeNext() via Node",
            details=[proc.stderr.strip()[:500]],
        )

    try:
        results = json.loads(proc.stdout)
    except ValueError:
        return CheckResult(name="Open redirect", status=Status.UNKNOWN, summary="Unparseable probe output", details=[proc.stdout[:500]])

    details = [f"{r['input']!r} -> {r['result']!r}" for r in results]
    leaked = [r for r in results if r["input"] in malicious and r["result"] is not None]
    safe_rejected = [r for r in results if r["input"] not in malicious and r["result"] is None]

    if leaked:
        return CheckResult(
            name="Open redirect",
            status=Status.FAIL,
            summary=f"sanitizeNext() accepted malicious redirect target(s): {[r['input'] for r in leaked]}",
            details=details,
            remediation="Tighten sanitizeNext() in frontend/src/lib/auth-redirect.ts to reject these inputs.",
        )
    if safe_rejected:
        return CheckResult(
            name="Open redirect",
            status=Status.FAIL,
            summary=f"sanitizeNext() rejected a legitimate same-origin path: {[r['input'] for r in safe_rejected]}",
            details=details,
            remediation="sanitizeNext() is over-restrictive; legitimate /join/<token> returnTo values are being dropped.",
        )

    return CheckResult(
        name="Open redirect",
        status=Status.PASS,
        summary="sanitizeNext() rejects evil.example, //evil.example, and javascript: while accepting same-origin paths",
        details=details,
    )
