"""Tests for Phase 5.1/5.2: backend/app/routers/admin_institutions.py
(internal staff institution management -- read paths + create/configure).
Fake Supabase client (generic table/query/rpc chain, same shape as
test_institution_admin.py), no network, no live DB. See
docs/PHASE5_INSTITUTION_ADMIN_SPEC.md Section 12 for the scenario matrix
this file implements.
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from fastapi import HTTPException, Response  # noqa: E402

from app.routers import admin as admin_module  # noqa: E402
from app.routers import admin_institutions as ai_module  # noqa: E402
from app.routers import institution as institution_module  # noqa: E402
from app.routers.auth import UserInfo  # noqa: E402

MODULE_VALUES = ai_module.MODULE_VALUES


class _FakeResult:
    def __init__(self, data):
        self.data = data


_UNIQUE_COLUMNS = {"institutions": "slug"}


def _raise_duplicate_key(table_name, col):
    raise Exception(
        f'duplicate key value violates unique constraint "{table_name}_{col}_key"'
    )


class _QueryBuilder:
    """Generic table().select()/insert()/update()/upsert()/eq()/in_()/
    order().execute() chain over a mutable list of dict rows -- same shape
    reused across every fake table in this file. insert()/update() simulate
    the institutions.slug UNIQUE constraint (the only one Phase 5.2 code
    needs to react to) by raising a "duplicate key" Exception, matching the
    real Postgres/postgrest-py error shape the endpoint code already greps
    for (same convention as reading.py's create_test)."""
    def __init__(self, table_name, rows, mode="select", payload=None, filters=None, order_by=None, order_desc=False):
        self.table_name = table_name
        self.rows = rows
        self.mode = mode
        self.payload = payload
        self.filters = filters or []
        self.order_by = order_by
        self.order_desc = order_desc

    def select(self, _cols=None):
        return self

    def insert(self, row):
        return _QueryBuilder(self.table_name, self.rows, mode="insert", payload=row)

    def update(self, patch):
        return _QueryBuilder(self.table_name, self.rows, mode="update", payload=patch, filters=self.filters)

    def upsert(self, row, on_conflict=None):
        return _QueryBuilder(self.table_name, self.rows, mode="upsert", payload=(row, on_conflict))

    def eq(self, col, val):
        return _QueryBuilder(self.table_name, self.rows, self.mode, self.payload,
                              self.filters + [("eq", col, val)], self.order_by, self.order_desc)

    def in_(self, col, vals):
        return _QueryBuilder(self.table_name, self.rows, self.mode, self.payload,
                              self.filters + [("in", col, vals)], self.order_by, self.order_desc)

    def order(self, col, desc=False):
        return _QueryBuilder(self.table_name, self.rows, self.mode, self.payload, self.filters, col, desc)

    def _matches(self, r):
        for kind, col, val in self.filters:
            if kind == "eq" and r.get(col) != val:
                return False
            if kind == "in" and r.get(col) not in val:
                return False
        return True

    def execute(self):
        unique_col = _UNIQUE_COLUMNS.get(self.table_name)

        if self.mode == "insert":
            new_row = dict(self.payload)
            new_row.setdefault("id", str(uuid.uuid4()))
            new_row.setdefault("created_at", "2026-08-29T00:00:00+00:00")
            if unique_col and any(r.get(unique_col) == new_row.get(unique_col) for r in self.rows):
                _raise_duplicate_key(self.table_name, unique_col)
            self.rows.append(new_row)
            return _FakeResult([new_row])

        if self.mode == "update":
            matched = [r for r in self.rows if self._matches(r)]
            if unique_col and unique_col in self.payload:
                for r in self.rows:
                    if r not in matched and r.get(unique_col) == self.payload[unique_col]:
                        _raise_duplicate_key(self.table_name, unique_col)
            for r in matched:
                r.update(self.payload)
            return _FakeResult(matched)

        if self.mode == "upsert":
            row, on_conflict = self.payload
            keys = on_conflict.split(",") if on_conflict else list(row.keys())
            for r in self.rows:
                if all(r.get(k) == row.get(k) for k in keys):
                    r.update(row)
                    return _FakeResult([r])
            new_row = dict(row)
            self.rows.append(new_row)
            return _FakeResult([new_row])

        # Copies, not live references -- a real SELECT round-trip returns an
        # independent JSON payload, so a snapshot taken here (e.g. the
        # "before" row in update_institution) must not silently change if a
        # later insert()/update() call mutates the underlying fake table.
        rows = [dict(r) for r in self.rows if self._matches(r)]
        if self.order_by:
            rows = sorted(rows, key=lambda r: r.get(self.order_by) or "", reverse=self.order_desc)
        return _FakeResult(rows)


class _FakeRpc:
    """Simulates admin_create_institution's single-transaction contract:
    the institutions insert and every institution_modules insert either all
    land or none do. A real Postgres function gets this for free (one RPC
    call is one statement is one transaction, see the migration's comment);
    this fake reproduces the same all-or-nothing behavior by snapshotting
    and rolling back in Python, so a test can verify the contract without a
    live DB."""
    def __init__(self, supabase, name, params):
        self.supabase = supabase
        self.name = name
        self.params = params

    def execute(self):
        assert self.name == "admin_create_institution", f"unexpected rpc {self.name}"
        p = self.params
        institutions = self.supabase.tables.setdefault("institutions", [])
        modules = self.supabase.tables.setdefault("institution_modules", [])

        if any(r.get("slug") == p["p_slug"] for r in institutions):
            _raise_duplicate_key("institutions", "slug")

        new_id = str(uuid.uuid4())
        created_at = "2026-08-29T00:00:00+00:00"
        modules_snapshot = list(modules)
        institutions.append({
            "id": new_id, "name": p["p_name"], "slug": p["p_slug"], "logo_url": p["p_logo_url"],
            "contact_email": p["p_contact_email"], "status": p["p_status"],
            "speaking_sessions_per_month": p["p_quota"], "created_at": created_at,
        })
        try:
            for module in p["p_modules"]:
                if module not in MODULE_VALUES:
                    raise Exception(
                        'new row for relation "institution_modules" violates check '
                        'constraint "institution_modules_module_check"'
                    )
                modules.append({"institution_id": new_id, "module": module, "enabled": True})
        except Exception:
            institutions[:] = [r for r in institutions if r["id"] != new_id]
            modules[:] = modules_snapshot
            raise

        return _FakeResult([{"id": new_id, "created_at": created_at}])


class _FakeSupabase:
    def __init__(self, **tables):
        self.tables = {name: list(rows) for name, rows in tables.items()}

    def table(self, name):
        return _QueryBuilder(name, self.tables.setdefault(name, []))

    def rpc(self, name, params):
        return _FakeRpc(self, name, params)


def _user():
    return UserInfo(id=str(uuid.uuid4()), email="staff@example.com")


def _record_audit_log(monkeypatch, calls):
    """Records real (action, target_id, target_label, detail) calls instead
    of stubbing _write_audit_log away -- Phase 5.2's audit coverage (case 13)
    needs to assert these actually fire, unlike the read-only Phase 5.1
    tests above which never mutate anything."""
    def _fake(supabase, admin, action, target_type, target_id=None, target_label=None, detail=None):
        calls.append({"action": action, "target_type": target_type, "target_id": target_id,
                       "target_label": target_label, "detail": detail})
    monkeypatch.setattr(ai_module, "_write_audit_log", _fake)


def _institution(institution_id, status="active", **extra):
    row = {
        "id": institution_id, "name": "ABC Nursing Institute", "slug": "abc-nursing",
        "logo_url": None, "status": status, "contact_email": "contact@abc.example.com",
        "speaking_sessions_per_month": 20, "created_at": "2026-08-01T00:00:00+00:00",
    }
    row.update(extra)
    return row


def _membership(user_id, institution_id, role="student", status="active", **extra):
    row = {"user_id": user_id, "institution_id": institution_id, "role": role, "status": status,
           "joined_at": "2026-08-02T00:00:00+00:00"}
    row.update(extra)
    return row


def _profile(user_id, sessions_used=0, **extra):
    row = {"user_id": user_id, "plan": "free", "sessions_used_this_month": sessions_used,
           "sessions_reset_date": institution_module.get_month_start_utc(), "bonus_sessions": 0}
    row.update(extra)
    return row


# ── Authorization: reuse require_analyst verbatim, no new auth surface ──

def test_reuses_admin_modules_require_analyst():
    assert ai_module.require_analyst is admin_module.require_analyst


def test_institution_admin_without_staff_role_denied_by_require_analyst(monkeypatch):
    """institution_members.role='institution_admin' grants nothing here --
    require_analyst reads only public.user_roles, which has no row for this
    user, so it defaults to 'user' and is rejected. Proves the two role
    systems stay isolated (spec Section 7)."""
    user = _user()
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(
        user_roles=[],  # no staff role row for this user
        institution_members=[_membership(user.id, inst_id, role="institution_admin")],
    )
    monkeypatch.setattr(admin_module, "get_supabase", lambda: fake)
    with pytest.raises(HTTPException) as excinfo:
        ai_module.require_analyst(current_user=user)
    assert excinfo.value.status_code == 403


# ── GET /admin/institutions/{id}: 404 for a nonexistent institution ─────

def test_unknown_institution_id_returns_404_on_every_path_scoped_route(monkeypatch):
    fake = _FakeSupabase(institutions=[])
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)
    missing_id = str(uuid.uuid4())

    for fn in (
        ai_module.get_institution_detail,
        ai_module.get_institution_students,
        ai_module.get_institution_usage,
        ai_module.list_institution_admins,
        ai_module.list_institution_invites,
    ):
        with pytest.raises(HTTPException) as excinfo:
            fn(missing_id, current_user=_user())
        assert excinfo.value.status_code == 404


