"""Option 1: suppress the B2C free-trial/lifetime-attempt bypass for active
institution members, while keeping the existing
`B2C subscription access OR institution grant` model (has_effective_module_access)
untouched.

Router-level regression tests -- reading._require_reading_plan,
listening._require_listening_plan, mock.start_mock, writing._require_writing_plan
-- called directly against a fake Supabase client (table/select/eq/in_/order/
limit/execute, same style as test_speaking_session_quota.py), no live DB.
"""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import HTTPException

from app.routers import reading, listening, mock, writing
from app.routers.mock import StartMockRequest


def _run(coro):
    return asyncio.run(coro)


# ── Fake Supabase: table/select(count=)/eq/in_/order/limit/execute ───────

class FakeResult:
    def __init__(self, data=None, count=None):
        self.data = data if data is not None else []
        self.count = count


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self._filters = []
        self._count_mode = None
        self._limit = None

    def select(self, *_a, count=None, **_k):
        self._count_mode = count
        return self

    def eq(self, col, val):
        self._filters.append(lambda r, c=col, v=val: r.get(c) == v)
        return self

    def in_(self, col, vals):
        vals = set(vals)
        self._filters.append(lambda r, c=col, v=vals: r.get(c) in v)
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        matched = [r for r in self.rows if all(f(r) for f in self._filters)]
        if self._limit is not None:
            matched = matched[: self._limit]
        if self._count_mode == "exact":
            return FakeResult(matched, count=len(matched))
        return FakeResult(matched)


class FakeSupabase:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return FakeQuery(self.tables.get(name, []))


_STUDENT = SimpleNamespace(id="student-1", is_anonymous=False)

_FREE_PROFILE = {"user_id": "student-1", "plan": "free", "plan_expires_at": None}
_PRO_PROFILE = {"user_id": "student-1", "plan": "pro", "plan_expires_at": "2099-01-01T00:00:00Z"}


def _speaking_only_institution(status="active", member_status="active"):
    return {
        "institution_members": [
            {"institution_id": "inst-a", "user_id": "student-1", "status": member_status},
        ],
        "institutions": [
            {"id": "inst-a", "status": status, "speaking_sessions_per_month": 20},
        ],
        "institution_modules": [
            {"institution_id": "inst-a", "module": "speaking", "enabled": True},
        ],
    }


def _no_institution():
    return {"institution_members": [], "institutions": [], "institution_modules": []}


# ── Reading ────────────────────────────────────────────────────────────

def test_reading_free_institution_student_denied_no_free_trial_bypass():
    tables = {"user_profiles": [_FREE_PROFILE], "submissions": [], **_speaking_only_institution()}
    supabase = FakeSupabase(tables)
    with pytest.raises(HTTPException) as exc:
        reading._require_reading_plan(supabase, _STUDENT)
    assert exc.value.status_code == 403


def test_reading_free_institution_student_allowed_when_institution_enables_it():
    fx = _speaking_only_institution()
    fx["institution_modules"].append({"institution_id": "inst-a", "module": "reading", "enabled": True})
    tables = {"user_profiles": [_FREE_PROFILE], "submissions": [], **fx}
    supabase = FakeSupabase(tables)
    assert reading._require_reading_plan(supabase, _STUDENT) == "free"


def test_reading_normal_free_b2c_user_free_trial_unchanged():
    tables = {"user_profiles": [_FREE_PROFILE], "submissions": [], **_no_institution()}
    supabase = FakeSupabase(tables)
    assert reading._require_reading_plan(supabase, _STUDENT) == "free"


def test_reading_paid_institution_member_keeps_pro_access_when_institution_disables_it():
    fx = _speaking_only_institution()  # reading not in institution_modules -> disabled
    tables = {"user_profiles": [_PRO_PROFILE], "submissions": [], **fx}
    supabase = FakeSupabase(tables)
    assert reading._require_reading_plan(supabase, _STUDENT) == "pro"


def test_reading_revoked_membership_falls_back_to_normal_free_trial():
    fx = _speaking_only_institution(member_status="revoked")
    tables = {"user_profiles": [_FREE_PROFILE], "submissions": [], **fx}
    supabase = FakeSupabase(tables)
    assert reading._require_reading_plan(supabase, _STUDENT) == "free"


def test_reading_suspended_institution_falls_back_to_normal_free_trial():
    fx = _speaking_only_institution(status="suspended")
    tables = {"user_profiles": [_FREE_PROFILE], "submissions": [], **fx}
    supabase = FakeSupabase(tables)
    assert reading._require_reading_plan(supabase, _STUDENT) == "free"


# ── Listening ──────────────────────────────────────────────────────────

def test_listening_free_institution_student_denied_no_free_trial_bypass():
    tables = {"user_profiles": [_FREE_PROFILE], "submissions": [], **_speaking_only_institution()}
    supabase = FakeSupabase(tables)
    with pytest.raises(HTTPException) as exc:
        listening._require_listening_plan(supabase, _STUDENT)
    assert exc.value.status_code == 403


def test_listening_normal_free_b2c_user_free_trial_unchanged():
    tables = {"user_profiles": [_FREE_PROFILE], "submissions": [], **_no_institution()}
    supabase = FakeSupabase(tables)
    assert listening._require_listening_plan(supabase, _STUDENT) == "free"


