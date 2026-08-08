"""
RBAC tier tests for backend/app/routers/admin.py (ROLE_RANK, require_role,
_target_is_staff, and the role-escalation guard in admin_set_user_role).

Same style as test_admin_cron_auth.py: dependency/route functions called
directly with a mocked get_supabase, no live DB, no FastAPI TestClient.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402
from app.routers import admin as admin_module  # noqa: E402
from app.routers.auth import UserInfo  # noqa: E402


def _fake_supabase(role: str | None):
    """A get_supabase() stand-in whose .table("user_roles").select(...)
    .eq(...).execute() returns a single row for `role`, or no rows if
    `role` is None (mirrors a user with no user_roles row -- defaults to
    'user' everywhere this codebase reads it)."""
    supabase = MagicMock()
    result = MagicMock()
    result.data = [{"role": role}] if role is not None else []
    supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = result
    return supabase


class RequireRoleTests(unittest.TestCase):
    def _call(self, dep, role: str):
        user = UserInfo(id="u1", email="u1@example.com", name="U1")
        with patch.object(admin_module, "get_supabase", return_value=_fake_supabase(role)):
            return dep(current_user=user)

    def test_exact_tier_passes(self):
        self.assertEqual(self._call(admin_module.require_support, "support").id, "u1")

    def test_higher_tier_passes_lower_floor(self):
        self.assertEqual(self._call(admin_module.require_support, "owner").id, "u1")

    def test_lower_tier_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            self._call(admin_module.require_admin, "support")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_plain_user_rejected_at_every_staff_floor(self):
        for dep in (admin_module.require_support, admin_module.require_analyst,
                    admin_module.require_admin, admin_module.require_owner):
            with self.assertRaises(HTTPException):
                self._call(dep, "user")

    def test_missing_role_row_defaults_to_user_and_is_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            self._call(admin_module.require_support, None)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_owner_satisfies_every_floor(self):
        for dep in (admin_module.require_support, admin_module.require_analyst,
                    admin_module.require_admin, admin_module.require_owner):
            self.assertEqual(self._call(dep, "owner").id, "u1")

    def test_admin_rejected_at_owner_floor(self):
        """RC3.4: role assignment (POST /admin/users/role) sits behind
        require_owner -- an admin must not clear this floor."""
        with self.assertRaises(HTTPException) as ctx:
            self._call(admin_module.require_owner, "admin")
        self.assertEqual(ctx.exception.status_code, 403)


class TargetIsStaffTests(unittest.TestCase):
    def test_support_and_up_is_staff(self):
        for role in ("support", "analyst", "admin", "owner"):
            self.assertTrue(admin_module._target_is_staff(_fake_supabase(role), "target"))

    def test_plain_user_is_not_staff(self):
        self.assertFalse(admin_module._target_is_staff(_fake_supabase("user"), "target"))

    def test_missing_role_row_is_not_staff(self):
        self.assertFalse(admin_module._target_is_staff(_fake_supabase(None), "target"))


class RoleEscalationGuardTests(unittest.TestCase):
    """admin_set_user_role: RC3.4 moved the escalation guard from an
    in-body rank comparison to the route's Depends(require_owner) floor
    (see RequireRoleTests.test_admin_rejected_at_owner_floor) -- only an
    owner ever reaches this function in production. What's left to check
    at the body level is role validation and the last-owner guard; see
    test_staff_roles.py for the fuller last-owner/audit-detail coverage."""

    def _grant(self, caller_role: str, target_role: str):
        supabase = _fake_supabase(caller_role)
        caller = UserInfo(id="caller", email="caller@example.com", name="Caller")
        req = admin_module.SetRoleRequest(user_id="target-id", role=target_role)
        with patch.object(admin_module, "get_supabase", return_value=supabase), \
             patch.object(admin_module, "_write_audit_log"):
            return admin_module.admin_set_user_role(req=req, current_user=caller)

    def test_owner_can_grant_owner(self):
        result = self._grant("owner", "owner")
        self.assertEqual(result, {"success": True})

    def test_unknown_role_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            self._grant("owner", "superadmin")
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