# ── GET /admin/institutions: list, batched, no cross-tenant ambiguity ───

def test_list_institutions_batches_across_institutions_no_ambiguity(monkeypatch):
    inst_a, inst_b = str(uuid.uuid4()), str(uuid.uuid4())
    student_a, student_b = str(uuid.uuid4()), str(uuid.uuid4())
    admin_a = str(uuid.uuid4())
    fake = _FakeSupabase(
        institutions=[_institution(inst_a, name="A", created_at="2026-08-02T00:00:00+00:00"),
                      _institution(inst_b, name="B", created_at="2026-08-01T00:00:00+00:00")],
        institution_members=[
            _membership(student_a, inst_a, role="student"),
            _membership(student_b, inst_b, role="student"),
            _membership(admin_a, inst_a, role="institution_admin"),
        ],
        institution_modules=[
            {"institution_id": inst_a, "module": "speaking", "enabled": True},
            {"institution_id": inst_b, "module": "reading", "enabled": True},
        ],
        user_profiles=[_profile(student_a, sessions_used=4), _profile(student_b, sessions_used=9)],
        users=[{"id": admin_a, "email": "admin-a@example.com"}],
    )
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)

    result = ai_module.list_institutions(current_user=_user())

    assert [r["id"] for r in result] == [inst_a, inst_b]  # newest created_at first
    row_a = next(r for r in result if r["id"] == inst_a)
    row_b = next(r for r in result if r["id"] == inst_b)
    assert row_a["active_students"] == 1
    assert row_a["sessions_this_month"] == 4
    assert row_a["enabled_modules"] == ["speaking"]
    assert row_a["admin_emails"] == ["admin-a@example.com"]
    assert row_b["active_students"] == 1
    assert row_b["sessions_this_month"] == 9
    assert row_b["admin_emails"] == []  # institution B has no admin -- must not inherit A's


def test_list_institutions_empty_when_no_institutions(monkeypatch):
    fake = _FakeSupabase(institutions=[])
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)
    assert ai_module.list_institutions(current_user=_user()) == []


# ── GET /admin/institutions/{id}: overview ───────────────────────────────

def test_institution_detail_returns_overview_fields(monkeypatch):
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _FakeSupabase(
        institutions=[_institution(inst_id)],
        institution_members=[_membership(student, inst_id, role="student")],
        institution_modules=[{"institution_id": inst_id, "module": "speaking", "enabled": True}],
    )
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)

    detail = ai_module.get_institution_detail(inst_id, current_user=_user())

    assert detail["id"] == inst_id
    assert detail["name"] == "ABC Nursing Institute"
    assert detail["contact_email"] == "contact@abc.example.com"
    assert detail["active_student_count"] == 1
    assert detail["enabled_modules"] == ["speaking"]


# ── GET /admin/institutions/{id}/students: staff-scoped roster ──────────

def test_students_roster_scoped_to_path_institution_not_other_institutions(monkeypatch):
    inst_a, inst_b = str(uuid.uuid4()), str(uuid.uuid4())
    student_a, student_b = str(uuid.uuid4()), str(uuid.uuid4())
    fake = _FakeSupabase(
        institutions=[_institution(inst_a), _institution(inst_b)],
        institution_members=[
            _membership(student_a, inst_a, role="student"),
            _membership(student_b, inst_b, role="student"),
        ],
        institution_modules=[{"institution_id": inst_a, "module": "speaking", "enabled": True}],
        users=[{"id": student_a, "email": "a@example.com", "name": "A"}],
        user_profiles=[_profile(student_a, sessions_used=2)],
    )
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)

    roster = ai_module.get_institution_students(inst_a, current_user=_user())

    assert len(roster) == 1
    assert roster[0]["email"] == "a@example.com"
    assert roster[0]["sessions_used_this_month"] == 2


