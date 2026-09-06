"""Tests for GET /plans/me: the entitlement summary endpoint that lets the
frontend /upgrade page distinguish self-serve users, institution students,
and institution admins server-side instead of guessing client-side.

Pure unit tests calling the router function directly (bypassing FastAPI DI),
same convention as test_admin_institutions.py -- a generic fake Supabase
table/select/eq/execute chain, no network, no live DB.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.routers import plans as plans_module  # noqa: E402
from app.routers.auth import UserInfo  # noqa: E402


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, rows):
        self.rows = rows
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
    def __init__(self, profiles=None, members=None, institutions=None, modules=None):
        self.tables = {
            "user_profiles": profiles or [],
            "institution_members": members or [],
            "institutions": institutions or [],
            "institution_modules": modules or [],
        }

    def table(self, name):
        return _FakeTable(self.tables.get(name, []))


def _user(user_id="user-1"):
    return UserInfo(id=user_id, email="u@example.com")


def _profile(user_id="user-1", plan="free", **extra):
    row = {"user_id": user_id, "plan": plan, "plan_expires_at": None, "subscription_status": "none"}
    row.update(extra)
    return row


def _call(fake, user_id="user-1"):
    return plans_module.get_my_plan(current_user=_user(user_id), supabase=fake)


def _plan_row(response, plan_id):
    return next(p for p in response["plans"] if p["id"] == plan_id)


# ── Self-serve, Free plan ────────────────────────────────────────────────

def test_self_serve_free_user():
    fake = _FakeSupabase(profiles=[_profile(plan="free")])
    res = _call(fake)

    assert res["user_type"] == "self_serve"
    assert res["self_serve_plan"] == "free"
    assert res["institution"]["is_member"] is False
    assert res["effective_access"]["speaking"] is True
    assert res["effective_access"]["reading"] is False
    assert res["effective_access"]["listening"] is False
    assert res["effective_access"]["writing"] is False
    assert res["effective_access"]["mock"] is False

    assert _plan_row(res, "free")["is_current"] is True
    assert _plan_row(res, "free")["is_purchasable"] is False
    for plan_id in ("basic", "pro", "elite"):
        assert _plan_row(res, plan_id)["is_current"] is False
        assert _plan_row(res, plan_id)["is_purchasable"] is True


# ── Self-serve, paid Basic plan ──────────────────────────────────────────

def test_self_serve_basic_user_current_plan_not_purchasable():
    fake = _FakeSupabase(profiles=[_profile(plan="basic", plan_expires_at="2099-01-01T00:00:00Z")])
    res = _call(fake)

    assert res["user_type"] == "self_serve"
    assert res["self_serve_plan"] == "basic"
    assert res["effective_access"]["reading"] is True
    assert res["effective_access"]["listening"] is True
    assert res["effective_access"]["writing"] is False

    assert _plan_row(res, "basic")["is_current"] is True
    assert _plan_row(res, "basic")["is_purchasable"] is False
    assert _plan_row(res, "free")["is_purchasable"] is False
    assert _plan_row(res, "pro")["is_purchasable"] is True
    assert _plan_row(res, "elite")["is_purchasable"] is True


# ── Self-serve, paid Pro plan ────────────────────────────────────────────

def test_self_serve_pro_user_upgrade_rules():
    fake = _FakeSupabase(profiles=[_profile(plan="pro", plan_expires_at="2099-01-01T00:00:00Z")])
    res = _call(fake)

    assert res["self_serve_plan"] == "pro"
    assert _plan_row(res, "free")["is_purchasable"] is False
    assert _plan_row(res, "basic")["is_purchasable"] is False
    assert _plan_row(res, "pro")["is_current"] is True
    assert _plan_row(res, "pro")["is_purchasable"] is False
    assert _plan_row(res, "elite")["is_purchasable"] is True


# ── Self-serve, paid Elite plan (top of the ladder) ──────────────────────

def test_self_serve_elite_user_nothing_purchasable():
    fake = _FakeSupabase(profiles=[_profile(plan="elite", plan_expires_at="2099-01-01T00:00:00Z")])
    res = _call(fake)

    assert res["self_serve_plan"] == "elite"
    assert _plan_row(res, "elite")["is_current"] is True
    for plan_id in ("free", "basic", "pro", "elite"):
        assert _plan_row(res, plan_id)["is_purchasable"] is False


# ── Institution student, speaking-only grant ─────────────────────────────

def test_institution_student_speaking_only():
    fake = _FakeSupabase(
        profiles=[_profile(plan="free")],
        members=[{"institution_id": "inst-a", "user_id": "user-1", "status": "active", "role": "student"}],
        institutions=[{"id": "inst-a", "name": "Acme Nursing", "status": "active", "speaking_sessions_per_month": 20, "created_at": "2026-01-01"}],
        modules=[{"institution_id": "inst-a", "module": "speaking", "enabled": True}],
    )
    res = _call(fake)

    assert res["user_type"] == "institution_student"
    assert res["institution"]["is_member"] is True
    assert res["institution"]["status"] == "active"
    assert res["institution"]["name"] == "Acme Nursing"
    assert res["institution"]["enabled_modules"] == ["speaking"]
    assert res["institution"]["speaking_sessions_per_month"] == 20
    assert res["effective_access"]["speaking"] is True
    assert res["effective_access"]["reading"] is False


# ── Institution student, multiple modules granted ────────────────────────

def test_institution_student_multiple_modules():
    fake = _FakeSupabase(
        profiles=[_profile(plan="free")],
        members=[{"institution_id": "inst-b", "user_id": "user-1", "status": "active", "role": "student"}],
        institutions=[{"id": "inst-b", "name": "Beta College", "status": "active", "speaking_sessions_per_month": 15, "created_at": "2026-01-01"}],
        modules=[
            {"institution_id": "inst-b", "module": "speaking", "enabled": True},
            {"institution_id": "inst-b", "module": "reading", "enabled": True},
            {"institution_id": "inst-b", "module": "listening", "enabled": False},
        ],
    )
    res = _call(fake)

    assert res["institution"]["enabled_modules"] == ["reading", "speaking"]
    assert res["effective_access"]["reading"] is True
    assert res["effective_access"]["listening"] is False

    # paid upgrade options must still be visible/purchasable to an institution student
    assert _plan_row(res, "basic")["is_purchasable"] is True
    assert _plan_row(res, "pro")["is_purchasable"] is True
    assert _plan_row(res, "elite")["is_purchasable"] is True
    assert _plan_row(res, "free")["is_purchasable"] is False


# ── Institution grant + paid B2C plan coexist ────────────────────────────

def test_institution_grant_does_not_shadow_paid_b2c_plan():
    fake = _FakeSupabase(
        profiles=[_profile(plan="pro", plan_expires_at="2099-01-01T00:00:00Z")],
        members=[{"institution_id": "inst-c", "user_id": "user-1", "status": "active", "role": "student"}],
        institutions=[{"id": "inst-c", "name": "Gamma Institute", "status": "active", "speaking_sessions_per_month": 10, "created_at": "2026-01-01"}],
        modules=[{"institution_id": "inst-c", "module": "speaking", "enabled": True}],  # institution grants speaking only
    )
    res = _call(fake)

    assert res["self_serve_plan"] == "pro"
    # writing is Pro-gated in B2C and NOT granted by the institution -- must
    # still be true because B2C access is OR'd with institution access, never
    # overwritten by it.
    assert res["effective_access"]["writing"] is True
    assert _plan_row(res, "pro")["is_current"] is True
    assert _plan_row(res, "pro")["is_purchasable"] is False
    # institution grants must never inflate B2C plan-rank comparisons --
    # a Pro self-serve plan still can't "buy" Basic, institution or not.
    assert _plan_row(res, "basic")["is_purchasable"] is False
    assert _plan_row(res, "elite")["is_purchasable"] is True


# ── Institution student with B2C Elite: nothing left to purchase ────────

def test_institution_student_elite_b2c_cannot_purchase_lower_tiers():
    fake = _FakeSupabase(
        profiles=[_profile(plan="elite", plan_expires_at="2099-01-01T00:00:00Z")],
        members=[{"institution_id": "inst-f", "user_id": "user-1", "status": "active", "role": "student"}],
        institutions=[{"id": "inst-f", "name": "Epsilon Uni", "status": "active", "speaking_sessions_per_month": 10, "created_at": "2026-01-01"}],
        modules=[{"institution_id": "inst-f", "module": "speaking", "enabled": True}],
    )
    res = _call(fake)

    assert res["self_serve_plan"] == "elite"
    assert _plan_row(res, "elite")["is_current"] is True
    for plan_id in ("free", "basic", "pro", "elite"):
        assert _plan_row(res, plan_id)["is_purchasable"] is False


# ── Suspended institution membership falls back to self-serve ───────────

def test_suspended_institution_membership_falls_back_to_self_serve():
    fake = _FakeSupabase(
        profiles=[_profile(plan="free")],
        members=[{"institution_id": "inst-d", "user_id": "user-1", "status": "active", "role": "student"}],
        institutions=[{"id": "inst-d", "name": "Suspended U", "status": "suspended", "speaking_sessions_per_month": 20, "created_at": "2026-01-01"}],
        modules=[{"institution_id": "inst-d", "module": "speaking", "enabled": True}],
    )
    res = _call(fake)

    assert res["user_type"] == "self_serve"
    assert res["institution"]["is_member"] is False
    assert res["institution"]["enabled_modules"] == []


# ── No institution membership at all ─────────────────────────────────────

def test_no_institution_membership():
    fake = _FakeSupabase(profiles=[_profile(plan="free")])
    res = _call(fake)

    assert res["user_type"] == "self_serve"
    assert res["institution"]["is_member"] is False
    assert res["institution"]["name"] is None


# ── Institution admin role ────────────────────────────────────────────────

def test_institution_admin_role():
    fake = _FakeSupabase(
        profiles=[_profile(plan="free")],
        members=[{"institution_id": "inst-e", "user_id": "user-1", "status": "active", "role": "institution_admin"}],
        institutions=[{"id": "inst-e", "name": "Delta School", "status": "active", "speaking_sessions_per_month": 30, "created_at": "2026-01-01"}],
        modules=[{"institution_id": "inst-e", "module": "speaking", "enabled": True}],
    )
    res = _call(fake)

    assert res["user_type"] == "institution_admin"


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
