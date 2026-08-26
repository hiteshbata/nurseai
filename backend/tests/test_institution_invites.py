"""
Tests for the Phase 2 institution invite endpoints: staff-only creation,
public token-gated preview, authenticated accept. Fake Supabase client
(table/rpc chain), same style as test_subscription_lifecycle.py -- no
network, no live DB.
"""
import sys
import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402
from app.routers import institutions as institutions_module  # noqa: E402
from app.routers.auth import UserInfo  # noqa: E402


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeInsertTable:
    def __init__(self, recorder, returned_row):
        self.recorder = recorder
        self.returned_row = returned_row

    def insert(self, row):
        self.recorder.append(row)
        return self

    def execute(self):
        return _FakeResult([self.returned_row])


class _FakeInstitutionLookup:
    """Minimal select().eq(...).eq(...).execute() chain for the institution
    existence/active check the create endpoint runs before inserting."""
    def __init__(self, rows, filters=None):
        self.rows = rows
        self.filters = filters or {}

    def select(self, _cols):
        return self

    def eq(self, col, val):
        f = dict(self.filters)
        f[col] = val
        return _FakeInstitutionLookup(self.rows, f)

    def execute(self):
        out = [r for r in self.rows if all(r.get(k) == v for k, v in self.filters.items())]
        return _FakeResult(out)


class _FakeSupabase:
    def __init__(self, returned_row, institution_rows=None):
        self.inserted = []
        self._returned_row = returned_row
        self._institution_rows = institution_rows if institution_rows is not None else []

    def table(self, name):
        if name == "institution_invites":
            return _FakeInsertTable(self.inserted, self._returned_row)
        if name == "institutions":
            return _FakeInstitutionLookup(self._institution_rows)
        raise AssertionError(f"unexpected table {name}")


def _admin_user():
    return UserInfo(id=str(uuid.uuid4()), email="staff@speakoet.com")


def _active_institution_row(institution_id):
    return {"id": institution_id, "status": "active"}


def test_create_invite_generates_urlsafe_token_and_hardcodes_student_role(monkeypatch):
    institution_id = str(uuid.uuid4())
    returned_row = {
        "id": str(uuid.uuid4()),
        "token": "placeholder-will-be-overwritten-by-fake",
        "expires_at": None,
        "max_uses": None,
    }
    fake_supabase = _FakeSupabase(returned_row, institution_rows=[_active_institution_row(institution_id)])
    monkeypatch.setattr(institutions_module, "get_supabase", lambda: fake_supabase)
    monkeypatch.setattr(institutions_module, "_write_audit_log", lambda *a, **k: None)

    req = institutions_module.InviteCreate(institution_id=institution_id, max_uses=None, expires_at=None)
    result = institutions_module.create_institution_invite(req, current_user=_admin_user())

    assert len(fake_supabase.inserted) == 1
    inserted = fake_supabase.inserted[0]
    assert inserted["institution_id"] == institution_id
    assert inserted["role"] == "student"
    assert inserted["max_uses"] is None
    assert len(inserted["token"]) > 20  # secrets.token_urlsafe(24) output length
    assert "token" in result


def test_invite_create_has_no_role_field_client_cannot_smuggle_a_role(monkeypatch):
    # InviteCreate declares no `role` field -- a client-supplied role in the
    # raw JSON body is silently dropped by pydantic (default: ignore unknown
    # fields), so it never becomes an attribute on the parsed request.
    for attempted_role in ("institution_admin", "teacher", "anything_else"):
        parsed = institutions_module.InviteCreate.model_validate({
            "institution_id": str(uuid.uuid4()),
            "role": attempted_role,
            "max_uses": None,
            "expires_at": None,
        })
        assert not hasattr(parsed, "role")


def test_create_invite_always_writes_student_role_regardless_of_attempted_role(monkeypatch):
    institution_id = str(uuid.uuid4())
    returned_row = {"id": str(uuid.uuid4()), "token": "x", "expires_at": None, "max_uses": None}
    for attempted_role in ("institution_admin", "teacher", "anything_else"):
        fake_supabase = _FakeSupabase(returned_row, institution_rows=[_active_institution_row(institution_id)])
        monkeypatch.setattr(institutions_module, "get_supabase", lambda fs=fake_supabase: fs)
        monkeypatch.setattr(institutions_module, "_write_audit_log", lambda *a, **k: None)

        parsed = institutions_module.InviteCreate.model_validate({
            "institution_id": institution_id, "role": attempted_role,
            "max_uses": None, "expires_at": None,
        })
        institutions_module.create_institution_invite(parsed, current_user=_admin_user())

        assert fake_supabase.inserted[0]["role"] == "student"


def test_create_invite_rejects_missing_institution(monkeypatch):
    fake_supabase = _FakeSupabase({"id": "x", "token": "x"}, institution_rows=[])
    monkeypatch.setattr(institutions_module, "get_supabase", lambda: fake_supabase)

    req = institutions_module.InviteCreate(institution_id=str(uuid.uuid4()), max_uses=None, expires_at=None)
    with __import__("pytest").raises(HTTPException) as excinfo:
        institutions_module.create_institution_invite(req, current_user=_admin_user())
    assert excinfo.value.status_code == 404


def test_create_invite_rejects_suspended_institution(monkeypatch):
    institution_id = str(uuid.uuid4())
    fake_supabase = _FakeSupabase(
        {"id": "x", "token": "x"},
        institution_rows=[{"id": institution_id, "status": "suspended"}],
    )
    monkeypatch.setattr(institutions_module, "get_supabase", lambda: fake_supabase)

    req = institutions_module.InviteCreate(institution_id=institution_id, max_uses=None, expires_at=None)
    with __import__("pytest").raises(HTTPException) as excinfo:
        institutions_module.create_institution_invite(req, current_user=_admin_user())
    assert excinfo.value.status_code == 400


def test_invite_create_rejects_zero_and_negative_max_uses(monkeypatch):
    # max_uses/expires_at shape checks live in InviteCreate's pydantic
    # field_validators (Task 2 Step 3) -- they run at request-parsing time,
    # before the endpoint body ever executes, and FastAPI turns a raised
    # ValidationError into an HTTP 422 automatically (standard framework
    # behavior, not something this endpoint needs to reimplement). These
    # unit tests call the model directly, same as every other test in this
    # file, so they assert ValidationError rather than going through
    # FastAPI's HTTP layer.
    from pydantic import ValidationError
    institution_id = str(uuid.uuid4())
    for bad_value in (0, -1):
        try:
            institutions_module.InviteCreate(institution_id=institution_id, max_uses=bad_value, expires_at=None)
            assert False, f"expected ValidationError for max_uses={bad_value}"
        except ValidationError:
            pass


def test_invite_create_rejects_already_expired_expires_at(monkeypatch):
    from pydantic import ValidationError
    institution_id = str(uuid.uuid4())
    try:
        institutions_module.InviteCreate(
            institution_id=institution_id, max_uses=None,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        assert False, "expected ValidationError for an already-expired expires_at"
    except ValidationError:
        pass