def test_students_roster_never_leaks_user_id_or_internal_fields(monkeypatch):
    inst_id = str(uuid.uuid4())
    student = str(uuid.uuid4())
    fake = _FakeSupabase(
        institutions=[_institution(inst_id)],
        institution_members=[_membership(student, inst_id, role="student")],
        institution_modules=[{"institution_id": inst_id, "module": "speaking", "enabled": True}],
        users=[{"id": student, "email": "s@example.com", "name": "S"}],
        user_profiles=[_profile(student, sessions_used=1, plan="pro", bonus_sessions=2,
                                 subscription_status="active")],
    )
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)

    roster = ai_module.get_institution_students(inst_id, current_user=_user())

    for forbidden in ("user_id", "plan", "subscription_status", "bonus_sessions", "institution_id"):
        assert forbidden not in roster[0]


# ── GET /admin/institutions/{id}/usage: numbers only ─────────────────────

def test_institution_usage_sums_sessions_and_reports_quota(monkeypatch):
    inst_id = str(uuid.uuid4())
    student_a, student_b = str(uuid.uuid4()), str(uuid.uuid4())
    fake = _FakeSupabase(
        institutions=[_institution(inst_id, speaking_sessions_per_month=15)],
        institution_members=[
            _membership(student_a, inst_id, role="student"),
            _membership(student_b, inst_id, role="student"),
        ],
        institution_modules=[{"institution_id": inst_id, "module": "speaking", "enabled": True}],
        user_profiles=[_profile(student_a, sessions_used=3), _profile(student_b, sessions_used=5)],
    )
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)

    usage = ai_module.get_institution_usage(inst_id, current_user=_user())

    assert usage["active_student_count"] == 2
    assert usage["sessions_this_month"] == 8
    assert usage["speaking_sessions_per_month"] == 15
    assert usage["enabled_modules"] == ["speaking"]


# ── GET /admin/institutions/{id}/admins: staff-scoped, no credential leak ─

def test_list_admins_returns_only_institution_admin_role_for_this_institution(monkeypatch):
    inst_a, inst_b = str(uuid.uuid4()), str(uuid.uuid4())
    admin_a, student_a, admin_b = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    fake = _FakeSupabase(
        institutions=[_institution(inst_a)],
        institution_members=[
            _membership(admin_a, inst_a, role="institution_admin"),
            _membership(student_a, inst_a, role="student"),
            _membership(admin_b, inst_b, role="institution_admin"),
        ],
        users=[
            {"id": admin_a, "email": "admin-a@example.com", "name": "Admin A"},
            {"id": admin_b, "email": "admin-b@example.com", "name": "Admin B"},
        ],
    )
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)

    admins = ai_module.list_institution_admins(inst_a, current_user=_user())

    assert len(admins) == 1
    assert admins[0]["email"] == "admin-a@example.com"


def test_list_admins_never_returns_auth_credentials_or_password(monkeypatch):
    inst_id = str(uuid.uuid4())
    admin_id = str(uuid.uuid4())
    fake = _FakeSupabase(
        institutions=[_institution(inst_id)],
        institution_members=[_membership(admin_id, inst_id, role="institution_admin")],
        users=[{"id": admin_id, "email": "a@example.com", "name": "A", "password": "should-never-appear"}],
    )
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)

    admins = ai_module.list_institution_admins(inst_id, current_user=_user())

    for forbidden in ("password", "user_id"):
        assert forbidden not in admins[0]


# ── GET /admin/institutions/{id}/invites: no token leakage ──────────────

def test_list_invites_never_returns_token_role_or_institution_id(monkeypatch):
    inst_id = str(uuid.uuid4())
    invite_id = str(uuid.uuid4())
    fake = _FakeSupabase(
        institutions=[_institution(inst_id)],
        institution_invites=[{
            "id": invite_id, "institution_id": inst_id, "token": "raw-secret-token",
            "role": "student", "status": "active", "max_uses": 3, "use_count": 1,
            "expires_at": None, "created_at": "2026-08-28T00:00:00+00:00", "created_by": str(uuid.uuid4()),
        }],
    )
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)

    result = ai_module.list_institution_invites(inst_id, current_user=_user())

    assert len(result) == 1
    for forbidden in ("token", "role", "institution_id", "created_by"):
        assert forbidden not in result[0]
    assert result[0]["remaining_uses"] == 2


def test_list_invites_reuses_institution_module_invite_summary():
    assert ai_module._invite_summary is institution_module._invite_summary


# ── Phase 5.2: POST /admin/institutions, PATCH /admin/institutions/{id} ──

def _create_req(**overrides):
    payload = {
        "name": "ABC Nursing Institute", "slug": "abc-nursing",
        "contact_email": "contact@abc.example.com", "status": "active",
        "modules": ["speaking"], "speaking_sessions_per_month": 20,
    }
    payload.update(overrides)
    return ai_module.InstitutionCreate(**payload)


# ── Authorization: admin/owner allowed, everyone else denied ────────────

def test_create_and_update_reuse_admin_modules_require_admin_verbatim():
    assert ai_module.require_admin is admin_module.require_admin


def test_owner_satisfies_require_admin_via_existing_rank_hierarchy(monkeypatch):
    # No new "owner" special-case anywhere in admin_institutions.py --
    # ROLE_RANK["owner"] (4) >= ROLE_RANK["admin"] (3) already satisfies
    # require_admin's floor check (admin.py:56).
    user = _user()
    fake = _FakeSupabase(user_roles=[{"user_id": user.id, "role": "owner"}])
    monkeypatch.setattr(admin_module, "get_supabase", lambda: fake)
    assert ai_module.require_admin(current_user=user) is user


@pytest.mark.parametrize("role", ["analyst", "support", "user"])
def test_sub_admin_staff_roles_denied_by_require_admin(monkeypatch, role):
    user = _user()
    rows = [] if role == "user" else [{"user_id": user.id, "role": role}]
    fake = _FakeSupabase(user_roles=rows)
    monkeypatch.setattr(admin_module, "get_supabase", lambda: fake)
    with pytest.raises(HTTPException) as excinfo:
        ai_module.require_admin(current_user=user)
    assert excinfo.value.status_code == 403


def test_institution_admin_without_staff_role_denied_by_require_admin(monkeypatch):
    """Same isolation guarantee as the existing require_analyst test above,
    re-proven for require_admin: an institution_members role grants nothing
    against the staff (user_roles) check."""
    user = _user()
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(
        user_roles=[],
        institution_members=[_membership(user.id, inst_id, role="institution_admin")],
    )
    monkeypatch.setattr(admin_module, "get_supabase", lambda: fake)
    with pytest.raises(HTTPException) as excinfo:
        ai_module.require_admin(current_user=user)
    assert excinfo.value.status_code == 403