# ── Writing (regression: already institution-aware, no standalone bypass) ─

def test_writing_free_institution_student_denied():
    tables = {"user_profiles": [_FREE_PROFILE], **_speaking_only_institution()}
    supabase = FakeSupabase(tables)
    with pytest.raises(HTTPException) as exc:
        _run(writing._require_writing_plan(supabase, "student-1"))
    assert exc.value.status_code == 403


def test_writing_paid_institution_member_keeps_pro_access():
    fx = _speaking_only_institution()  # writing not institution-enabled
    tables = {"user_profiles": [_PRO_PROFILE], **fx}
    supabase = FakeSupabase(tables)
    assert _run(writing._require_writing_plan(supabase, "student-1")) == "pro"


# ── Mock Test ──────────────────────────────────────────────────────────

def _mock_tables(profile, prior_sessions=None, **institution_fx):
    return {
        "user_profiles": [profile],
        "mock_test_sessions": prior_sessions or [],
        "mock_tests": [],  # empty on purpose -- reaching pack lookup means the
                            # free-trial/institution gate let the request through
        **(institution_fx or _no_institution()),
    }


def test_mock_free_institution_student_denied_before_pack_lookup(monkeypatch):
    tables = _mock_tables(_FREE_PROFILE, **_speaking_only_institution())
    supabase = FakeSupabase(tables)
    monkeypatch.setattr(mock, "get_supabase", lambda: supabase)
    with pytest.raises(HTTPException) as exc:
        _run(mock.start_mock(StartMockRequest(mock_test_id=1), SimpleNamespace(), _STUDENT))
    assert exc.value.status_code == 403
    assert "Elite" in exc.value.detail["error"]


def test_mock_normal_free_b2c_user_reaches_content_lookup(monkeypatch):
    """No prior mock, no institution -- the free lifetime attempt must still
    be granted, proven by getting past the gate to the (empty) pack lookup,
    which 404s rather than 403ing."""
    tables = _mock_tables(_FREE_PROFILE)
    supabase = FakeSupabase(tables)
    monkeypatch.setattr(mock, "get_supabase", lambda: supabase)
    with pytest.raises(HTTPException) as exc:
        _run(mock.start_mock(StartMockRequest(mock_test_id=1), SimpleNamespace(), _STUDENT))
    assert exc.value.status_code == 404


def test_mock_normal_free_b2c_user_second_attempt_denied(monkeypatch):
    prior = [{"id": 1, "user_id": "student-1", "status": "complete"}]
    tables = _mock_tables(_FREE_PROFILE, prior_sessions=prior)
    supabase = FakeSupabase(tables)
    monkeypatch.setattr(mock, "get_supabase", lambda: supabase)
    with pytest.raises(HTTPException) as exc:
        _run(mock.start_mock(StartMockRequest(mock_test_id=1), SimpleNamespace(), _STUDENT))
    assert exc.value.status_code == 403
    assert "already used" in exc.value.detail["error"]


def test_mock_revoked_membership_falls_back_to_normal_free_trial(monkeypatch):
    fx = _speaking_only_institution(member_status="revoked")
    tables = _mock_tables(_FREE_PROFILE, **fx)
    supabase = FakeSupabase(tables)
    monkeypatch.setattr(mock, "get_supabase", lambda: supabase)
    with pytest.raises(HTTPException) as exc:
        _run(mock.start_mock(StartMockRequest(mock_test_id=1), SimpleNamespace(), _STUDENT))
    assert exc.value.status_code == 404  # reached pack lookup -- free trial granted


def test_mock_institution_grant_bypasses_lifetime_attempt_cap(monkeypatch):
    """An institution that DOES enable mock_tests must not cap the student
    at one lifetime attempt like the generic B2C free-trial does."""
    fx = _speaking_only_institution()
    fx["institution_modules"].append({"institution_id": "inst-a", "module": "mock_tests", "enabled": True})
    prior = [{"id": 1, "user_id": "student-1", "status": "complete"}]
    tables = _mock_tables(_FREE_PROFILE, prior_sessions=prior, **fx)
    supabase = FakeSupabase(tables)
    monkeypatch.setattr(mock, "get_supabase", lambda: supabase)
    with pytest.raises(HTTPException) as exc:
        _run(mock.start_mock(StartMockRequest(mock_test_id=1), SimpleNamespace(), _STUDENT))
    assert exc.value.status_code == 404  # reached pack lookup, not the "already used" 403


def test_mock_paid_institution_member_unaffected(monkeypatch):
    fx = _speaking_only_institution()  # mock_tests not institution-enabled
    tables = _mock_tables({**_PRO_PROFILE, "plan": "elite", "plan_expires_at": "2099-01-01T00:00:00Z"}, **fx)
    supabase = FakeSupabase(tables)
    monkeypatch.setattr(mock, "get_supabase", lambda: supabase)
    with pytest.raises(HTTPException) as exc:
        _run(mock.start_mock(StartMockRequest(mock_test_id=1), SimpleNamespace(), _STUDENT))
    assert exc.value.status_code == 404  # Elite plan grants mock_tests on its own


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
