"""
Email OTP verification: server-side enforcement in get_current_user.

Signup no longer grants normal application access until auth.users.
email_confirmed_at is set -- these tests exercise that gate directly against
the real get_current_user() logic, using the same fake-Supabase-client
pattern as test_auth_role_preservation.py.

Run with:
    python -m unittest backend/tests/test_email_confirmation_gate.py -v
"""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import jwt
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers import auth as auth_module  # noqa: E402
from app.core.config import settings  # noqa: E402

TEST_JWT_SECRET = "test-jwt-secret-at-least-32-bytes-long"


def make_token(user_id, email="nurse@example.com", is_anonymous=False):
    payload = {
        "sub": user_id,
        "aud": "authenticated",
        "user_metadata": {"name": "Test Nurse"},
        "exp": time.time() + 3600,
        "is_anonymous": is_anonymous,
    }
    if email is not None:
        payload["email"] = email
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, rows_by_id):
        self._rows = rows_by_id

    def upsert(self, row, on_conflict=None, ignore_duplicates=False):
        key = row.get("user_id") or row.get("id")
        if not (key in self._rows and ignore_duplicates):
            self._rows[key] = dict(row)
        return self

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def execute(self):
        return FakeResult(list(self._rows.values()))


class FakeAuthAdmin:
    def __init__(self, email_confirmed_at):
        self.email_confirmed_at = email_confirmed_at
        self.call_count = 0

    def get_user_by_id(self, _user_id):
        self.call_count += 1
        return MagicMock(user=MagicMock(email_confirmed_at=self.email_confirmed_at))


class FakeSupabase:
    def __init__(self, email_confirmed_at):
        self.auth = MagicMock(admin=FakeAuthAdmin(email_confirmed_at))

    def table(self, _name):
        return FakeTable({})


def run_get_current_user(fake_supabase, user_id, email="nurse@example.com", is_anonymous=False):
    credentials = MagicMock(credentials=make_token(user_id, email=email, is_anonymous=is_anonymous))
    original_get_supabase = auth_module.get_supabase
    original_secret = settings.SUPABASE_JWT_SECRET
    auth_module.get_supabase = lambda: fake_supabase
    settings.SUPABASE_JWT_SECRET = TEST_JWT_SECRET
    try:
        return auth_module.get_current_user(credentials)
    finally:
        auth_module.get_supabase = original_get_supabase
        settings.SUPABASE_JWT_SECRET = original_secret


class EmailConfirmationGateTests(unittest.TestCase):
    def setUp(self):
        auth_module._user_role_cache.clear()
        auth_module._email_confirmed_cache.clear()

    def test_confirmed_user_passes(self):
        fake = FakeSupabase(email_confirmed_at="2026-01-01T00:00:00Z")
        result = run_get_current_user(fake, "user-1")
        self.assertEqual(result.id, "user-1")

    def test_unconfirmed_non_anonymous_user_blocked(self):
        fake = FakeSupabase(email_confirmed_at=None)
        with self.assertRaises(HTTPException) as ctx:
            run_get_current_user(fake, "user-2")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, "email_not_confirmed")

    def test_anonymous_user_exempt_even_when_unconfirmed(self):
        fake = FakeSupabase(email_confirmed_at=None)
        result = run_get_current_user(fake, "guest-1", email=None, is_anonymous=True)
        self.assertTrue(result.is_anonymous)

    def test_confirmed_status_is_cached_after_first_check(self):
        fake = FakeSupabase(email_confirmed_at="2026-01-01T00:00:00Z")
        run_get_current_user(fake, "user-3")
        run_get_current_user(fake, "user-3")
        self.assertEqual(fake.auth.admin.call_count, 1)

    def test_unconfirmed_status_is_not_cached_and_rechecked_every_call(self):
        fake = FakeSupabase(email_confirmed_at=None)
        for _ in range(3):
            with self.assertRaises(HTTPException):
                run_get_current_user(fake, "user-4")
        self.assertEqual(fake.auth.admin.call_count, 3)

    def test_user_becomes_confirmed_between_requests_unblocks_immediately(self):
        fake = FakeSupabase(email_confirmed_at=None)
        with self.assertRaises(HTTPException):
            run_get_current_user(fake, "user-5")
        fake.auth.admin.email_confirmed_at = "2026-01-02T00:00:00Z"
        result = run_get_current_user(fake, "user-5")
        self.assertEqual(result.id, "user-5")


if __name__ == "__main__":
    unittest.main()
