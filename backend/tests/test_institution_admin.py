"""
Tests for Phase 4 institution-admin authorization + routes: role-scoped
membership resolution, 403/409 fail-closed behavior, cross-tenant
ownership on revoke, and invite-role escalation (must always collapse to
student). Fake Supabase client (generic table/query chain), no network,
no live DB. See docs/superpowers/specs/2026-08-28-institution-phase4-admin.md
Section 9 for the scenario matrix this file implements.
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.services import institution_admin  # noqa: E402
from app.routers import institution as institution_module  # noqa: E402
from app.routers.auth import UserInfo  # noqa: E402


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _QueryBuilder:
    """Minimal generic table().select/insert/update().eq/in_().execute()
    chain over a mutable list of dict rows, shared across every fake table
    used in this file -- membership/institution/invite/profile/users
    tables all need the same eq/in_ filtering shape."""
    def __init__(self, rows, mode="select", payload=None, filters=None, order_by=None, limit_n=None):
        self.rows = rows
        self.mode = mode
        self.payload = payload
        self.filters = filters or []
        self.order_by = order_by
        self.limit_n = limit_n

    def select(self, _cols=None):
        return self

    def insert(self, row):
        return _QueryBuilder(self.rows, mode="insert", payload=row)

    def update(self, patch):
        return _QueryBuilder(self.rows, mode="update", payload=patch, filters=self.filters)

    def eq(self, col, val):
        return _QueryBuilder(self.rows, self.mode, self.payload, self.filters + [("eq", col, val)],
                              self.order_by, self.limit_n)

    def in_(self, col, vals):
        return _QueryBuilder(self.rows, self.mode, self.payload, self.filters + [("in", col, vals)],
                              self.order_by, self.limit_n)

    def order(self, col, desc=False):
        return _QueryBuilder(self.rows, self.mode, self.payload, self.filters, (col, desc), self.limit_n)

    def limit(self, n):
        return _QueryBuilder(self.rows, self.mode, self.payload, self.filters, self.order_by, n)

    def _matches(self, r):
        for kind, col, val in self.filters:
            if kind == "eq" and r.get(col) != val:
                return False
            if kind == "in" and r.get(col) not in val:
                return False
        return True

    def execute(self):
        if self.mode == "insert":
            new_row = dict(self.payload)
            new_row.setdefault("id", str(uuid.uuid4()))
            self.rows.append(new_row)
            return _FakeResult([new_row])
        if self.mode == "update":
            updated = []
            for r in self.rows:
                if self._matches(r):
                    r.update(self.payload)
                    updated.append(r)
            return _FakeResult(updated)
        result = [r for r in self.rows if self._matches(r)]
        if self.order_by:
            col, desc = self.order_by
            result = sorted(result, key=lambda r: r.get(col) or "", reverse=desc)
        if self.limit_n is not None:
            result = result[:self.limit_n]
        return _FakeResult(result)


class _FakeSupabase:
    def __init__(self, **tables):
        self.tables = {name: list(rows) for name, rows in tables.items()}

    def table(self, name):
        return _QueryBuilder(self.tables.setdefault(name, []))


def _user():
    return UserInfo(id=str(uuid.uuid4()), email="user@example.com")


def _membership(user_id, institution_id, role="student", status="active"):
    return {"user_id": user_id, "institution_id": institution_id, "role": role, "status": status}


def _institution(institution_id, status="active", **extra):
    row = {"id": institution_id, "name": "ABC Nursing Institute", "logo_url": None,
           "speaking_sessions_per_month": 20, "status": status}
    row.update(extra)
    return row


# ── require_active_institution_role: resolution + fail-closed ──────────

def test_no_membership_returns_403():
    fake = _FakeSupabase(institution_members=[], institutions=[])
    with pytest.raises(HTTPException) as excinfo:
        institution_admin.require_active_institution_role("teacher")(current_user=_user(), supabase=fake)
    assert excinfo.value.status_code == 403


def test_student_only_role_fails_teacher_minimum():
    user = _user()
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(
        institution_members=[_membership(user.id, inst_id, role="student")],
        institutions=[_institution(inst_id)],
    )
    with pytest.raises(HTTPException) as excinfo:
        institution_admin.require_active_institution_role("teacher")(current_user=user, supabase=fake)
    assert excinfo.value.status_code == 403


def test_teacher_role_satisfies_teacher_minimum():
    user = _user()
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(
        institution_members=[_membership(user.id, inst_id, role="teacher")],
        institutions=[_institution(inst_id)],
    )
    scope = institution_admin.require_active_institution_role("teacher")(current_user=user, supabase=fake)
    assert scope.institution_id == inst_id
    assert scope.role == "teacher"


def test_teacher_role_fails_institution_admin_minimum():
    user = _user()
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(
        institution_members=[_membership(user.id, inst_id, role="teacher")],
        institutions=[_institution(inst_id)],
    )
    with pytest.raises(HTTPException) as excinfo:
        institution_admin.require_active_institution_role("institution_admin")(current_user=user, supabase=fake)
    assert excinfo.value.status_code == 403


def test_admin_in_one_institution_student_in_another_resolves_to_admin_institution():
    user = _user()
    inst_a, inst_b = str(uuid.uuid4()), str(uuid.uuid4())
    fake = _FakeSupabase(
        institution_members=[
            _membership(user.id, inst_a, role="student"),
            _membership(user.id, inst_b, role="institution_admin"),
        ],
        institutions=[_institution(inst_a), _institution(inst_b)],
    )
    scope = institution_admin.require_active_institution_role("institution_admin")(current_user=user, supabase=fake)
    assert scope.institution_id == inst_b


def test_admin_rank_satisfies_teacher_minimum_in_same_institution():
    user = _user()
    inst_a, inst_b = str(uuid.uuid4()), str(uuid.uuid4())
    fake = _FakeSupabase(
        institution_members=[
            _membership(user.id, inst_a, role="student"),
            _membership(user.id, inst_b, role="institution_admin"),
        ],
        institutions=[_institution(inst_a), _institution(inst_b)],
    )
    scope = institution_admin.require_active_institution_role("teacher")(current_user=user, supabase=fake)
    assert scope.institution_id == inst_b


def test_admin_in_two_institutions_returns_409_with_both_candidates():
    user = _user()
    inst_a, inst_b = str(uuid.uuid4()), str(uuid.uuid4())
    fake = _FakeSupabase(
        institution_members=[
            _membership(user.id, inst_a, role="institution_admin"),
            _membership(user.id, inst_b, role="institution_admin"),
        ],
        institutions=[_institution(inst_a), _institution(inst_b)],
    )
    with pytest.raises(HTTPException) as excinfo:
        institution_admin.require_active_institution_role("institution_admin")(current_user=user, supabase=fake)
    assert excinfo.value.status_code == 409
    assert set(excinfo.value.detail["institutions"]) == {inst_a, inst_b}


def test_suspended_institution_yields_403():
    user = _user()
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(
        institution_members=[_membership(user.id, inst_id, role="institution_admin")],
        institutions=[_institution(inst_id, status="suspended")],
    )
    with pytest.raises(HTTPException) as excinfo:
        institution_admin.require_active_institution_role("institution_admin")(current_user=user, supabase=fake)
    assert excinfo.value.status_code == 403


def test_revoked_membership_yields_403():
    user = _user()
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(
        institution_members=[_membership(user.id, inst_id, role="institution_admin", status="revoked")],
        institutions=[_institution(inst_id)],
    )
    with pytest.raises(HTTPException) as excinfo:
        institution_admin.require_active_institution_role("institution_admin")(current_user=user, supabase=fake)
    assert excinfo.value.status_code == 403


def test_invited_not_active_membership_yields_403():
    user = _user()
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(
        institution_members=[_membership(user.id, inst_id, role="institution_admin", status="invited")],
        institutions=[_institution(inst_id)],
    )
    with pytest.raises(HTTPException) as excinfo:
        institution_admin.require_active_institution_role("institution_admin")(current_user=user, supabase=fake)
    assert excinfo.value.status_code == 403


# ── POST /institution/invites: role escalation must always fail ────────

def _admin_scope(inst_id):
    return institution_admin.InstitutionScope(institution_id=inst_id, role="institution_admin")


def test_invite_create_has_no_role_field_client_cannot_smuggle_a_role():
    for attempted_role in ("institution_admin", "teacher", "anything_else"):
        parsed = institution_module.InviteCreate.model_validate({
            "role": attempted_role, "max_uses": None, "expires_at": None,
        })
        assert not hasattr(parsed, "role")


def test_invite_create_has_no_institution_id_field_scope_is_server_derived():
    parsed = institution_module.InviteCreate.model_validate({
        "institution_id": str(uuid.uuid4()), "max_uses": None, "expires_at": None,
    })
    assert not hasattr(parsed, "institution_id")


def test_create_invite_always_writes_student_role_and_scoped_institution(monkeypatch):
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(institution_invites=[], audit_log=[])
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(institution_module, "_write_audit_log", lambda *a, **k: None)

    for attempted_role in ("institution_admin", "teacher", "anything_else", None):
        payload = {"max_uses": None, "expires_at": None}
        if attempted_role is not None:
            payload["role"] = attempted_role
        req = institution_module.InviteCreate.model_validate(payload)

        result = institution_module.create_institution_invite(
            req, scope=_admin_scope(inst_id), current_user=_user(),
        )

        created = fake.tables["institution_invites"][-1]
        assert created["role"] == "student"
        assert created["institution_id"] == inst_id
        assert result["role"] == "student"


def test_create_invite_ignores_injected_institution_id_in_body(monkeypatch):
    scoped_inst_id = str(uuid.uuid4())
    other_inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(institution_invites=[])
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(institution_module, "_write_audit_log", lambda *a, **k: None)

    req = institution_module.InviteCreate.model_validate({
        "institution_id": other_inst_id, "max_uses": None, "expires_at": None,
    })
    institution_module.create_institution_invite(req, scope=_admin_scope(scoped_inst_id), current_user=_user())

    created = fake.tables["institution_invites"][-1]
    assert created["institution_id"] == scoped_inst_id


def test_create_invite_created_by_matches_caller(monkeypatch):
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(institution_invites=[])
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(institution_module, "_write_audit_log", lambda *a, **k: None)
    caller = _user()

    institution_module.create_institution_invite(
        institution_module.InviteCreate.model_validate({"max_uses": None, "expires_at": None}),
        scope=_admin_scope(inst_id), current_user=caller,
    )

    created = fake.tables["institution_invites"][-1]
    assert created["created_by"] == caller.id


def test_create_invite_ignores_injected_created_by_in_body(monkeypatch):
    inst_id = str(uuid.uuid4())
    other_user_id = str(uuid.uuid4())
    fake = _FakeSupabase(institution_invites=[])
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(institution_module, "_write_audit_log", lambda *a, **k: None)
    caller = _user()

    req = institution_module.InviteCreate.model_validate({
        "created_by": other_user_id, "max_uses": None, "expires_at": None,
    })
    assert not hasattr(req, "created_by")
    institution_module.create_institution_invite(req, scope=_admin_scope(inst_id), current_user=caller)

    created = fake.tables["institution_invites"][-1]
    assert created["created_by"] == caller.id


# ── POST /institution/invites/{id}/revoke: cross-tenant ownership ──────

def test_revoke_cross_tenant_invite_returns_generic_404(monkeypatch):
    inst_a, inst_b = str(uuid.uuid4()), str(uuid.uuid4())
    invite_id = str(uuid.uuid4())
    fake = _FakeSupabase(institution_invites=[
        {"id": invite_id, "institution_id": inst_b, "status": "active"},
    ])
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(institution_module, "_write_audit_log", lambda *a, **k: None)

    with pytest.raises(HTTPException) as excinfo:
        institution_module.revoke_institution_invite(
            invite_id, scope=_admin_scope(inst_a), current_user=_user(),
        )
    assert excinfo.value.status_code == 404
    # Institution B's invite is untouched.
    assert fake.tables["institution_invites"][0]["status"] == "active"


def test_revoke_own_institution_invite_succeeds(monkeypatch):
    inst_id = str(uuid.uuid4())
    invite_id = str(uuid.uuid4())
    fake = _FakeSupabase(institution_invites=[
        {"id": invite_id, "institution_id": inst_id, "status": "active"},
    ])
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(institution_module, "_write_audit_log", lambda *a, **k: None)

    result = institution_module.revoke_institution_invite(
        invite_id, scope=_admin_scope(inst_id), current_user=_user(),
    )
    assert result == {"status": "revoked"}
    assert fake.tables["institution_invites"][0]["status"] == "revoked"


# ── GET /institution/overview: usage reconciliation (no writes) ────────

def test_overview_sums_usage_without_writing_and_ignores_stale_reset_date(monkeypatch):
    inst_id = str(uuid.uuid4())
    student_a, student_b = str(uuid.uuid4()), str(uuid.uuid4())
    fake = _FakeSupabase(
        institutions=[_institution(inst_id)],
        institution_members=[
            _membership(student_a, inst_id, role="student"),
            _membership(student_b, inst_id, role="student"),
        ],
        institution_modules=[{"institution_id": inst_id, "module": "speaking", "enabled": True}],
        user_profiles=[
            {"user_id": student_a, "plan": "free", "sessions_used_this_month": 5,
             "sessions_reset_date": institution_module.get_month_start_utc(), "bonus_sessions": 0},
            # Stale reset_date (last month) -- must report 0, and this GET must not write.
            {"user_id": student_b, "plan": "free", "sessions_used_this_month": 99,
             "sessions_reset_date": "2020-01-01T00:00:00+00:00", "bonus_sessions": 0},
        ],
    )
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)

    result = institution_module.get_institution_overview(scope=scope)

    assert result["sessions_used_this_month"] == 5
    # Read-only: the stale row must remain untouched in storage.
    stale_row = next(p for p in fake.tables["user_profiles"] if p["user_id"] == student_b)
    assert stale_row["sessions_used_this_month"] == 99
    assert stale_row["sessions_reset_date"] == "2020-01-01T00:00:00+00:00"


# ── GET /institution/students: roster scoped to caller's institution ───

def _invite_row(invite_id, inst_id, max_uses=None, use_count=0, status="active", **extra):
    row = {
        "id": invite_id, "institution_id": inst_id, "token": "raw-secret-token",
        "role": "student", "status": status, "max_uses": max_uses,
        "use_count": use_count, "expires_at": None, "created_at": "2026-08-28T00:00:00+00:00",
        "created_by": str(uuid.uuid4()),
    }
    row.update(extra)
    return row


# ── GET /institution/invites: no token/role/institution_id leak ────────

def test_list_invites_never_returns_token_role_or_institution_id(monkeypatch):
    inst_id = str(uuid.uuid4())
    invite_id = str(uuid.uuid4())
    fake = _FakeSupabase(institution_invites=[_invite_row(invite_id, inst_id, max_uses=3, use_count=2)])
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)

    result = institution_module.list_institution_invites(scope=_admin_scope(inst_id))

    assert len(result) == 1
    listed = result[0]
    for forbidden in ("token", "role", "institution_id", "created_by"):
        assert forbidden not in listed
    assert listed["id"] == invite_id
    assert listed["status"] == "active"
    assert listed["max_uses"] == 3
    assert listed["use_count"] == 2
    assert listed["remaining_uses"] == 1


def test_list_invites_remaining_uses_null_for_unlimited():
    inst_id = str(uuid.uuid4())
    listed = institution_module._invite_summary(
        _invite_row(str(uuid.uuid4()), inst_id, max_uses=None, use_count=5)
    )
    assert listed["remaining_uses"] is None


def test_list_invites_remaining_uses_never_negative():
    inst_id = str(uuid.uuid4())
    listed = institution_module._invite_summary(
        _invite_row(str(uuid.uuid4()), inst_id, max_uses=2, use_count=5)
    )
    assert listed["remaining_uses"] == 0


# ── POST /institution/invites: join_url + rate limit ────────────────────

def test_create_invite_returns_join_url_from_configured_frontend_url(monkeypatch):
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(institution_invites=[])
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(institution_module, "_write_audit_log", lambda *a, **k: None)
    monkeypatch.setattr(institution_module.settings, "FRONTEND_URL", "https://qa.speakoet.com")
    monkeypatch.setattr(institution_module.invite_create_rate_limiter, "is_rate_limited", lambda key: False)

    req = institution_module.InviteCreate.model_validate({"max_uses": None, "expires_at": None})
    result = institution_module.create_institution_invite(req, scope=_admin_scope(inst_id), current_user=_user())

    created = fake.tables["institution_invites"][-1]
    assert result["join_url"] == f"https://qa.speakoet.com/join/{created['token']}"
    assert result["token"] == created["token"]


def test_create_invite_rate_limited_returns_429(monkeypatch):
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(institution_invites=[])
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(institution_module.invite_create_rate_limiter, "is_rate_limited", lambda key: True)

    with pytest.raises(HTTPException) as excinfo:
        institution_module.create_institution_invite(
            institution_module.InviteCreate.model_validate({"max_uses": None, "expires_at": None}),
            scope=_admin_scope(inst_id), current_user=_user(),
        )
    assert excinfo.value.status_code == 429
    assert fake.tables["institution_invites"] == []  # never reached the insert


def test_create_invite_rate_limiter_keyed_by_current_user_id(monkeypatch):
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(institution_invites=[])
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(institution_module, "_write_audit_log", lambda *a, **k: None)
    seen_keys = []
    monkeypatch.setattr(
        institution_module.invite_create_rate_limiter, "is_rate_limited",
        lambda key: seen_keys.append(key) or False,
    )
    user = _user()

    institution_module.create_institution_invite(
        institution_module.InviteCreate.model_validate({"max_uses": None, "expires_at": None}),
        scope=_admin_scope(inst_id), current_user=user,
    )

    assert seen_keys == [user.id]


# ── POST /institution/invites/{id}/revoke: idempotent, doesn't touch member ─

def test_revoke_already_revoked_invite_is_idempotent(monkeypatch):
    inst_id = str(uuid.uuid4())
    invite_id = str(uuid.uuid4())
    fake = _FakeSupabase(institution_invites=[
        {"id": invite_id, "institution_id": inst_id, "status": "revoked"},
    ])
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(institution_module, "_write_audit_log", lambda *a, **k: None)

    result = institution_module.revoke_institution_invite(
        invite_id, scope=_admin_scope(inst_id), current_user=_user(),
    )
    assert result == {"status": "revoked"}
    assert fake.tables["institution_invites"][0]["status"] == "revoked"


def test_revoke_does_not_touch_institution_members(monkeypatch):
    """An already-joined student's membership must survive invite revocation
    -- revoke only ever writes institution_invites.status, never touches
    institution_members (spec Section 5)."""
    inst_id = str(uuid.uuid4())
    invite_id = str(uuid.uuid4())
    student_id = str(uuid.uuid4())
    fake = _FakeSupabase(
        institution_invites=[{"id": invite_id, "institution_id": inst_id, "status": "active"}],
        institution_members=[_membership(student_id, inst_id, role="student", status="active")],
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(institution_module, "_write_audit_log", lambda *a, **k: None)

    institution_module.revoke_institution_invite(invite_id, scope=_admin_scope(inst_id), current_user=_user())

    member = fake.tables["institution_members"][0]
    assert member["status"] == "active"


def test_invite_create_rate_limit_20_allowed_21st_blocked():
    """Exercises the real SlidingWindowRateLimiter (in-process fallback --
    no REDIS_URL in tests), not a mocked is_rate_limited, per spec Section 8."""
    key = str(uuid.uuid4())
    limiter = institution_module.invite_create_rate_limiter
    for _ in range(20):
        assert limiter.is_rate_limited(key) is False
    assert limiter.is_rate_limited(key) is True


def _students_fake(inst_id, members, *, users=None, profiles=None, submissions=None,
                    speaking_sessions_per_month=20, speaking_enabled=True):
    return _FakeSupabase(
        institution_members=members,
        institutions=[_institution(inst_id, speaking_sessions_per_month=speaking_sessions_per_month)],
        institution_modules=[{"institution_id": inst_id, "module": "speaking", "enabled": speaking_enabled}],
        users=users or [],
        user_profiles=profiles or [],
        submissions=submissions or [],
    )


def test_students_roster_lists_only_scoped_institution_students(monkeypatch):
    inst_a, inst_b = str(uuid.uuid4()), str(uuid.uuid4())
    student_a, teacher_a, student_b = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    fake = _students_fake(
        inst_a,
        members=[
            _membership(student_a, inst_a, role="student"),
            _membership(teacher_a, inst_a, role="teacher"),  # excluded: MVP is students-only
            _membership(student_b, inst_b, role="student"),  # excluded: other institution
        ],
        users=[{"id": student_a, "email": "student-a@example.com", "name": "Student A"}],
        profiles=[
            {"user_id": student_a, "plan": "free", "sessions_used_this_month": 3,
             "sessions_reset_date": institution_module.get_month_start_utc(), "bonus_sessions": 0},
        ],
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_a, role="teacher")

    roster = institution_module.get_institution_students(scope=scope)

    assert len(roster) == 1
    assert roster[0]["email"] == "student-a@example.com"
    assert roster[0]["sessions_used_this_month"] == 3


def test_students_roster_includes_user_id_but_not_other_internal_fields(monkeypatch):
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _students_fake(
        inst_id,
        members=[_membership(student, inst_id, role="student")],
        users=[{"id": student, "email": "s@example.com", "name": "S"}],
        profiles=[{"user_id": student, "plan": "pro", "sessions_used_this_month": 1,
                    "sessions_reset_date": institution_module.get_month_start_utc(),
                    "bonus_sessions": 2, "subscription_status": "active"}],
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")

    roster = institution_module.get_institution_students(scope=scope)

    assert roster[0]["user_id"] == student
    for forbidden in ("plan", "subscription_status", "bonus_sessions", "institution_id"):
        assert forbidden not in roster[0]


def test_students_roster_name_returned_when_present(monkeypatch):
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _students_fake(
        inst_id,
        members=[_membership(student, inst_id, role="student")],
        users=[{"id": student, "email": "s@example.com", "name": "Jamie Nurse"}],
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")

    roster = institution_module.get_institution_students(scope=scope)
    assert roster[0]["name"] == "Jamie Nurse"


def test_students_roster_name_falls_back_to_none_when_missing(monkeypatch):
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _students_fake(
        inst_id,
        members=[_membership(student, inst_id, role="student")],
        users=[{"id": student, "email": "s@example.com", "name": None}],
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")

    roster = institution_module.get_institution_students(scope=scope)
    assert roster[0]["name"] is None
    assert roster[0]["email"] == "s@example.com"


def test_students_roster_latest_speaking_score_picks_most_recent(monkeypatch):
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _students_fake(
        inst_id,
        members=[_membership(student, inst_id, role="student")],
        users=[{"id": student, "email": "s@example.com", "name": "S"}],
        submissions=[
            {"user_id": student, "score": 320, "created_at": "2026-08-01T00:00:00+00:00", "module": "speaking"},
            {"user_id": student, "score": 390, "created_at": "2026-08-20T00:00:00+00:00", "module": "speaking"},
            {"user_id": student, "score": 999, "created_at": "2026-08-10T00:00:00+00:00", "module": "reading"},
        ],
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")

    roster = institution_module.get_institution_students(scope=scope)
    assert roster[0]["latest_speaking_score"] == 390


def test_students_roster_no_submission_gives_null_score(monkeypatch):
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _students_fake(
        inst_id,
        members=[_membership(student, inst_id, role="student")],
        users=[{"id": student, "email": "s@example.com", "name": "S"}],
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")

    roster = institution_module.get_institution_students(scope=scope)
    assert roster[0]["latest_speaking_score"] is None


def test_students_roster_sessions_remaining_quota_minus_used(monkeypatch):
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _students_fake(
        inst_id,
        members=[_membership(student, inst_id, role="student")],
        users=[{"id": student, "email": "s@example.com", "name": "S"}],
        profiles=[{"user_id": student, "plan": "free", "sessions_used_this_month": 12,
                    "sessions_reset_date": institution_module.get_month_start_utc(), "bonus_sessions": 0}],
        speaking_sessions_per_month=20,
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")

    roster = institution_module.get_institution_students(scope=scope)
    assert roster[0]["sessions_used_this_month"] == 12
    assert roster[0]["sessions_remaining"] == 8


def test_students_roster_sessions_remaining_null_when_quota_unlimited(monkeypatch):
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _students_fake(
        inst_id,
        members=[_membership(student, inst_id, role="student")],
        users=[{"id": student, "email": "s@example.com", "name": "S"}],
        speaking_sessions_per_month=None,
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")

    roster = institution_module.get_institution_students(scope=scope)
    assert roster[0]["sessions_remaining"] is None


def test_students_roster_sessions_remaining_null_when_speaking_disabled(monkeypatch):
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _students_fake(
        inst_id,
        members=[_membership(student, inst_id, role="student")],
        users=[{"id": student, "email": "s@example.com", "name": "S"}],
        profiles=[{"user_id": student, "plan": "free", "sessions_used_this_month": 5,
                    "sessions_reset_date": institution_module.get_month_start_utc(), "bonus_sessions": 0}],
        speaking_enabled=False,
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")

    roster = institution_module.get_institution_students(scope=scope)
    assert roster[0]["sessions_remaining"] is None


def test_students_roster_sessions_remaining_clamped_at_zero(monkeypatch):
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _students_fake(
        inst_id,
        members=[_membership(student, inst_id, role="student")],
        users=[{"id": student, "email": "s@example.com", "name": "S"}],
        profiles=[{"user_id": student, "plan": "free", "sessions_used_this_month": 25,
                    "sessions_reset_date": institution_module.get_month_start_utc(), "bonus_sessions": 0}],
        speaking_sessions_per_month=20,
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")

    roster = institution_module.get_institution_students(scope=scope)
    assert roster[0]["sessions_remaining"] == 0


def test_students_roster_ordered_joined_at_desc(monkeypatch):
    inst_id = str(uuid.uuid4())
    older, newer = str(uuid.uuid4()), str(uuid.uuid4())
    fake = _students_fake(
        inst_id,
        members=[
            {**_membership(older, inst_id, role="student"), "joined_at": "2026-01-01T00:00:00+00:00"},
            {**_membership(newer, inst_id, role="student"), "joined_at": "2026-08-01T00:00:00+00:00"},
        ],
        users=[
            {"id": older, "email": "older@example.com", "name": "Older"},
            {"id": newer, "email": "newer@example.com", "name": "Newer"},
        ],
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")

    roster = institution_module.get_institution_students(scope=scope)
    assert [r["email"] for r in roster] == ["newer@example.com", "older@example.com"]


def test_students_roster_returns_last_seen_at(monkeypatch):
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _students_fake(
        inst_id,
        members=[_membership(student, inst_id, role="student")],
        users=[{"id": student, "email": "s@example.com", "name": "S", "last_seen_at": "2026-08-30T00:00:00+00:00"}],
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")

    roster = institution_module.get_institution_students(scope=scope)
    assert roster[0]["last_seen_at"] == "2026-08-30T00:00:00+00:00"


# ── GET /institution/students/{user_id}: single-student detail ─────────

def _detail_fake(inst_id, members, *, users=None, profiles=None, submissions=None,
                  speaking_sessions_per_month=20, speaking_enabled=True):
    return _students_fake(
        inst_id, members, users=users, profiles=profiles, submissions=submissions,
        speaking_sessions_per_month=speaking_sessions_per_month, speaking_enabled=speaking_enabled,
    )


def test_student_detail_happy_path(monkeypatch):
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _detail_fake(
        inst_id,
        members=[{**_membership(student, inst_id, role="student"), "joined_at": "2026-08-01T00:00:00+00:00"}],
        users=[{"id": student, "email": "s@example.com", "name": "S", "last_seen_at": "2026-09-01T00:00:00+00:00"}],
        profiles=[{"user_id": student, "plan": "free", "sessions_used_this_month": 4,
                    "sessions_reset_date": institution_module.get_month_start_utc(), "bonus_sessions": 0}],
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")

    detail = institution_module.get_institution_student_detail(student, scope=scope)

    assert detail["user_id"] == student
    assert detail["email"] == "s@example.com"
    assert detail["status"] == "active"
    assert detail["role"] == "student"
    assert detail["joined_at"] == "2026-08-01T00:00:00+00:00"
    assert detail["sessions_used_this_month"] == 4
    assert detail["last_seen_at"] == "2026-09-01T00:00:00+00:00"


def test_student_detail_institution_admin_access(monkeypatch):
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _detail_fake(
        inst_id,
        members=[_membership(student, inst_id, role="student")],
        users=[{"id": student, "email": "s@example.com", "name": "S"}],
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="institution_admin")

    detail = institution_module.get_institution_student_detail(student, scope=scope)
    assert detail["user_id"] == student


def test_student_detail_teacher_access_matches_roster_permission(monkeypatch):
    """require_teacher is the same dependency used by the roster -- a caller
    with only teacher rank (not institution_admin) must be able to load the
    detail view, exactly like the roster."""
    user = _user()
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(
        institution_members=[_membership(user.id, inst_id, role="teacher")],
        institutions=[_institution(inst_id)],
    )
    scope = institution_admin.require_active_institution_role("teacher")(current_user=user, supabase=fake)
    assert scope.role == "teacher"


def test_student_detail_cross_institution_student_returns_404(monkeypatch):
    inst_a, inst_b = str(uuid.uuid4()), str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _detail_fake(
        inst_a,
        members=[_membership(student, inst_b, role="student")],  # student belongs to inst_b, not inst_a
        users=[{"id": student, "email": "other@example.com", "name": "Other"}],
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_a, role="teacher")

    with pytest.raises(HTTPException) as excinfo:
        institution_module.get_institution_student_detail(student, scope=scope)
    assert excinfo.value.status_code == 404


def test_student_detail_revoked_target_membership_still_returned_with_status(monkeypatch):
    """Matches roster behavior: the roster already lists every membership
    status (including revoked), so detail must not silently deny access to
    an existing membership row -- it reports the true status instead."""
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _detail_fake(
        inst_id,
        members=[_membership(student, inst_id, role="student", status="revoked")],
        users=[{"id": student, "email": "s@example.com", "name": "S"}],
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")

    detail = institution_module.get_institution_student_detail(student, scope=scope)
    assert detail["status"] == "revoked"


def test_student_detail_caller_revoked_membership_denied_at_dependency(monkeypatch):
    user = _user()
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(
        institution_members=[_membership(user.id, inst_id, role="teacher", status="revoked")],
        institutions=[_institution(inst_id)],
    )
    with pytest.raises(HTTPException) as excinfo:
        institution_admin.require_active_institution_role("teacher")(current_user=user, supabase=fake)
    assert excinfo.value.status_code == 403


def test_student_detail_nonexistent_user_returns_404(monkeypatch):
    inst_id = str(uuid.uuid4())
    fake = _detail_fake(inst_id, members=[])
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")

    with pytest.raises(HTTPException) as excinfo:
        institution_module.get_institution_student_detail(str(uuid.uuid4()), scope=scope)
    assert excinfo.value.status_code == 404


def test_student_detail_quota_positive_number(monkeypatch):
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _detail_fake(
        inst_id,
        members=[_membership(student, inst_id, role="student")],
        users=[{"id": student, "email": "s@example.com", "name": "S"}],
        profiles=[{"user_id": student, "plan": "free", "sessions_used_this_month": 12,
                    "sessions_reset_date": institution_module.get_month_start_utc(), "bonus_sessions": 0}],
        speaking_sessions_per_month=20,
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")

    detail = institution_module.get_institution_student_detail(student, scope=scope)
    assert detail["speaking_sessions_per_month"] == 20
    assert detail["sessions_remaining"] == 8


def test_student_detail_quota_unlimited_gives_null_remaining(monkeypatch):
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _detail_fake(
        inst_id,
        members=[_membership(student, inst_id, role="student")],
        users=[{"id": student, "email": "s@example.com", "name": "S"}],
        speaking_sessions_per_month=None,
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")

    detail = institution_module.get_institution_student_detail(student, scope=scope)
    assert detail["speaking_sessions_per_month"] is None
    assert detail["sessions_remaining"] is None


def test_student_detail_sessions_remaining_never_negative(monkeypatch):
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _detail_fake(
        inst_id,
        members=[_membership(student, inst_id, role="student")],
        users=[{"id": student, "email": "s@example.com", "name": "S"}],
        profiles=[{"user_id": student, "plan": "free", "sessions_used_this_month": 99,
                    "sessions_reset_date": institution_module.get_month_start_utc(), "bonus_sessions": 0}],
        speaking_sessions_per_month=20,
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")

    detail = institution_module.get_institution_student_detail(student, scope=scope)
    assert detail["sessions_remaining"] == 0


def test_student_detail_last_seen_at_returned(monkeypatch):
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _detail_fake(
        inst_id,
        members=[_membership(student, inst_id, role="student")],
        users=[{"id": student, "email": "s@example.com", "name": "S", "last_seen_at": "2026-09-04T12:00:00+00:00"}],
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")

    detail = institution_module.get_institution_student_detail(student, scope=scope)
    assert detail["last_seen_at"] == "2026-09-04T12:00:00+00:00"


def test_student_detail_latest_speaking_score_returned(monkeypatch):
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _detail_fake(
        inst_id,
        members=[_membership(student, inst_id, role="student")],
        users=[{"id": student, "email": "s@example.com", "name": "S"}],
        submissions=[
            {"user_id": student, "score": 320, "created_at": "2026-08-01T00:00:00+00:00", "module": "speaking"},
            {"user_id": student, "score": 390, "created_at": "2026-08-20T00:00:00+00:00", "module": "speaking"},
        ],
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")

    detail = institution_module.get_institution_student_detail(student, scope=scope)
    assert detail["latest_speaking_score"] == 390


def test_student_detail_recent_submissions_bounded_and_newest_first(monkeypatch):
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    submissions = [
        {"id": i, "user_id": student, "module": "speaking", "score": i,
         "created_at": f"2026-08-{i:02d}T00:00:00+00:00"}
        for i in range(1, 13)  # 12 submissions -- must be capped at 10
    ]
    fake = _detail_fake(
        inst_id,
        members=[_membership(student, inst_id, role="student")],
        users=[{"id": student, "email": "s@example.com", "name": "S"}],
        submissions=submissions,
    )
    monkeypatch.setattr(institution_module, "get_supabase", lambda: fake)
    scope = institution_admin.InstitutionScope(institution_id=inst_id, role="teacher")

    detail = institution_module.get_institution_student_detail(student, scope=scope)
    recent = detail["recent_submissions"]
    assert len(recent) == 10
    assert [r["id"] for r in recent] == [12, 11, 10, 9, 8, 7, 6, 5, 4, 3]
    # The fake query builder's select() doesn't project columns (unlike the
    # real client, which only returns "id, module, score, created_at") --
    # assert the needed fields are present rather than an exact key set.
    assert {"id", "module", "score", "created_at"} <= set(recent[0].keys())
