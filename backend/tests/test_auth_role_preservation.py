"""
LB-4: Admin Self-Demotion regression tests.

Reproduces the bug in app.routers.auth.get_current_user, which used to run
an unconditional upsert({"role": "user"}, on_conflict="user_id") on every
authenticated request. Because that upsert had no ignore_duplicates flag,
Postgres executed INSERT ... ON CONFLICT (user_id) DO UPDATE, which
overwrote any existing role (including 'admin') back to 'user' every time
the 15-minute in-memory cache expired (e.g. after any server restart).

These tests use a minimal in-memory fake of the Supabase postgrest client
that implements real ON CONFLICT semantics (DO UPDATE vs DO NOTHING), so the
tests actually exercise the same upsert/ignore_duplicates contract Postgres
would enforce, not just "was upsert called".

No pytest dependency is required; run with:
    python -m unittest backend/tests/test_auth_role_preservation.py -v
"""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import jwt
from fastapi import HTTPException
from postgrest.exceptions import APIError as PostgrestAPIError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers import auth as auth_module  # noqa: E402
from app.core.config import settings  # noqa: E402

TEST_JWT_SECRET = "test-jwt-secret-at-least-32-bytes-long"


def make_token(user_id, email="nurse@example.com"):
    return jwt.encode(
        {
            "sub": user_id,
            "email": email,
            "aud": "authenticated",
            "user_metadata": {"name": "Test Nurse"},
            "exp": time.time() + 3600,
        },
        TEST_JWT_SECRET,
        algorithm="HS256",
    )


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeTable:
    """In-memory stand-in for a Supabase table with real upsert semantics."""

    def __init__(self, rows_by_id):
        self._rows = rows_by_id  # dict[str, dict] keyed by user_id/id

    def upsert(self, row, on_conflict=None, ignore_duplicates=False):
        key = row.get("user_id") or row.get("id")
        exists = key in self._rows
        if exists and ignore_duplicates:
            pass  # ON CONFLICT DO NOTHING -- existing row untouched
        else:
            self._rows[key] = dict(row)  # INSERT or DO UPDATE
        return self

    def select(self, *_args, **_kwargs):
        self._pending_select = True
        return self

    def eq(self, _column, value):
        self._filter_value = value
        return self

    def execute(self):
        if getattr(self, "_pending_select", False):
            self._pending_select = False
            row = self._rows.get(self._filter_value)
            return FakeResult([row] if row else [])
        return FakeResult(list(self._rows.values()))


class FakeAuthUser:
    def __init__(self, email_confirmed_at="2026-01-01T00:00:00Z"):
        self.email_confirmed_at = email_confirmed_at


class FakeAuthAdmin:
    """Always reports the user as confirmed -- these tests exercise role
    preservation, not the email-confirmation gate (see
    test_email_confirmation_gate.py for that)."""

    def get_user_by_id(self, _user_id):
        return MagicMock(user=FakeAuthUser())


class FakeAuth:
    def __init__(self):
        self.admin = FakeAuthAdmin()


class FakeSupabase:
    def __init__(self, rows_by_id):
        self._rows = rows_by_id
        self._mirror_rows: dict = {}  # public.users -- see get_current_user's second upsert
        self.auth = FakeAuth()

    def table(self, name):
        if name == "user_roles":
            return FakeTable(self._rows)
        if name == "users":
            return FakeTable(self._mirror_rows)
        raise AssertionError(f"unexpected table: {name!r}")


def run_get_current_user(fake_supabase, user_id):
    """Invoke the real get_current_user() logic against a fake Supabase client.

    get_current_user() verifies the token locally (HS256, project JWT
    secret) instead of calling Supabase Auth over the network, so the test
    signs a real token with a test secret rather than mocking .auth.get_user().
    """
    credentials = MagicMock(credentials=make_token(user_id))
    original_get_supabase = auth_module.get_supabase
    original_secret = settings.SUPABASE_JWT_SECRET
    auth_module.get_supabase = lambda: fake_supabase
    settings.SUPABASE_JWT_SECRET = TEST_JWT_SECRET
    try:
        return auth_module.get_current_user(credentials)
    finally:
        auth_module.get_supabase = original_get_supabase
        settings.SUPABASE_JWT_SECRET = original_secret