# ── POST /admin/institutions: validation ─────────────────────────────────

def test_create_rejects_invalid_module_value():
    with pytest.raises(ValidationError):
        _create_req(modules=["speaking", "not_a_real_module"])


@pytest.mark.parametrize("bad_quota", [0, -1])
def test_create_rejects_non_positive_quota(bad_quota):
    with pytest.raises(ValidationError):
        _create_req(speaking_sessions_per_month=bad_quota)


def test_update_rejects_invalid_module_value():
    with pytest.raises(ValidationError):
        ai_module.InstitutionUpdate(modules=["not_a_real_module"])


@pytest.mark.parametrize("bad_quota", [0, -1])
def test_update_rejects_non_positive_quota(bad_quota):
    with pytest.raises(ValidationError):
        ai_module.InstitutionUpdate(speaking_sessions_per_month=bad_quota)


def test_update_has_no_institution_id_field_client_cannot_smuggle_a_target():
    # Same convention as InviteCreate (institutions.py) -- a client-supplied
    # institution_id in the raw JSON body is silently dropped by pydantic
    # (unknown fields ignored by default), never becoming a real attribute.
    parsed = ai_module.InstitutionUpdate.model_validate({
        "institution_id": str(uuid.uuid4()), "name": "New Name",
    })
    assert not hasattr(parsed, "institution_id")


# ── POST /admin/institutions: create ─────────────────────────────────────

def test_create_institution_creates_institution_and_module_rows(monkeypatch):
    calls = []
    _record_audit_log(monkeypatch, calls)
    fake = _FakeSupabase(institutions=[], institution_modules=[])
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)

    req = _create_req(modules=["speaking", "reading"])
    result = ai_module.create_institution(req, current_user=_user())

    assert len(fake.tables["institutions"]) == 1
    created = fake.tables["institutions"][0]
    assert created["slug"] == "abc-nursing"
    assert created["id"] == result["id"]

    module_rows = [m for m in fake.tables["institution_modules"] if m["institution_id"] == result["id"]]
    assert {m["module"] for m in module_rows} == {"speaking", "reading"}
    assert all(m["enabled"] for m in module_rows)
    assert result["enabled_modules"] == ["reading", "speaking"]

    created_events = [c for c in calls if c["action"] == "institution_created"]
    assert len(created_events) == 1
    assert created_events[0]["target_id"] == result["id"]
    assert created_events[0]["detail"]["slug"] == "abc-nursing"


def test_create_institution_duplicate_slug_returns_409(monkeypatch):
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(institutions=[_institution(inst_id, slug="abc-nursing")], institution_modules=[])
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(ai_module, "_write_audit_log", lambda *a, **k: None)

    with pytest.raises(HTTPException) as excinfo:
        ai_module.create_institution(_create_req(slug="abc-nursing"), current_user=_user())
    assert excinfo.value.status_code == 409
    # No second institution row was appended alongside the rejected duplicate.
    assert len(fake.tables["institutions"]) == 1


def test_failed_module_insert_leaves_no_partial_institution_state(monkeypatch):
    """The core atomicity guarantee (spec: 'creating an institution plus its
    module rows must not leave a half-configured institution if a later
    insert fails'). Pydantic's Literal already blocks a bad module value at
    the HTTP boundary, so this reaches past that boundary and calls the RPC
    contract directly -- the same contract admin_create_institution's SQL
    (one function call = one transaction) provides for real, reproduced here
    by _FakeRpc so it's verifiable without a live DB."""
    fake = _FakeSupabase(institutions=[], institution_modules=[])

    with pytest.raises(Exception, match="check constraint"):
        fake.rpc("admin_create_institution", {
            "p_name": "ABC", "p_slug": "abc-nursing", "p_logo_url": None,
            "p_contact_email": "c@example.com", "p_status": "active", "p_quota": 20,
            "p_modules": ["speaking", "not_a_real_module"],
        }).execute()

    assert fake.tables["institutions"] == []
    assert fake.tables["institution_modules"] == []


def test_create_institution_endpoint_propagates_rpc_failure_without_partial_writes(monkeypatch):
    """Same guarantee, exercised through the real endpoint function -- proves
    create_institution() doesn't itself do any writing that could survive an
    RPC failure (e.g. no institutions insert issued in Python before/after
    the RPC call)."""
    fake = _FakeSupabase(institutions=[], institution_modules=[])
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(ai_module, "_write_audit_log", lambda *a, **k: None)

    # Bypass InstitutionCreate's own Literal validation (model_construct skips
    # validators) to simulate a module value slipping past the HTTP boundary,
    # isolating this test to the endpoint+RPC atomicity contract itself.
    req = ai_module.InstitutionCreate.model_construct(
        name="ABC", slug="abc-nursing", logo_url=None, contact_email="c@example.com",
        status="active", modules=["speaking", "not_a_real_module"], speaking_sessions_per_month=20,
    )

    with pytest.raises(Exception, match="check constraint"):
        ai_module.create_institution(req, current_user=_user())

    assert fake.tables["institutions"] == []
    assert fake.tables["institution_modules"] == []


# ── PATCH /admin/institutions/{id}: partial update ───────────────────────

def test_patch_updates_only_permitted_fields(monkeypatch):
    calls = []
    _record_audit_log(monkeypatch, calls)
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(
        institutions=[_institution(inst_id, name="Old Name", slug="old-slug", contact_email="old@example.com")],
        institution_modules=[{"institution_id": inst_id, "module": "speaking", "enabled": True}],
    )
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)

    ai_module.update_institution(inst_id, ai_module.InstitutionUpdate(name="New Name"), current_user=_user())

    row = fake.tables["institutions"][0]
    assert row["name"] == "New Name"
    # Untouched fields stay exactly as they were.
    assert row["slug"] == "old-slug"
    assert row["contact_email"] == "old@example.com"
    assert row["status"] == "active"

    updated_events = [c for c in calls if c["action"] == "institution_updated"]
    assert len(updated_events) == 1
    assert updated_events[0]["detail"] == {"name": "New Name"}
    # No quota/module events fired for a name-only patch.
    assert not [c for c in calls if c["action"] in ("institution_quota_changed", "institution_module_changed")]


def test_patch_with_no_fields_returns_400(monkeypatch):
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(institutions=[_institution(inst_id)], institution_modules=[])
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)

    with pytest.raises(HTTPException) as excinfo:
        ai_module.update_institution(inst_id, ai_module.InstitutionUpdate(), current_user=_user())
    assert excinfo.value.status_code == 400


