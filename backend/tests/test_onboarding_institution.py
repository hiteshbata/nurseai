"""Phase 3: institution-aware /onboarding/status + tamper protection on
/onboarding/complete. Same fake-Supabase style as
test_institution_free_trial_bypass.py -- table/select/eq/in_/upsert/execute,
no live DB.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.routers import onboarding


class FakeResult:
    def __init__(self, data=None):
        self.data = data if data is not None else []


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self._filters = []

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._filters.append(lambda r, c=col, v=val: r.get(c) == v)
        return self

    def in_(self, col, vals):
        vals = set(vals)
        self._filters.append(lambda r, c=col, v=vals: r.get(c) in v)
        return self

    def upsert(self, body, on_conflict=None):
        self.rows.append(body)
        self._upserted = body
        return self

    def execute(self):
        if hasattr(self, "_upserted"):
            return FakeResult([self._upserted])
        matched = [r for r in self.rows if all(f(r) for f in self._filters)]
        return FakeResult(matched)


class FakeSupabase:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return FakeQuery(self.tables.get(name, []))


_STUDENT = SimpleNamespace(id="student-1", is_anonymous=False)


def _institution_fixture(status="active", member_status="active"):
    return {
        "institution_members": [
            {"institution_id": "inst-a", "user_id": "student-1", "status": member_status},
        ],
        "institutions": [
            {
                "id": "inst-a",
                "name": "ABC Nursing Institute",
                "logo_url": "https://example.com/logo.png",
                "status": status,
                "speaking_sessions_per_month": 20,
                "created_at": "2026-08-01T00:00:00Z",
            },
        ],
        "institution_modules": [
            {"institution_id": "inst-a", "module": "speaking", "enabled": True},
        ],
    }


def _no_institution():
    return {"institution_members": [], "institutions": [], "institution_modules": []}


# ── /onboarding/status ────────────────────────────────────────────────────

def test_status_normal_b2c_user_backwards_compatible(monkeypatch):
    tables = {
        "user_profiles": [{"user_id": "student-1", "onboarding_completed": True, "target_band": "B"}],
        **_no_institution(),
    }
    supabase = FakeSupabase(tables)
    monkeypatch.setattr(onboarding, "get_supabase", lambda: supabase)
    result = onboarding.get_onboarding_status(_STUDENT)
    assert result["onboarding_completed"] is True
    assert result["target_band"] == "B"
    assert result["is_institution_member"] is False
    assert result["institution"] is None


def test_status_no_profile_row_defaults(monkeypatch):
    tables = {"user_profiles": [], **_no_institution()}
    supabase = FakeSupabase(tables)
    monkeypatch.setattr(onboarding, "get_supabase", lambda: supabase)
    result = onboarding.get_onboarding_status(_STUDENT)
    assert result["onboarding_completed"] is False
    assert result["is_institution_member"] is False


def test_status_active_institution_member(monkeypatch):
    tables = {
        "user_profiles": [{"user_id": "student-1", "onboarding_completed": False}],
        **_institution_fixture(),
    }
    supabase = FakeSupabase(tables)
    monkeypatch.setattr(onboarding, "get_supabase", lambda: supabase)
    result = onboarding.get_onboarding_status(_STUDENT)
    assert result["is_institution_member"] is True
    assert result["institution"]["name"] == "ABC Nursing Institute"
    assert result["institution"]["logo_url"] == "https://example.com/logo.png"
    assert result["institution"]["modules"] == ["speaking"]


def test_status_revoked_membership_hides_institution(monkeypatch):
    tables = {
        "user_profiles": [{"user_id": "student-1", "onboarding_completed": False}],
        **_institution_fixture(member_status="revoked"),
    }
    supabase = FakeSupabase(tables)
    monkeypatch.setattr(onboarding, "get_supabase", lambda: supabase)
    result = onboarding.get_onboarding_status(_STUDENT)
    assert result["is_institution_member"] is False
    assert result["institution"] is None


def test_status_suspended_institution_hides_institution(monkeypatch):
    tables = {
        "user_profiles": [{"user_id": "student-1", "onboarding_completed": False}],
        **_institution_fixture(status="suspended"),
    }
    supabase = FakeSupabase(tables)
    monkeypatch.setattr(onboarding, "get_supabase", lambda: supabase)
    result = onboarding.get_onboarding_status(_STUDENT)
    assert result["is_institution_member"] is False
    assert result["institution"] is None


# ── /onboarding/complete ──────────────────────────────────────────────────

def test_complete_accepts_shortened_institution_payload(monkeypatch):
    tables = {"user_profiles": []}
    supabase = FakeSupabase(tables)
    monkeypatch.setattr(onboarding, "get_supabase", lambda: supabase)
    payload = onboarding.OnboardingCreate(target_band="B", onboarding_completed=True)
    result = onboarding.complete_onboarding(payload, _STUDENT)
    assert result["onboarding_completed"] is True
    assert result["target_band"] == "B"


def test_complete_ignores_client_supplied_institution_fields(monkeypatch):
    """OnboardingCreate has no institution_id/institution_modules/role field --
    Pydantic drops unknown keys, so a tampering client can't smuggle
    membership/module/role changes through this endpoint."""
    tables = {"user_profiles": []}
    supabase = FakeSupabase(tables)
    monkeypatch.setattr(onboarding, "get_supabase", lambda: supabase)
    raw = {
        "target_band": "B",
        "onboarding_completed": True,
        "institution_id": "attacker-institution",
        "institution_modules": ["reading"],
        "role": "institution_admin",
    }
    payload = onboarding.OnboardingCreate(**raw)
    result = onboarding.complete_onboarding(payload, _STUDENT)
    assert "institution_id" not in result
    assert "institution_modules" not in result
    assert "role" not in result
    assert result["target_band"] == "B"


if __name__ == "__main__":
    import inspect
    mod = sys.modules[__name__]
    tests = [(name, f) for name, f in vars(mod).items() if name.startswith("test_") and inspect.isfunction(f)]
    failed = 0

    class MP:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    mp = MP()
    for name, t in tests:
        try:
            if "monkeypatch" in inspect.signature(t).parameters:
                t(mp)
            else:
                t()
            print(f"PASS {name}")
        except Exception as e:
            failed += 1
            print(f"FAIL {name}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
