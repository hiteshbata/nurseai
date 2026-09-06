from pathlib import Path

from scripts.production_readiness.checks import git
from scripts.production_readiness.models import Status

_HEAD = "2606cfd8e41e2000bcc320e83feb9c53a467c46b"


def _patch_run(monkeypatch, branch=" main", head=_HEAD, origin_main=_HEAD, porcelain=""):
    def fake_run(repo_root, *args):
        if args[:2] == ("rev-parse", "--abbrev-ref"):
            return 0, branch.strip()
        if args == ("rev-parse", "HEAD"):
            return 0, head
        if args == ("rev-parse", "origin/main"):
            return 0, origin_main
        if args == ("status", "--porcelain"):
            return 0, porcelain
        raise AssertionError(f"unexpected git args: {args}")

    monkeypatch.setattr(git, "_run", fake_run)
    monkeypatch.setattr(git, "_tracked_at_head", lambda repo_root, path: True)


def test_clean_head_matching_commit_passes(monkeypatch):
    _patch_run(monkeypatch)
    result = git.check_git(Path("."))
    assert result.status == Status.PASS


def test_dirty_working_tree_fails(monkeypatch):
    _patch_run(monkeypatch, porcelain=" M some/file.py")
    result = git.check_git(Path("."))
    assert result.status == Status.FAIL
    assert "dirty" in result.summary


def test_commit_mismatch_fails(monkeypatch):
    other_sha = "1111111111111111111111111111111111111"
    _patch_run(monkeypatch, head=other_sha, origin_main=other_sha)
    result = git.check_git(Path("."))
    assert result.status == Status.FAIL
    assert "does not match expected production commit" in result.summary


def test_wrong_branch_fails_with_wrong_checkout_reason(monkeypatch):
    _patch_run(monkeypatch, branch="qa")
    result = git.check_git(Path("."))
    assert result.status == Status.FAIL
    assert "WRONG CHECKOUT" in result.summary
    assert "Current branch: qa" in result.details
    assert "Expected branch: main" in result.details


def test_missing_institution_feature_fails(monkeypatch):
    _patch_run(monkeypatch)
    monkeypatch.setattr(git, "_tracked_at_head", lambda repo_root, path: False)
    result = git.check_git(Path("."))
    assert result.status == Status.FAIL
    assert "institution feature files missing" in result.summary


def test_dirty_tree_from_audit_tool_only_is_labeled_artifact_not_wrong_checkout(monkeypatch):
    """The audit tool lives inside the repo it audits and is itself never
    committed. If it's the only reason the tree is dirty (correct branch,
    correct HEAD), that must not be reported as production branch drift."""
    _patch_run(
        monkeypatch,
        porcelain="?? scripts/__init__.py\n?? scripts/production-readiness-audit.py\n?? scripts/production_readiness/\n",
    )
    result = git.check_git(Path("."))
    assert result.status == Status.FAIL
    assert "AUDIT TOOL ARTIFACT" in result.summary
    assert "WRONG CHECKOUT" not in result.summary
    assert any("AUDIT TOOL ARTIFACT" in d for d in result.details)


def test_dirty_tree_mixing_audit_tool_and_real_changes_is_wrong_checkout(monkeypatch):
    """A real, non-audit-tool modification alongside the audit tool's own
    files must still surface as WRONG CHECKOUT -- the artifact carve-out
    only applies when audit-tool paths are the *sole* cause of dirt."""
    _patch_run(
        monkeypatch,
        porcelain="?? scripts/production_readiness/\n M backend/app/main.py\n",
    )
    result = git.check_git(Path("."))
    assert result.status == Status.FAIL
    assert "WRONG CHECKOUT" in result.summary
