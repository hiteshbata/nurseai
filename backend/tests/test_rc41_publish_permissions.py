"""RC4.1 -- owner-only gating for the three version-cut/publish endpoints
(Reading/Listening "Make Live", Mock Test "Publish new version"). Decision:
these endpoints use require_owner, not require_admin -- see the RC4.1
publish-permission resolution. Same test style as test_rbac.py (direct
dependency calls against a role-mocked get_supabase, no live DB).

This file does NOT re-test the version-cut mechanics themselves (snapshot
building, freeze-on-publish, etc.) -- see test_reading_versioning.py,
test_listening_versioning.py, test_mock_versioning.py for that. It only
proves who is allowed to reach these endpoints, and that nothing else in
the RBAC hierarchy moved.
"""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import HTTPException, params as fastapi_params
from unittest.mock import MagicMock, patch

from app.routers import admin as admin_module
from app.routers import reading as reading_module
from app.routers import listening as listening_module
from app.routers import mock as mock_module
from app.routers.auth import UserInfo


def _fake_supabase(role: str | None):
    """Mirrors test_rbac.py's helper: a get_supabase() stand-in whose
    user_roles lookup returns `role` (or no rows -> defaults to 'user')."""
    supabase = MagicMock()
    result = MagicMock()
    result.data = [{"role": role}] if role is not None else []
    supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = result
    return supabase


def _dependency_of(fn, param_name: str):
    """The callable a route param's Depends(...) wraps, so we can prove it's
    literally admin_module.require_owner/require_admin -- not merely
    behaviorally similar."""
    default = inspect.signature(fn).parameters[param_name].default
    assert isinstance(default, fastapi_params.Depends)
    return default.dependency


def _call_dependency(dep, role: str):
    user = UserInfo(id="u1", email="u1@example.com", name="U1")
    with patch.object(admin_module, "get_supabase", return_value=_fake_supabase(role)):
        return dep(current_user=user)


class PublishEndpointsAreOwnerGated:
    """Mixin: `endpoint` + `param_name` identify the route; subclasses supply
    them. Not run directly (no test_ prefix on the class)."""
    endpoint = None
    param_name = "admin"

    def test_dependency_is_require_owner_not_require_admin(self):
        dep = _dependency_of(self.endpoint, self.param_name)
        assert dep is admin_module.require_owner
        assert dep is not admin_module.require_admin

    def test_owner_passes(self):
        assert _call_dependency(admin_module.require_owner, "owner").id == "u1"

    def test_admin_rejected(self):
        with pytest.raises(HTTPException) as ctx:
            _call_dependency(admin_module.require_owner, "admin")
        assert ctx.value.status_code == 403

    def test_analyst_rejected(self):
        with pytest.raises(HTTPException) as ctx:
            _call_dependency(admin_module.require_owner, "analyst")
        assert ctx.value.status_code == 403


class TestReadingPublishIsOwnerGated(PublishEndpointsAreOwnerGated):
    endpoint = reading_module.set_test_active


class TestListeningPublishIsOwnerGated(PublishEndpointsAreOwnerGated):
    endpoint = listening_module.set_test_active


class TestMockPublishIsOwnerGated(PublishEndpointsAreOwnerGated):
    endpoint = mock_module.admin_publish_mock_test_version
    param_name = "current_user"


class TestNormalAdminOpsUnaffected:
    """RC4.1 changed exactly 3 endpoints. Everything else that was
    require_admin stays require_admin -- spot-check one route per router
    plus the RC4.1 backfill endpoint itself (a one-time rollout action, not
    a version-cut, so it intentionally stays admin-level)."""

    def test_reading_admin_list_tests_still_require_admin(self):
        assert _dependency_of(reading_module.admin_list_tests, "_admin") is admin_module.require_admin

    def test_listening_admin_list_tests_still_require_admin(self):
        assert _dependency_of(listening_module.admin_list_tests, "_admin") is admin_module.require_admin

    def test_mock_generate_still_require_admin(self):
        assert _dependency_of(mock_module.admin_generate_mock_test, "current_user") is admin_module.require_admin

    def test_mock_set_active_still_require_admin(self):
        assert _dependency_of(mock_module.admin_set_mock_test_active, "current_user") is admin_module.require_admin

    def test_backfill_versions_still_require_admin(self):
        assert _dependency_of(admin_module.admin_backfill_rc41_versions, "current_user") is admin_module.require_admin


class TestRoleHierarchyUntouched:
    """RC4.1 must not redefine roles or reorder the tier -- only reassign
    which floor 3 endpoints sit behind."""

    def test_role_rank_unchanged(self):
        assert admin_module.ROLE_RANK == {"user": 0, "support": 1, "analyst": 2, "admin": 3, "owner": 4}

    def test_require_owner_is_still_require_role_owner_floor(self):
        # Same construction as require_admin/require_support/require_analyst --
        # RC4.1 reused the existing dependency, it did not add a new one.
        with pytest.raises(HTTPException) as ctx:
            _call_dependency(admin_module.require_owner, "admin")
        assert "owner" in ctx.value.detail.lower()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