def test_patch_unknown_institution_returns_404(monkeypatch):
    fake = _FakeSupabase(institutions=[])
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)

    with pytest.raises(HTTPException) as excinfo:
        ai_module.update_institution(str(uuid.uuid4()), ai_module.InstitutionUpdate(name="X"), current_user=_user())
    assert excinfo.value.status_code == 404


def test_patch_duplicate_slug_returns_409(monkeypatch):
    inst_a, inst_b = str(uuid.uuid4()), str(uuid.uuid4())
    fake = _FakeSupabase(institutions=[
        _institution(inst_a, slug="taken-slug"),
        _institution(inst_b, slug="my-slug"),
    ], institution_modules=[])
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(ai_module, "_write_audit_log", lambda *a, **k: None)

    with pytest.raises(HTTPException) as excinfo:
        ai_module.update_institution(inst_b, ai_module.InstitutionUpdate(slug="taken-slug"), current_user=_user())
    assert excinfo.value.status_code == 409
    # inst_b's slug was never actually overwritten by the rejected update.
    assert next(r for r in fake.tables["institutions"] if r["id"] == inst_b)["slug"] == "my-slug"


def test_patch_quota_change_fires_quota_changed_audit_with_old_and_new(monkeypatch):
    calls = []
    _record_audit_log(monkeypatch, calls)
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(
        institutions=[_institution(inst_id, speaking_sessions_per_month=20)],
        institution_modules=[],
    )
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)

    ai_module.update_institution(
        inst_id, ai_module.InstitutionUpdate(speaking_sessions_per_month=15), current_user=_user(),
    )

    quota_events = [c for c in calls if c["action"] == "institution_quota_changed"]
    assert len(quota_events) == 1
    assert quota_events[0]["detail"] == {"old_quota": 20, "new_quota": 15}
    assert not [c for c in calls if c["action"] == "institution_updated"]  # quota-only patch, no core fields


def test_patch_modules_enables_and_disables_and_audits_only_changed_modules(monkeypatch):
    calls = []
    _record_audit_log(monkeypatch, calls)
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(
        institutions=[_institution(inst_id)],
        institution_modules=[
            {"institution_id": inst_id, "module": "speaking", "enabled": True},
            {"institution_id": inst_id, "module": "reading", "enabled": False},
        ],
    )
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)

    # speaking stays enabled (untouched/unaudited), reading turns on, writing turns on.
    ai_module.update_institution(
        inst_id, ai_module.InstitutionUpdate(modules=["speaking", "reading", "writing"]), current_user=_user(),
    )

    enabled_now = {
        m["module"] for m in fake.tables["institution_modules"]
        if m["institution_id"] == inst_id and m["enabled"]
    }
    assert enabled_now == {"speaking", "reading", "writing"}

    module_events = {c["detail"]["module"]: c["detail"]["enabled"]
                     for c in calls if c["action"] == "institution_module_changed"}
    assert module_events == {"reading": True, "writing": True}  # speaking never appears -- it didn't change


def test_patch_modules_can_disable_a_previously_enabled_module(monkeypatch):
    calls = []
    _record_audit_log(monkeypatch, calls)
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(
        institutions=[_institution(inst_id)],
        institution_modules=[{"institution_id": inst_id, "module": "speaking", "enabled": True}],
    )
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)

    ai_module.update_institution(inst_id, ai_module.InstitutionUpdate(modules=[]), current_user=_user())

    row = next(m for m in fake.tables["institution_modules"] if m["module"] == "speaking")
    assert row["enabled"] is False
    module_events = [c for c in calls if c["action"] == "institution_module_changed"]
    assert module_events == [{"action": "institution_module_changed", "target_type": "institution",
                               "target_id": inst_id, "target_label": None,
                               "detail": {"module": "speaking", "enabled": False}}]


# ── Regression: existing Phase 1-4 institution behavior and B2C untouched ─

def test_phase52_adds_no_new_module_level_dependency_functions():
    """Phase 5.2 authorization is exactly require_admin (already covered
    above) -- admin_institutions.py never imports
    require_active_institution_role, keeping the two role systems isolated
    exactly as Phase 5.1 established (spec Section 7)."""
    assert not hasattr(ai_module, "require_active_institution_role")


# ── POST /admin/institutions/{id}/staff (Phase 5.3b) ────────────────────
# Auth resolution is stubbed with a fake standing in for Supabase Auth's
# admin API (generate_link/invite_user_by_email) -- error strings and
# creation semantics below match what was observed live against the QA
# project's Supabase Auth in Phase 5.3a
# (backend/scripts/qa_verify_phase5_3a_auth_behavior.py), not guessed.

class _FakeAuthUser:
    def __init__(self, id, email, email_confirmed_at=None):
        self.id = id
        self.email = email
        self.email_confirmed_at = email_confirmed_at


class _FakeLinkResp:
    def __init__(self, user):
        self.user = user


class _FakeAdminAuth:
    def __init__(self, users=None, invite_fails=False):
        self.users = {u.email: u for u in (users or [])}
        self.invite_fails = invite_fails
        self.invite_calls = []
        self.generate_link_calls = []

    def generate_link(self, params):
        email = params["email"]
        self.generate_link_calls.append(email)
        user = self.users.get(email)
        if user is None:
            raise Exception("AuthApiError: User with this email not found")
        return _FakeLinkResp(user)

    def invite_user_by_email(self, email, options=None):
        self.invite_calls.append(email)
        if self.invite_fails:
            raise Exception("AuthApiError: Error sending invite email")
        user = self.users.get(email)
        if user is None:
            user = _FakeAuthUser(id=str(uuid.uuid4()), email=email, email_confirmed_at=None)
            self.users[email] = user
        return _FakeLinkResp(user)


class _FakeAuthNamespace:
    def __init__(self, admin):
        self.admin = admin


def _staff_fake(institution_id, *, members=None, auth_admin=None):
    fake = _FakeSupabase(institutions=[_institution(institution_id)], institution_members=members or [])
    fake.auth = _FakeAuthNamespace(auth_admin if auth_admin is not None else _FakeAdminAuth())
    return fake


def _existing_membership_fake(inst_id, email, *, membership_role, membership_status, confirmed=True):
    uid = str(uuid.uuid4())
    auth_user = _FakeAuthUser(
        id=uid, email=email,
        email_confirmed_at="2026-01-01T00:00:00+00:00" if confirmed else None,
    )
    fake = _staff_fake(
        inst_id,
        members=[_membership(uid, inst_id, role=membership_role, status=membership_status)],
        auth_admin=_FakeAdminAuth(users=[auth_user]),
    )
    return fake, uid


