"""RC3.4 self-check: staff role assignment, owner-only gating, last-owner
protection, and owner inheritance across the RC3 require_* tiers. Uses the
same minimal in-memory Supabase fake as test_draft_workflow.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import HTTPException

from app.routers import admin
from app.routers.auth import UserInfo


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self._filters = []
        self._op = None
        self._payload = None

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def upsert(self, payload, **_k):
        self._op = "upsert"
        self._payload = payload
        return self

    def execute(self):
        matched = [r for r in self._rows if all(r.get(c) == v for c, v in self._filters)]
        if self._op == "insert":
            self._rows.append(dict(self._payload))
            return FakeResult([self._payload])
        if self._op == "upsert":
            existing = next((r for r in self._rows if r.get("user_id") == self._payload.get("user_id")), None)
            if existing:
                existing.update(self._payload)
            else:
                self._rows.append(dict(self._payload))
            return FakeResult([self._payload])
        return FakeResult(matched)


class FakeSupabase:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        self.tables.setdefault(name, [])
        return FakeQuery(self.tables[name])


def _user(uid, email="staff@x.com"):
    return UserInfo(id=uid, email=email, name="", is_anonymous=False)


def _patched(monkeypatch, roles):
    fake = FakeSupabase()
    fake.tables["user_roles"] = roles
    monkeypatch.setattr(admin, "get_supabase", lambda: fake)
    return fake


# ── role assignment ──────────────────────────────────────────────────

def test_owner_can_assign_role(monkeypatch):
    fake = _patched(monkeypatch, [
        {"user_id": "owner1", "role": "owner"},
        {"user_id": "u2", "role": "user"},
    ])
    result = admin.admin_set_user_role(admin.SetRoleRequest(user_id="u2", role="analyst"), _user("owner1"))
    assert result == {"success": True}
    assert admin._get_role(fake, "u2") == "analyst"
    audit = fake.tables["audit_log"]
    assert audit[-1]["action"] == "staff_role_changed"
    assert audit[-1]["detail"] == {"old_role": "user", "new_role": "analyst"}


def test_rejects_unknown_role(monkeypatch):
    _patched(monkeypatch, [{"user_id": "owner1", "role": "owner"}])
    with pytest.raises(HTTPException) as exc:
        admin.admin_set_user_role(admin.SetRoleRequest(user_id="u2", role="superadmin"), _user("owner1"))
    assert exc.value.status_code == 400


# ── last owner protection ────────────────────────────────────────────

def test_cannot_demote_last_owner(monkeypatch):
    fake = _patched(monkeypatch, [{"user_id": "owner1", "role": "owner"}])
    with pytest.raises(HTTPException) as exc:
        admin.admin_set_user_role(admin.SetRoleRequest(user_id="owner1", role="admin"), _user("owner1"))
    assert exc.value.status_code == 400
    assert admin._get_role(fake, "owner1") == "owner"


def test_can_demote_owner_when_second_owner_exists(monkeypatch):
    fake = _patched(monkeypatch, [
        {"user_id": "owner1", "role": "owner"},
        {"user_id": "owner2", "role": "owner"},
    ])
    admin.admin_set_user_role(admin.SetRoleRequest(user_id="owner1", role="admin"), _user("owner2"))
    assert admin._get_role(fake, "owner1") == "admin"


# ── non-owner cannot assign owner (enforced at the require_owner gate) ─

def test_non_owner_blocked_by_require_owner_dependency(monkeypatch):
    _patched(monkeypatch, [{"user_id": "admin1", "role": "admin"}])
    with pytest.raises(HTTPException) as exc:
        admin.require_owner(_user("admin1"))
    assert exc.value.status_code == 403


# ── owner inheritance: owner clears every RC3 role gate ────────────────

def test_owner_passes_every_role_gate(monkeypatch):
    _patched(monkeypatch, [{"user_id": "owner1", "role": "owner"}])
    owner = _user("owner1")
    for dep in (admin.require_support, admin.require_analyst, admin.require_admin, admin.require_owner):
        assert dep(owner) is owner


def test_admin_blocked_from_owner_gate_but_not_lower(monkeypatch):
    _patched(monkeypatch, [{"user_id": "admin1", "role": "admin"}])
    staff = _user("admin1")
    assert admin.require_admin(staff) is staff
    with pytest.raises(HTTPException):
        admin.require_owner(staff)


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.run(["pytest", __file__, "-q"]).returncode)
