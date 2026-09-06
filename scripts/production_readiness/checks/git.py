"""Local git state check. Read-only: `git status`, `git rev-parse`,
`git ls-tree` / `git cat-file -e` only -- never a write, fetch, or checkout.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .. import config
from ..models import CheckResult, Status

INSTITUTION_ROUTER_PATHS = (
    "backend/app/routers/institution.py",
    "backend/app/routers/institutions.py",
)
INSTITUTION_FRONTEND_PATHS = (
    "frontend/app/institution/page.tsx",
    "frontend/app/join/[token]/page.tsx",
)

# This audit tool lives in the repo it audits, but is itself never committed
# (see README: it's run from an ad-hoc checkout). If it's the *only* reason
# the tree is dirty, that's not production branch drift -- it's the audit
# tool's own footprint. Distinguish the two so the report doesn't cry "wrong
# checkout" over the audit tool sitting in the working tree it's inspecting.
AUDIT_TOOL_PATH_PREFIXES = (
    "scripts/production_readiness/",
    "scripts/production-readiness-audit.py",
    "scripts/__init__.py",
)


def _dirty_paths(porcelain: str) -> list[str]:
    paths = []
    for line in porcelain.splitlines():
        if len(line) <= 3:
            continue
        path = line[3:].strip().strip('"')
        if " -> " in path:  # renames: "old -> new"
            path = path.split(" -> ", 1)[1]
        paths.append(path)
    return paths


def _is_audit_tool_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in AUDIT_TOOL_PATH_PREFIXES)


def _run(repo_root: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode, (proc.stdout or proc.stderr or "").strip()


def _tracked_at_head(repo_root: Path, path: str) -> bool:
    code, _ = _run(repo_root, "cat-file", "-e", f"HEAD:{path}")
    return code == 0


def check_git(repo_root: Path | None = None) -> CheckResult:
    repo_root = repo_root or Path.cwd()
    details: list[str] = []

    code, branch = _run(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    if code != 0:
        return CheckResult(
            name="Git",
            status=Status.UNKNOWN,
            summary="Not a git repository or git unavailable",
            details=[branch],
            remediation="Run from within the repository clone.",
        )

    _, head_sha = _run(repo_root, "rev-parse", "HEAD")
    _, origin_main_sha = _run(repo_root, "rev-parse", "origin/main")
    _, porcelain = _run(repo_root, "status", "--porcelain")
    tree_clean = porcelain == ""

    details.append(f"branch={branch}")
    details.append(f"HEAD={head_sha}")
    details.append(f"origin/main={origin_main_sha}")
    details.append(f"working_tree_clean={tree_clean}")

    fail_reasons: list[str] = []

    wrong_branch = branch.strip() != config.EXPECTED_PRODUCTION_BRANCH
    dirty_paths = _dirty_paths(porcelain)
    dirty_only_audit_tool = bool(dirty_paths) and all(_is_audit_tool_path(p) for p in dirty_paths)

    if not wrong_branch and dirty_only_audit_tool:
        # Tree is dirty, but every dirty path is the audit tool's own
        # uncommitted files -- not production branch drift. Still FAIL
        # (fail-closed: an uncommitted audit tool run isn't a clean-tree
        # audit), but label it so it isn't mistaken for real drift.
        details.append("GIT SOURCE = AUDIT TOOL ARTIFACT")
        details.append(f"Untracked/modified audit-tool file(s): {dirty_paths}")
        fail_reasons.append(
            "GIT SOURCE = AUDIT TOOL ARTIFACT: working tree is dirty only because of the "
            "uncommitted audit tool itself (" + ", ".join(dirty_paths) + "); production branch is clean"
        )
    elif wrong_branch or not tree_clean:
        # Distinct, hard-to-miss reason: this is the "you're auditing the
        # wrong checkout" case (e.g. running from a dirty QA clone on
        # branch `qa`), not an ordinary commit drift on production `main`.
        details.append("GIT SOURCE = WRONG CHECKOUT")
        details.append(f"Current branch: {branch}")
        details.append(f"Expected branch: {config.EXPECTED_PRODUCTION_BRANCH}")
        details.append(f"Current HEAD: {head_sha}")
        details.append(f"Expected HEAD: {config.EXPECTED_PRODUCTION_COMMIT}")
        bits = []
        if wrong_branch:
            bits.append(f"branch is '{branch}' (expected '{config.EXPECTED_PRODUCTION_BRANCH}')")
        if not tree_clean:
            bits.append("working tree is dirty")
        fail_reasons.append("GIT SOURCE = WRONG CHECKOUT: " + "; ".join(bits))

    if not head_sha.startswith(config.EXPECTED_PRODUCTION_COMMIT) and head_sha != origin_main_sha:
        fail_reasons.append(
            f"HEAD ({head_sha[:8]}) does not match expected production commit "
            f"({config.EXPECTED_PRODUCTION_COMMIT})"
        )

    if origin_main_sha and not origin_main_sha.startswith(config.EXPECTED_PRODUCTION_COMMIT):
        fail_reasons.append(
            f"origin/main ({origin_main_sha[:8]}) does not match expected production commit "
            f"({config.EXPECTED_PRODUCTION_COMMIT})"
        )

    if head_sha and origin_main_sha and head_sha != origin_main_sha:
        details.append("HEAD != origin/main (informational unless HEAD also fails the commit check above)")

    # Institution feature presence -- checked against the committed tree at
    # HEAD, not the working directory, so uncommitted/untracked scratch
    # files can't produce a false PASS.
    missing_features: list[str] = []
    for path in config.INSTITUTION_MIGRATIONS:
        full = f"supabase/migrations/{path}"
        if not _tracked_at_head(repo_root, full):
            missing_features.append(full)

    if not any(_tracked_at_head(repo_root, p) for p in INSTITUTION_ROUTER_PATHS):
        missing_features.append(" or ".join(INSTITUTION_ROUTER_PATHS))

    for path in INSTITUTION_FRONTEND_PATHS:
        if not _tracked_at_head(repo_root, path):
            missing_features.append(path)

    if missing_features:
        fail_reasons.append("institution feature files missing at HEAD: " + ", ".join(missing_features))
    else:
        details.append("institution feature present (migrations + router + frontend routes)")

    if fail_reasons:
        return CheckResult(
            name="Git",
            status=Status.FAIL,
            summary="; ".join(fail_reasons),
            details=details,
            remediation="Ensure the production checkout is a clean HEAD at origin/main matching the expected commit, with the institution feature committed.",
        )

    return CheckResult(
        name="Git",
        status=Status.PASS,
        summary=f"HEAD matches expected commit {config.EXPECTED_PRODUCTION_COMMIT}, tree clean, institution feature present",
        details=details,
    )