def _assign(monkeypatch, fake, institution_id, email, role, current_user=None, stub_audit=True, capture_response=None):
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(ai_module.staff_assign_rate_limiter, "is_rate_limited", lambda key: False)
    if stub_audit:
        monkeypatch.setattr(ai_module, "_write_audit_log", lambda *a, **k: None)
    response = Response()
    result = ai_module.assign_institution_staff(
        institution_id, ai_module.StaffAssign(email=email, role=role),
        http_response=response, current_user=current_user or _user(),
    )
    if capture_response is not None:
        capture_response.append(response)
    return result


# ── Authorization: reuses require_admin verbatim, never require_active_institution_role ──

def test_staff_assign_reuses_admin_modules_require_admin():
    assert ai_module.require_admin is admin_module.require_admin


def test_staff_assign_admin_role_allowed(monkeypatch):
    user = _user()
    fake = _FakeSupabase(user_roles=[{"user_id": user.id, "role": "admin"}])
    monkeypatch.setattr(admin_module, "get_supabase", lambda: fake)
    assert ai_module.require_admin(current_user=user) is user


def test_staff_assign_owner_role_allowed(monkeypatch):
    user = _user()
    fake = _FakeSupabase(user_roles=[{"user_id": user.id, "role": "owner"}])
    monkeypatch.setattr(admin_module, "get_supabase", lambda: fake)
    assert ai_module.require_admin(current_user=user) is user


def test_staff_assign_analyst_role_denied(monkeypatch):
    user = _user()
    fake = _FakeSupabase(user_roles=[{"user_id": user.id, "role": "analyst"}])
    monkeypatch.setattr(admin_module, "get_supabase", lambda: fake)
    with pytest.raises(HTTPException) as excinfo:
        ai_module.require_admin(current_user=user)
    assert excinfo.value.status_code == 403


def test_staff_assign_support_role_denied(monkeypatch):
    user = _user()
    fake = _FakeSupabase(user_roles=[{"user_id": user.id, "role": "support"}])
    monkeypatch.setattr(admin_module, "get_supabase", lambda: fake)
    with pytest.raises(HTTPException) as excinfo:
        ai_module.require_admin(current_user=user)
    assert excinfo.value.status_code == 403


def test_staff_assign_plain_user_role_denied(monkeypatch):
    user = _user()
    fake = _FakeSupabase(user_roles=[{"user_id": user.id, "role": "user"}])
    monkeypatch.setattr(admin_module, "get_supabase", lambda: fake)
    with pytest.raises(HTTPException) as excinfo:
        ai_module.require_admin(current_user=user)
    assert excinfo.value.status_code == 403


def test_staff_assign_institution_admin_without_staff_role_denied(monkeypatch):
    """institution_members.role='institution_admin' grants nothing against
    require_admin -- the two role systems stay isolated (spec Section 7)."""
    user = _user()
    inst_id = str(uuid.uuid4())
    fake = _FakeSupabase(
        user_roles=[], institution_members=[_membership(user.id, inst_id, role="institution_admin")],
    )
    monkeypatch.setattr(admin_module, "get_supabase", lambda: fake)
    with pytest.raises(HTTPException) as excinfo:
        ai_module.require_admin(current_user=user)
    assert excinfo.value.status_code == 403


# ── 404 / request validation ────────────────────────────────────────────

def test_staff_assign_unknown_institution_returns_404(monkeypatch):
    fake = _staff_fake(str(uuid.uuid4()))
    with pytest.raises(HTTPException) as excinfo:
        _assign(monkeypatch, fake, str(uuid.uuid4()), "new@example.com", "teacher")
    assert excinfo.value.status_code == 404


def test_staff_assign_malformed_email_rejected_by_model():
    with pytest.raises(ValidationError):
        ai_module.StaffAssign.model_validate({"email": "not-an-email", "role": "teacher"})


def test_staff_assign_invalid_role_rejected_by_model():
    with pytest.raises(ValidationError):
        ai_module.StaffAssign.model_validate({"email": "new@example.com", "role": "student"})
    with pytest.raises(ValidationError):
        ai_module.StaffAssign.model_validate({"email": "new@example.com", "role": "owner"})


def test_staff_assign_institution_id_field_is_not_declared_on_model():
    """No institution_id field on the body -- the only scope is the path
    parameter (InviteCreate/InstitutionUpdate convention). An injected value
    is silently dropped by pydantic, never read by the endpoint."""
    parsed = ai_module.StaffAssign.model_validate({
        "email": "new@example.com", "role": "teacher", "institution_id": str(uuid.uuid4()),
    })
    assert not hasattr(parsed, "institution_id")


def test_staff_assign_user_id_field_is_not_declared_on_model():
    """No user_id field either -- the only way to name a target is by email,
    resolved server-side; a client cannot smuggle in an arbitrary user_id."""
    parsed = ai_module.StaffAssign.model_validate({
        "email": "new@example.com", "role": "teacher", "user_id": str(uuid.uuid4()),
    })
    assert not hasattr(parsed, "user_id")


# ── Auth resolution: new / existing confirmed / existing unconfirmed ────

def test_staff_assign_new_auth_user_creates_active_membership(monkeypatch):
    inst_id = str(uuid.uuid4())
    fake = _staff_fake(inst_id)

    result = _assign(monkeypatch, fake, inst_id, "brand-new@example.com", "teacher")

    assert result["auth_state"] == "not_found"
    assert result["status"] == "active"
    row = fake.tables["institution_members"][0]
    assert row["status"] == "active"
    assert row["role"] == "teacher"
    assert row["joined_at"] is not None
    assert fake.auth.admin.invite_calls == ["brand-new@example.com"]


def test_staff_assign_existing_confirmed_user_creates_active_membership_no_invite_sent(monkeypatch):
    inst_id = str(uuid.uuid4())
    existing = _FakeAuthUser(id=str(uuid.uuid4()), email="confirmed@example.com",
                              email_confirmed_at="2026-01-01T00:00:00+00:00")
    admin_auth = _FakeAdminAuth(users=[existing])
    fake = _staff_fake(inst_id, auth_admin=admin_auth)

    result = _assign(monkeypatch, fake, inst_id, "confirmed@example.com", "institution_admin")

    assert result["auth_state"] == "confirmed"
    assert result["status"] == "active"
    assert admin_auth.invite_calls == []
    row = fake.tables["institution_members"][0]
    assert row["user_id"] == existing.id
    assert row["status"] == "active"