class AdminSelfDemotionTests(unittest.TestCase):
    def setUp(self):
        auth_module._user_role_cache.clear()
        auth_module._email_confirmed_cache.clear()

    def test_new_user_gets_default_role(self):
        rows = {}
        fake = FakeSupabase(rows)
        run_get_current_user(fake, "new-user-1")
        self.assertEqual(rows["new-user-1"]["role"], "user")

    def test_existing_user_remains_user(self):
        rows = {"user-1": {"user_id": "user-1", "role": "user"}}
        fake = FakeSupabase(rows)
        run_get_current_user(fake, "user-1")
        self.assertEqual(rows["user-1"]["role"], "user")

    def test_existing_admin_remains_admin(self):
        rows = {"admin-1": {"user_id": "admin-1", "role": "admin"}}
        fake = FakeSupabase(rows)
        run_get_current_user(fake, "admin-1")
        self.assertEqual(rows["admin-1"]["role"], "admin")

    def test_token_refresh_does_not_change_role(self):
        """Simulates repeated token refreshes, each re-invoking get_current_user
        after the in-memory cache TTL has elapsed (e.g. across server restarts
        or separate worker processes)."""
        rows = {"admin-2": {"user_id": "admin-2", "role": "admin"}}
        fake = FakeSupabase(rows)
        for _ in range(5):
            auth_module._user_role_cache.pop("admin-2", None)  # simulate TTL/restart
            run_get_current_user(fake, "admin-2")
            self.assertEqual(rows["admin-2"]["role"], "admin")

    def test_login_logout_cycle_does_not_change_role(self):
        rows = {"admin-3": {"user_id": "admin-3", "role": "admin"}}
        fake = FakeSupabase(rows)
        for _ in range(3):
            auth_module._user_role_cache.clear()  # simulate a fresh login session
            run_get_current_user(fake, "admin-3")
        self.assertEqual(rows["admin-3"]["role"], "admin")

    def test_cache_prevents_redundant_upserts_within_ttl(self):
        rows = {"user-2": {"user_id": "user-2", "role": "user"}}
        fake = FakeSupabase(rows)
        run_get_current_user(fake, "user-2")
        cached_at = auth_module._user_role_cache["user-2"]
        run_get_current_user(fake, "user-2")
        self.assertEqual(auth_module._user_role_cache["user-2"], cached_at)

    def test_missing_auth_user_fk_violation_becomes_401(self):
        """PR B regression: user_roles.user_id FKs to auth.users(id) (verified
        against the live schema -- see PR discussion). A JWT is only verified
        locally (signature/expiry), so it carries no guarantee the subject
        still exists in auth.users -- e.g. the account was deleted after the
        token was issued. Before this fix, the resulting 23503 FK violation
        propagated as an unhandled 500; it must now surface as a clean 401."""
        class FakeFKViolationTable:
            def upsert(self, _row, on_conflict=None, ignore_duplicates=False):
                raise PostgrestAPIError({
                    "code": "23503",
                    "message": (
                        'insert or update on table "user_roles" violates '
                        'foreign key constraint "user_roles_user_id_fkey"'
                    ),
                    "details": 'Key (user_id)=(ghost-user) is not present in table "users".',
                    "hint": None,
                })

        class FakeSupabaseFKViolation:
            def __init__(self):
                self.auth = FakeAuth()

            def table(self, name):
                if name == "user_roles":
                    return FakeFKViolationTable()
                raise AssertionError(f"unexpected table: {name!r}")

        fake = FakeSupabaseFKViolation()
        with self.assertRaises(HTTPException) as ctx:
            run_get_current_user(fake, "ghost-user")
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Authentication failed")

    def test_users_mirror_synced_alongside_role(self):
        """The users-mirror table sync (2026-07-18_users_mirror.sql) rides
        the same request that upserts user_roles -- verifies it actually
        writes email/name, unlike the ignore_duplicates=True role upsert
        this test class otherwise exercises."""
        rows = {}
        fake = FakeSupabase(rows)
        run_get_current_user(fake, "new-user-2")
        mirror_row = fake._mirror_rows["new-user-2"]
        self.assertEqual(mirror_row["email"], "nurse@example.com")
        self.assertEqual(mirror_row["name"], "Test Nurse")


if __name__ == "__main__":
    unittest.main()
