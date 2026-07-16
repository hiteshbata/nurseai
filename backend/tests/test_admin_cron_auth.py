"""
require_admin_or_cron() auth-gate tests for the maintenance endpoints
(/admin/logs/prune, /admin/subscriptions/sweep-expired) that external cron
services (cron-job.org, Render Cron Job) call without a human admin JWT.

Run with:
    python -m unittest backend/tests/test_admin_cron_auth.py -v
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402
from app.routers import admin as admin_module  # noqa: E402
from app.core.config import settings  # noqa: E402


class RequireAdminOrCronTests(unittest.TestCase):
    def setUp(self):
        self._original_secret = settings.CRON_SECRET
        settings.CRON_SECRET = "test-cron-secret"

    def tearDown(self):
        settings.CRON_SECRET = self._original_secret

    def test_correct_cron_secret_passes_without_jwt(self):
        result = admin_module.require_admin_or_cron(
            x_cron_secret="test-cron-secret", authorization=None
        )
        self.assertIsNone(result)

    def test_wrong_cron_secret_falls_through_to_jwt_and_fails(self):
        with self.assertRaises(HTTPException) as ctx:
            admin_module.require_admin_or_cron(
                x_cron_secret="wrong-secret", authorization=None
            )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_no_secret_no_auth_header_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            admin_module.require_admin_or_cron(x_cron_secret=None, authorization=None)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_unset_cron_secret_ignores_header_falls_back_to_jwt(self):
        settings.CRON_SECRET = ""
        with self.assertRaises(HTTPException) as ctx:
            admin_module.require_admin_or_cron(
                x_cron_secret="anything", authorization=None
            )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_bearer_token_path_delegates_to_admin_check(self):
        with patch.object(
            admin_module, "get_current_user", return_value="fake-user"
        ) as mock_get_user, patch.object(
            admin_module, "require_admin", return_value="admin-ok"
        ) as mock_require_admin:
            result = admin_module.require_admin_or_cron(
                x_cron_secret=None, authorization="Bearer some.jwt.token"
            )
        mock_get_user.assert_called_once()
        mock_require_admin.assert_called_once_with("fake-user")
        self.assertEqual(result, "admin-ok")


if __name__ == "__main__":
    unittest.main()