def test_staff_assign_existing_unconfirmed_user_creates_active_membership_no_duplicate_auth_user(monkeypatch):
    """Staff assignment IS the authorization decision -- an unconfirmed Auth
    user still gets an active institution_members row immediately. The Auth
    invite only controls the user's own login/password setup and is
    reissued best-effort alongside it (spec Section 1/2)."""
    inst_id = str(uuid.uuid4())
    existing = _FakeAuthUser(id=str(uuid.uuid4()), email="pending@example.com", email_confirmed_at=None)
    admin_auth = _FakeAdminAuth(users=[existing])
    fake = _staff_fake(inst_id, auth_admin=admin_auth)

    result = _assign(monkeypatch, fake, inst_id, "pending@example.com", "teacher")

    assert result["auth_state"] == "unconfirmed"
    assert result["status"] == "active"
    assert admin_auth.invite_calls == ["pending@example.com"]  # resend attempted
    assert len(admin_auth.users) == 1  # no duplicate Auth user created
    row = fake.tables["institution_members"][0]
    assert row["user_id"] == existing.id
    assert row["status"] == "active"
    assert row["joined_at"] is not None


def test_staff_assign_unconfirmed_resend_failure_still_creates_active_membership_with_warning(monkeypatch):
    """Resend failure must not downgrade the membership -- it's already the
    authorization grant, independent of whether the Auth email went out."""
    inst_id = str(uuid.uuid4())
    existing = _FakeAuthUser(id=str(uuid.uuid4()), email="pending2@example.com", email_confirmed_at=None)
    admin_auth = _FakeAdminAuth(users=[existing], invite_fails=True)
    fake = _staff_fake(inst_id, auth_admin=admin_auth)

    result = _assign(monkeypatch, fake, inst_id, "pending2@example.com", "teacher")

    assert result["status"] == "active"
    assert result["warning"] == "invite_resend_failed"
    assert fake.tables["institution_members"][0]["status"] == "active"


def test_staff_assign_auth_probe_failure_creates_no_membership(monkeypatch):
    inst_id = str(uuid.uuid4())

    class _BrokenAdminAuth(_FakeAdminAuth):
        def generate_link(self, params):
            raise Exception("AuthApiError: rate limit exceeded")

    fake = _staff_fake(inst_id, auth_admin=_BrokenAdminAuth())
    with pytest.raises(HTTPException) as excinfo:
        _assign(monkeypatch, fake, inst_id, "x@example.com", "teacher")
    assert excinfo.value.status_code == 502
    assert fake.tables.get("institution_members", []) == []


def test_staff_assign_new_user_invite_failure_creates_no_membership(monkeypatch):
    inst_id = str(uuid.uuid4())
    fake = _staff_fake(inst_id, auth_admin=_FakeAdminAuth(invite_fails=True))
    with pytest.raises(HTTPException) as excinfo:
        _assign(monkeypatch, fake, inst_id, "fresh@example.com", "teacher")
    assert excinfo.value.status_code == 502
    assert fake.tables.get("institution_members", []) == []


# ── Existing-membership rules ────────────────────────────────────────────

def test_staff_assign_existing_student_membership_returns_409(monkeypatch):
    inst_id = str(uuid.uuid4())
    fake, _ = _existing_membership_fake(inst_id, "student@example.com", membership_role="student", membership_status="active")
    with pytest.raises(HTTPException) as excinfo:
        _assign(monkeypatch, fake, inst_id, "student@example.com", "teacher")
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["error"] == "already_student"


def test_staff_assign_existing_teacher_membership_returns_409(monkeypatch):
    inst_id = str(uuid.uuid4())
    fake, _ = _existing_membership_fake(inst_id, "teacher@example.com", membership_role="teacher", membership_status="active")
    with pytest.raises(HTTPException) as excinfo:
        _assign(monkeypatch, fake, inst_id, "teacher@example.com", "institution_admin")
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["error"] == "already_teacher"


def test_staff_assign_existing_revoked_membership_returns_409_not_reactivated(monkeypatch):
    inst_id = str(uuid.uuid4())
    fake, _ = _existing_membership_fake(inst_id, "revoked@example.com", membership_role="teacher", membership_status="revoked")
    with pytest.raises(HTTPException) as excinfo:
        _assign(monkeypatch, fake, inst_id, "revoked@example.com", "teacher")
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["error"] == "revoked_membership"
    assert fake.tables["institution_members"][0]["status"] == "revoked"


def test_staff_assign_existing_invited_membership_returns_409(monkeypatch):
    inst_id = str(uuid.uuid4())
    fake, _ = _existing_membership_fake(inst_id, "invited@example.com", membership_role="teacher",
                                         membership_status="invited", confirmed=False)
    with pytest.raises(HTTPException) as excinfo:
        _assign(monkeypatch, fake, inst_id, "invited@example.com", "teacher")
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["error"] == "pending_membership"


def test_staff_assign_existing_institution_admin_returns_200_already_assigned(monkeypatch):
    inst_id = str(uuid.uuid4())
    fake, _ = _existing_membership_fake(inst_id, "admin@example.com", membership_role="institution_admin", membership_status="active")
    captured = []
    result = _assign(monkeypatch, fake, inst_id, "admin@example.com", "institution_admin", capture_response=captured)
    assert result["status"] == "already_assigned"
    assert len(fake.tables["institution_members"]) == 1
    assert captured[0].status_code == 200


def test_staff_assign_new_membership_returns_201(monkeypatch):
    """Phase 5.3b API contract: new staff membership creation is HTTP 201,
    matching the sibling POST /admin/institutions status_code=201."""
    inst_id = str(uuid.uuid4())
    fake = _staff_fake(inst_id)
    captured = []
    result = _assign(monkeypatch, fake, inst_id, "new201@example.com", "teacher", capture_response=captured)
    assert result["status"] == "active"
    assert captured[0].status_code == 201


def test_staff_assign_repeated_call_does_not_create_duplicate_membership(monkeypatch):
    inst_id = str(uuid.uuid4())
    fake = _staff_fake(inst_id)
    first = _assign(monkeypatch, fake, inst_id, "repeat@example.com", "teacher")
    assert first["status"] == "active"
    assert len(fake.tables["institution_members"]) == 1

    with pytest.raises(HTTPException) as excinfo:
        _assign(monkeypatch, fake, inst_id, "repeat@example.com", "teacher")
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["error"] == "already_teacher"
    assert len(fake.tables["institution_members"]) == 1


def test_staff_assign_insert_level_duplicate_key_race_returns_409(monkeypatch):
    """Simulates a concurrent second request landing between the pre-check
    read and this request's insert -- the UNIQUE(institution_id, user_id)
    constraint is the actual backstop, caught the same
    "duplicate key" convention as create_institution/update_institution."""
    inst_id = str(uuid.uuid4())
    fake = _staff_fake(inst_id)
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(ai_module.staff_assign_rate_limiter, "is_rate_limited", lambda key: False)
    monkeypatch.setattr(ai_module, "_write_audit_log", lambda *a, **k: None)

    real_table = fake.table

    def _table(name):
        qb = real_table(name)
        if name == "institution_members":
            def _insert(row):
                raise Exception(
                    'duplicate key value violates unique constraint "institution_members_institution_id_user_id_key"'
                )
            qb.insert = _insert
        return qb
    monkeypatch.setattr(fake, "table", _table)

    with pytest.raises(HTTPException) as excinfo:
        ai_module.assign_institution_staff(
            inst_id, ai_module.StaffAssign(email="race@example.com", role="teacher"),
            http_response=Response(), current_user=_user(),
        )
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["error"] == "already_assigned"


