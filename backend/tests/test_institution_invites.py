"""
Tests for the Phase 2 institution invite endpoints: public token-gated
preview, authenticated accept. Fake Supabase client (table/rpc chain), same
style as test_subscription_lifecycle.py -- no network, no live DB.

Staff-only invite *creation* used to live in this router too
(POST /institutions/invites) and was covered here, but that endpoint was
removed 2026-09-06 as a dead duplicate of institution.py's
_create_invite_row-based creation (see institutions.py's removal note) --
its coverage now lives in test_institution_invites.py's sibling suites for
institution.py/admin_institutions.py, not here.
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402
from app.routers import institutions as institutions_module  # noqa: E402
from app.routers.auth import UserInfo  # noqa: E402


class _FakeResult:
    def __init__(self, data):
        self.data = data


from fastapi import Request  # noqa: E402


class _FakeSelectQuery:
    def __init__(self, rows, selected_cols_log, filters=None):
        self.rows = rows
        self.selected_cols_log = selected_cols_log  # shared list, records every .select() call
        self.filters = filters or {}

    def select(self, cols):
        self.selected_cols_log.append(cols)
        return self

    def eq(self, col, val):
        f = dict(self.filters)
        f[col] = val
        return _FakeSelectQuery(self.rows, self.selected_cols_log, f)

    def execute(self):
        out = [r for r in self.rows if all(r.get(k) == v for k, v in self.filters.items())]
        return _FakeResult(out)


class _FakePreviewSupabase:
    def __init__(self, invite_rows, institution_rows, module_rows):
        self.invite_rows = invite_rows
        self.institution_rows = institution_rows
        self.module_rows = module_rows
        # one shared log per table so a test can assert exactly which
        # columns the preview endpoint asked for from each table
        self.invite_selects = []
        self.institution_selects = []
        self.module_selects = []

    def table(self, name):
        if name == "institution_invites":
            return _FakeSelectQuery(self.invite_rows, self.invite_selects)
        if name == "institutions":
            return _FakeSelectQuery(self.institution_rows, self.institution_selects)
        if name == "institution_modules":
            return _FakeSelectQuery(self.module_rows, self.module_selects)
        raise AssertionError(f"unexpected table {name}")


def _valid_invite_fixture():
    institution_id = str(uuid.uuid4())
    invite = {
        "id": str(uuid.uuid4()),
        "institution_id": institution_id,
        "token": "abc123",
        "status": "active",
        "expires_at": None,
        "max_uses": None,
        "use_count": 0,
    }
    institution = {
        "id": institution_id, "name": "ABC Nursing Institute",
        "logo_url": "https://cdn/logo.png", "status": "active",
    }
    modules = [{"institution_id": institution_id, "module": "speaking", "enabled": True}]
    return invite, institution, modules


def test_preview_returns_allowlisted_fields_only(monkeypatch):
    invite, institution, modules = _valid_invite_fixture()
    fake = _FakePreviewSupabase([invite], [institution], modules)
    monkeypatch.setattr(institutions_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(
        institutions_module.preview_rate_limiter, "is_rate_limited", lambda key: False
    )

    result = institutions_module.get_invite_preview(token="abc123", request=_FakeRequest())

    assert result == {
        "institution_name": "ABC Nursing Institute",
        "logo_url": "https://cdn/logo.png",
        "modules": ["speaking"],
        "expires_at": None,
    }


def test_preview_queries_are_intentionally_minimal(monkeypatch):
    # Query-layer data minimization (spec §5.2), independent of the
    # already-allow-listed response: the preview endpoint must not fetch
    # whole rows with select("*"). Assert the forbidden columns never
    # appear in what was actually requested from each table.
    invite, institution, modules = _valid_invite_fixture()
    fake = _FakePreviewSupabase([invite], [institution], modules)
    monkeypatch.setattr(institutions_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(
        institutions_module.preview_rate_limiter, "is_rate_limited", lambda key: False
    )

    institutions_module.get_invite_preview(token="abc123", request=_FakeRequest())

    assert fake.invite_selects and "*" not in fake.invite_selects
    for cols in fake.invite_selects:
        for forbidden in ("id", "token", "role", "created_by", "created_at"):
            assert forbidden not in cols.replace(" ", "").split(",")

    assert fake.institution_selects and "*" not in fake.institution_selects
    for cols in fake.institution_selects:
        for forbidden in ("contact_email", "speaking_sessions_per_month", "created_at", "id"):
            assert forbidden not in cols.replace(" ", "").split(",")

    assert fake.module_selects and "*" not in fake.module_selects
    for cols in fake.module_selects:
        assert cols.replace(" ", "").split(",") == ["module"]


def test_preview_rejects_unknown_token_with_generic_404(monkeypatch):
    fake = _FakePreviewSupabase([], [], [])
    monkeypatch.setattr(institutions_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(
        institutions_module.preview_rate_limiter, "is_rate_limited", lambda key: False
    )

    with __import__("pytest").raises(HTTPException) as excinfo:
        institutions_module.get_invite_preview(token="does-not-exist", request=_FakeRequest())
    assert excinfo.value.status_code == 404


class _FakeRequest:
    client = type("C", (), {"host": "127.0.0.1"})()
    headers = {}


class _FakeRpcResult:
    def __init__(self, data):
        self.data = data


class _FakeRpcCall:
    def __init__(self, recorder, name, params, response_row):
        self.recorder = recorder
        self.name = name
        self.params = params
        self.response_row = response_row

    def execute(self):
        self.recorder.append((self.name, self.params))
        return _FakeRpcResult([self.response_row] if self.response_row else [])


class _FakeAcceptSupabase:
    def __init__(self, response_row):
        self.response_row = response_row
        self.rpc_calls = []

    def rpc(self, name, params):
        return _FakeRpcCall(self.rpc_calls, name, params, self.response_row)


def _student_user():
    return UserInfo(id=str(uuid.uuid4()), email="student@example.com")


def _anonymous_user():
    return UserInfo(id=str(uuid.uuid4()), email=None, is_anonymous=True)


def test_accept_rejects_anonymous_session_with_401_and_never_calls_rpc(monkeypatch):
    # Authorization requirement (spec §5.3), not a frontend-only UX rule --
    # an anonymous/guest Supabase session still passes get_current_user
    # (it's a valid JWT), so this must be an explicit is_anonymous check.
    fake = _FakeAcceptSupabase({
        "result_status": "joined", "institution_id": str(uuid.uuid4()),
        "institution_name": "ABC Nursing Institute", "modules": ["speaking"],
    })
    monkeypatch.setattr(institutions_module, "get_supabase", lambda: fake)

    with __import__("pytest").raises(HTTPException) as excinfo:
        institutions_module.accept_institution_invite_endpoint(
            token="abc123", current_user=_anonymous_user()
        )
    assert excinfo.value.status_code == 401
    assert fake.rpc_calls == []  # RPC must never be reached for an anonymous session


def test_accept_success_calls_rpc_with_token_and_verified_user_id(monkeypatch):
    user = _student_user()
    fake = _FakeAcceptSupabase({
        "result_status": "joined", "institution_id": str(uuid.uuid4()),
        "institution_name": "ABC Nursing Institute", "modules": ["speaking"],
    })
    monkeypatch.setattr(institutions_module, "get_supabase", lambda: fake)

    result = institutions_module.accept_institution_invite_endpoint(
        token="abc123", current_user=user
    )

    assert fake.rpc_calls == [("accept_institution_invite", {"p_token": "abc123", "p_user_id": user.id})]
    assert result == {
        "status": "joined",
        "institution_name": "ABC Nursing Institute",
        "modules": ["speaking"],
    }


def test_accept_rejects_invalid_invite_with_generic_400(monkeypatch):
    fake = _FakeAcceptSupabase({
        "result_status": "invalid", "institution_id": None,
        "institution_name": None, "modules": None,
    })
    monkeypatch.setattr(institutions_module, "get_supabase", lambda: fake)

    with __import__("pytest").raises(HTTPException) as excinfo:
        institutions_module.accept_institution_invite_endpoint(
            token="bad-token", current_user=_student_user()
        )
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "This invitation cannot be used"


def test_accept_rejects_exhausted_invite(monkeypatch):
    fake = _FakeAcceptSupabase({
        "result_status": "exhausted", "institution_id": None,
        "institution_name": None, "modules": None,
    })
    monkeypatch.setattr(institutions_module, "get_supabase", lambda: fake)

    with __import__("pytest").raises(HTTPException) as excinfo:
        institutions_module.accept_institution_invite_endpoint(
            token="full-token", current_user=_student_user()
        )
    assert excinfo.value.status_code == 400
