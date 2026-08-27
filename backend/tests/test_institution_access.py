"""
Tests for the institutional access foundation (Phase 1): effective module
access = B2C plan access OR active institution grant, plus the
institution-level speaking quota override.

Pure unit tests against app.services.institution_access and
app.services.plan_gating.has_effective_module_access, using a fake Supabase
client (table/select/eq/in_/execute chain, same style as
test_subscription_lifecycle.py) -- no network, no live DB.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.institution_access import (
    get_active_institution_module_access,
    has_institution_module_access,
    get_effective_speaking_limit,
)
from app.services.plan_gating import has_effective_module_access


# ── Fake Supabase client ────────────────────────────────────────────────

class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, rows, name):
        self.rows = rows
        self.name = name
        self._filters = {}

    def select(self, _cols):
        return self

    def eq(self, col, val):
        self._filters[col] = ("eq", val)
        return self

    def in_(self, col, vals):
        self._filters[col] = ("in", set(vals))
        return self

    def execute(self):
        out = []
        for row in self.rows:
            ok = True
            for col, (op, val) in self._filters.items():
                if op == "eq" and row.get(col) != val:
                    ok = False
                elif op == "in" and row.get(col) not in val:
                    ok = False
            if ok:
                out.append(row)
        return _FakeResult(out)


class _FakeSupabase:
    """institution_members/institutions/institution_modules rows are seeded
    directly; unknown table names return an empty result set."""

    def __init__(self, members=None, institutions=None, modules=None):
        self.tables = {
            "institution_members": members or [],
            "institutions": institutions or [],
            "institution_modules": modules or [],
        }

    def table(self, name):
        return _FakeTable(self.tables.get(name, []), name)


# ── Fixtures: Institution A (pilot: speaking only), Institution B (future) ──

def _speaking_only_institution(institution_id="inst-a", quota=20, status="active"):
    return {
        "members": [
            {"institution_id": institution_id, "user_id": "student-1", "status": "active"},
        ],
        "institutions": [
            {"id": institution_id, "status": status, "speaking_sessions_per_month": quota},
        ],
        "modules": [
            {"institution_id": institution_id, "module": "speaking", "enabled": True},
            {"institution_id": institution_id, "module": "reading", "enabled": False},
        ],
    }


# ── Test 1: existing B2C user, no institution membership ────────────────

def test_b2c_user_with_no_membership_has_no_institution_access():
    supabase = _FakeSupabase()  # no rows anywhere
    access = get_active_institution_module_access(supabase, "b2c-user")
    assert access["modules"] == set()
    assert access["speaking_sessions_per_month"] is None


def test_b2c_user_effective_access_matches_plan_access_only():
    supabase = _FakeSupabase()
    # free plan has no reading access, and no institution grant either
    assert has_effective_module_access(supabase, "b2c-user", "free", "reading") is False
    # pro plan has writing access on its own -- institution lookup shouldn't matter
    assert has_effective_module_access(supabase, "b2c-user", "pro", "writing") is True


# ── Test 2: institution student, Speaking enabled only ───────────────────

def test_institution_student_speaking_only_grants_speaking_not_others():
    fx = _speaking_only_institution()
    supabase = _FakeSupabase(**fx)
    access = get_active_institution_module_access(supabase, "student-1")
    assert access["modules"] == {"speaking"}
    assert access["speaking_sessions_per_month"] == 20

    assert has_institution_module_access(supabase, "student-1", "speaking") is True
    for module in ("reading", "listening", "writing", "mock_tests"):
        assert has_institution_module_access(supabase, "student-1", module) is False


def test_institution_student_effective_access_via_plan_gating():
    fx = _speaking_only_institution()
    supabase = _FakeSupabase(**fx)
    # free plan alone would deny reading -- institution grant also denies it (disabled)
    assert has_effective_module_access(supabase, "student-1", "free", "reading") is False
    assert has_effective_module_access(supabase, "student-1", "free", "listening") is False
    assert has_effective_module_access(supabase, "student-1", "free", "writing") is False
    assert has_effective_module_access(supabase, "student-1", "free", "mock_tests") is False


# ── Test 3: institution student, Speaking + Reading enabled ─────────────

def test_institution_student_speaking_and_reading_enabled():
    supabase = _FakeSupabase(
        members=[{"institution_id": "inst-b", "user_id": "student-2", "status": "active"}],
        institutions=[{"id": "inst-b", "status": "active", "speaking_sessions_per_month": 20}],
        modules=[
            {"institution_id": "inst-b", "module": "speaking", "enabled": True},
            {"institution_id": "inst-b", "module": "reading", "enabled": True},
            {"institution_id": "inst-b", "module": "listening", "enabled": False},
        ],
    )
    assert has_effective_module_access(supabase, "student-2", "free", "reading") is True
    assert has_effective_module_access(supabase, "student-2", "free", "listening") is False
    assert has_effective_module_access(supabase, "student-2", "free", "writing") is False
    assert has_effective_module_access(supabase, "student-2", "free", "mock_tests") is False


# ── Test 4: suspended institution ────────────────────────────────────────

def test_suspended_institution_denies_all_grants():
    fx = _speaking_only_institution(status="suspended")
    supabase = _FakeSupabase(**fx)
    access = get_active_institution_module_access(supabase, "student-1")
    assert access["modules"] == set()
    assert has_institution_module_access(supabase, "student-1", "speaking") is False


# ── Test 5: revoked membership ───────────────────────────────────────────

def test_revoked_membership_denies_all_grants():
    fx = _speaking_only_institution()
    fx["members"][0]["status"] = "revoked"
    supabase = _FakeSupabase(**fx)
    access = get_active_institution_module_access(supabase, "student-1")
    assert access["modules"] == set()
    assert has_institution_module_access(supabase, "student-1", "speaking") is False


# ── Test 6: disabled module ──────────────────────────────────────────────

def test_disabled_module_denies_that_module_only():
    fx = _speaking_only_institution()
    fx["modules"][0]["enabled"] = False  # speaking disabled
    supabase = _FakeSupabase(**fx)
    assert has_institution_module_access(supabase, "student-1", "speaking") is False


# ── Test 7: cross-institution isolation ──────────────────────────────────

def test_membership_in_institution_a_does_not_grant_institution_b_modules():
    supabase = _FakeSupabase(
        members=[{"institution_id": "inst-a", "user_id": "student-1", "status": "active"}],
        institutions=[
            {"id": "inst-a", "status": "active", "speaking_sessions_per_month": 20},
            {"id": "inst-b", "status": "active", "speaking_sessions_per_month": 20},
        ],
        modules=[
            {"institution_id": "inst-a", "module": "speaking", "enabled": True},
            # institution B grants reading, but student-1 has no membership there
            {"institution_id": "inst-b", "module": "reading", "enabled": True},
        ],
    )
    access = get_active_institution_module_access(supabase, "student-1")
    assert access["modules"] == {"speaking"}
    assert "reading" not in access["modules"]


# ── get_effective_speaking_limit: institution quota vs B2C plan quota ────

def test_effective_speaking_limit_uses_institution_quota_when_granted():
    fx = _speaking_only_institution(quota=20)
    supabase = _FakeSupabase(**fx)
    # underlying B2C plan is free (limit 3) -- institution quota must win,
    # not be capped at the B2C free-plan limit
    assert get_effective_speaking_limit(supabase, "student-1", "free") == 20


def test_effective_speaking_limit_falls_back_to_plan_limit_without_institution_grant():
    supabase = _FakeSupabase()
    assert get_effective_speaking_limit(supabase, "b2c-user", "free") == 3
    assert get_effective_speaking_limit(supabase, "b2c-user", "elite") == 80


def test_effective_speaking_limit_ignores_institution_grant_that_excludes_speaking():
    supabase = _FakeSupabase(
        members=[{"institution_id": "inst-c", "user_id": "student-3", "status": "active"}],
        institutions=[{"id": "inst-c", "status": "active", "speaking_sessions_per_month": 20}],
        modules=[{"institution_id": "inst-c", "module": "reading", "enabled": True}],  # no speaking
    )
    assert get_effective_speaking_limit(supabase, "student-3", "free") == 3


if __name__ == "__main__":
    import inspect
    mod = sys.modules[__name__]
    tests = [f for name, f in vars(mod).items() if name.startswith("test_") and inspect.isfunction(f)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