# ── Multiple-institution safety ──────────────────────────────────────────

def test_staff_assign_admin_already_active_staff_in_another_institution_returns_409(monkeypatch):
    inst_a, inst_b = str(uuid.uuid4()), str(uuid.uuid4())
    uid = str(uuid.uuid4())
    auth_user = _FakeAuthUser(id=uid, email="multi@example.com", email_confirmed_at="2026-01-01T00:00:00+00:00")
    fake = _FakeSupabase(
        institutions=[_institution(inst_a), _institution(inst_b)],
        institution_members=[_membership(uid, inst_b, role="institution_admin", status="active")],
    )
    fake.auth = _FakeAuthNamespace(_FakeAdminAuth(users=[auth_user]))

    with pytest.raises(HTTPException) as excinfo:
        _assign(monkeypatch, fake, inst_a, "multi@example.com", "teacher")
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["error"] == "already_staff_elsewhere"
    assert excinfo.value.detail["institution_id"] == inst_b
    assert len(fake.tables["institution_members"]) == 1


# ── Self-assignment: no speculative block ────────────────────────────────

def test_staff_assign_self_assignment_allowed(monkeypatch):
    inst_id = str(uuid.uuid4())
    fake = _staff_fake(inst_id)
    staff_user = UserInfo(id=str(uuid.uuid4()), email="self-assign@example.com")

    result = _assign(monkeypatch, fake, inst_id, "self-assign@example.com", "institution_admin", current_user=staff_user)

    assert result["status"] == "active"
    assert fake.tables["institution_members"][0]["invited_by"] == staff_user.id


# ── Failure/retry handling ────────────────────────────────────────────────

def test_staff_assign_membership_insert_transient_failure_retries_once_then_succeeds(monkeypatch):
    inst_id = str(uuid.uuid4())
    fake = _staff_fake(inst_id)
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(ai_module.staff_assign_rate_limiter, "is_rate_limited", lambda key: False)
    monkeypatch.setattr(ai_module, "_write_audit_log", lambda *a, **k: None)

    real_table = fake.table
    call_count = {"n": 0}

    def _table(name):
        qb = real_table(name)
        if name == "institution_members":
            original_insert = qb.insert

            def _insert(row):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise Exception("connection reset by peer")
                return original_insert(row)
            qb.insert = _insert
        return qb
    monkeypatch.setattr(fake, "table", _table)

    result = ai_module.assign_institution_staff(
        inst_id, ai_module.StaffAssign(email="retry@example.com", role="teacher"),
        http_response=Response(), current_user=_user(),
    )
    assert result["status"] == "active"
    assert call_count["n"] == 2
    assert len(fake.tables["institution_members"]) == 1


def test_staff_assign_membership_insert_failure_after_retry_writes_failure_audit_no_auth_user_deleted(monkeypatch):
    """"do NOT delete Auth user" is proven structurally: _FakeAdminAuth has
    no delete_user method at all, so any accidental call to it would raise
    AttributeError and fail this test before the assertions below run."""
    inst_id = str(uuid.uuid4())
    admin_auth = _FakeAdminAuth()
    fake = _staff_fake(inst_id, auth_admin=admin_auth)
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(ai_module.staff_assign_rate_limiter, "is_rate_limited", lambda key: False)
    calls = []
    _record_audit_log(monkeypatch, calls)

    real_table = fake.table

    def _table(name):
        qb = real_table(name)
        if name == "institution_members":
            def _insert(row):
                raise Exception("connection reset by peer")
            qb.insert = _insert
        return qb
    monkeypatch.setattr(fake, "table", _table)

    with pytest.raises(HTTPException) as excinfo:
        ai_module.assign_institution_staff(
            inst_id, ai_module.StaffAssign(email="failure@example.com", role="teacher"),
            http_response=Response(), current_user=_user(),
        )
    assert excinfo.value.status_code == 500
    failed = [c for c in calls if c["action"] == "institution_staff_assignment_failed"]
    assert len(failed) == 1
    assert admin_auth.invite_calls == ["failure@example.com"]


# ── Audit logging ─────────────────────────────────────────────────────────

def test_staff_assign_writes_institution_staff_assigned_audit_log_no_secrets(monkeypatch):
    inst_id = str(uuid.uuid4())
    fake = _staff_fake(inst_id)
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(ai_module.staff_assign_rate_limiter, "is_rate_limited", lambda key: False)
    calls = []
    _record_audit_log(monkeypatch, calls)

    ai_module.assign_institution_staff(
        inst_id, ai_module.StaffAssign(email="audit@example.com", role="teacher"),
        http_response=Response(), current_user=_user(),
    )

    assigned = [c for c in calls if c["action"] == "institution_staff_assigned"]
    assert len(assigned) == 1
    detail = assigned[0]["detail"]
    assert detail["email"] == "audit@example.com"
    assert detail["role"] == "teacher"
    assert detail["auth_state"] == "not_found"
    assert detail["membership_status"] == "active"
    for forbidden in ("password", "token", "invite_url", "access_token", "refresh_token"):
        assert forbidden not in str(detail).lower()


# ── Rate limiting ─────────────────────────────────────────────────────────

def test_staff_assign_rate_limited_returns_429(monkeypatch):
    inst_id = str(uuid.uuid4())
    fake = _staff_fake(inst_id)
    monkeypatch.setattr(ai_module, "get_supabase", lambda: fake)
    monkeypatch.setattr(ai_module.staff_assign_rate_limiter, "is_rate_limited", lambda key: True)

    with pytest.raises(HTTPException) as excinfo:
        ai_module.assign_institution_staff(
            inst_id, ai_module.StaffAssign(email="limited@example.com", role="teacher"),
            http_response=Response(), current_user=_user(),
        )
    assert excinfo.value.status_code == 429
    assert fake.tables.get("institution_members", []) == []


def test_staff_assign_rate_limit_20_allowed_21st_blocked():
    """Exercises the real SlidingWindowRateLimiter (in-process fallback --
    no REDIS_URL in tests), same convention as institution.py's
    invite_create_rate_limiter test."""
    key = str(uuid.uuid4())
    limiter = ai_module.staff_assign_rate_limiter
    for _ in range(20):
        assert limiter.is_rate_limited(key) is False
    assert limiter.is_rate_limited(key) is True
