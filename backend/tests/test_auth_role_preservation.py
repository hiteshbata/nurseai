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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers import auth as auth_module  # noqa: E402


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeTable:
    """In-memory stand-in for a Supabase table with real upsert semantics."""

    def __init__(self, rows_by_id):
        self._rows = rows_by_id  # dict[str, dict] keyed by user_id

    def upsert(self, row, on_conflict=None, ignore_duplicates=False):
        user_id = row["user_id"]
        exists = user_id in self._rows
        if exists and ignore_duplicates:
            pass  # ON CONFLICT DO NOTHING -- existing row untouched
        else:
            self._rows[user_id] = dict(row)  # INSERT or DO UPDATE
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


class FakeSupabase:
    def __init__(self, rows_by_id):
        self._rows = rows_by_id
        self.auth = MagicMock()

    def table(self, name):
        assert name == "user_roles"
        return FakeTable(self._rows)


class FakeAuthUser:
    def __init__(self, user_id, email="nurse@example.com"):
        self.id = user_id
        self.email = email
        self.user_metadata = {"name": "Test Nurse"}


def run_get_current_user(fake_supabase, user_id):
    """Invoke the real get_current_user() logic against a fake Supabase client.

    get_current_user() now verifies tokens via get_auth_client() (a separate
    client, kept isolated from the service-role client used for table
    writes -- see core/supabase.py). fake_supabase.auth doubles as that
    auth client here since both just need a working .auth.get_user().
    """
    fake_supabase.auth.get_user.return_value = MagicMock(user=FakeAuthUser(user_id))
    credentials = MagicMock(credentials="fake-token")
    original_get_supabase = auth_module.get_supabase
    original_get_auth_client = auth_module.get_auth_client
    auth_module.get_supabase = lambda: fake_supabase
    auth_module.get_auth_client = lambda: fake_supabase
    try:
        return auth_module.get_current_user(credentials)
    finally:
        auth_module.get_supabase = original_get_supabase
        auth_module.get_auth_client = original_get_auth_client


class AdminSelfDemotionTests(unittest.TestCase):
    def setUp(self):
        auth_module._user_role_cache.clear()

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


if __name__ == "__main__":
    unittest.main()
