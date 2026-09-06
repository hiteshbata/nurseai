from scripts.production_readiness import config
from scripts.production_readiness.checks import supabase
from scripts.production_readiness.models import Status


class _FakeClient:
    def __init__(self, get_responses=None, query_responses=None):
        self._get_responses = get_responses or {}
        self._query_responses = query_responses or {}

    def get(self, path):
        class _R:
            def __init__(self, code, body):
                self.status_code = code
                self._body = body
                self.text = str(body)

            def json(self):
                return self._body

        for prefix, (code, body) in self._get_responses.items():
            if path.startswith(prefix):
                return _R(code, body)
        raise AssertionError(f"unexpected GET {path}")

    def query(self, ref, sql):
        for marker, rows in self._query_responses.items():
            if marker in sql:
                return rows
        raise AssertionError(f"unexpected query: {sql}")

    def close(self):
        pass


def test_missing_credential_is_unknown():
    assert supabase.check_supabase_project(None).status == Status.UNKNOWN
    assert supabase.check_institution_schema(None).status == Status.UNKNOWN
    assert supabase.check_rpc_security(None).status == Status.UNKNOWN


def _project_client(ledger):
    return _FakeClient(
        get_responses={
            f"/projects/{config.PRODUCTION_SUPABASE_PROJECT_REF}/database/migrations": (200, ledger),
            f"/projects/{config.PRODUCTION_SUPABASE_PROJECT_REF}": (200, {"status": "ACTIVE_HEALTHY", "region": "us-east-1"}),
        }
    )


def test_duplicate_migration_fails(monkeypatch):
    ledger = [
        {"version": "20260828200548", "name": "institution_foundation"},
        {"version": "20260828200549", "name": "institution_foundation"},
        {"version": "20260828200854", "name": "institution_invite_accept"},
    ]
    monkeypatch.setattr(supabase, "_SupabaseMgmtClient", lambda token: _project_client(ledger))
    result = supabase.check_supabase_project("fake-token")
    assert result.status == Status.FAIL
    assert "appears 2 times" in result.summary


def test_migration_name_matches_despite_different_ledger_timestamp(monkeypatch):
    """BUG 1 case 1: local filename timestamp (20260826000000) differs from
    the ledger version (20260828200548), but the migration name matches ->
    PASS."""
    ledger = [
        {"version": "20260828200548", "name": "institution_foundation"},
        {"version": "20260828200854", "name": "institution_invite_accept"},
    ]
    monkeypatch.setattr(supabase, "_SupabaseMgmtClient", lambda token: _project_client(ledger))
    result = supabase.check_supabase_project("fake-token")
    assert result.status == Status.PASS


def test_migration_name_missing_fails(monkeypatch):
    """BUG 1 case 2: exact migration name absent from the ledger -> FAIL."""
    ledger = [
        {"version": "20260828200548", "name": "institution_foundation"},
    ]
    monkeypatch.setattr(supabase, "_SupabaseMgmtClient", lambda token: _project_client(ledger))
    result = supabase.check_supabase_project("fake-token")
    assert result.status == Status.FAIL
    assert "institution_invite_accept" in result.summary


def test_migration_unrelated_similar_name_fails(monkeypatch):
    """BUG 1 case 3: ledger has a similarly-named but unrelated migration
    (institution_foundation_backup) -- exact-match must not treat it as a
    hit for institution_foundation -> FAIL."""
    ledger = [
        {"version": "20260828200548", "name": "institution_foundation_backup"},
        {"version": "20260828200854", "name": "institution_invite_accept"},
    ]
    monkeypatch.setattr(supabase, "_SupabaseMgmtClient", lambda token: _project_client(ledger))
    result = supabase.check_supabase_project("fake-token")
    assert result.status == Status.FAIL
    assert "institution_foundation" in result.summary


def test_both_institution_migrations_under_different_ledger_timestamps_pass(monkeypatch):
    """BUG 1 case 4: both institution migrations present, each under a
    ledger version unrelated to its local filename timestamp -> PASS."""
    ledger = [
        {"version": "20260828200548", "name": "institution_foundation"},
        {"version": "20260828200854", "name": "institution_invite_accept"},
    ]
    monkeypatch.setattr(supabase, "_SupabaseMgmtClient", lambda token: _project_client(ledger))
    result = supabase.check_supabase_project("fake-token")
    assert result.status == Status.PASS
    assert "both institution migrations applied exactly once" in result.summary


def test_missing_institution_table_fails(monkeypatch):
    client = _FakeClient(
        query_responses={
            "relrowsecurity": [
                {"table_name": "institutions", "rls_enabled": True},
                {"table_name": "institution_members", "rls_enabled": True},
                {"table_name": "institution_modules", "rls_enabled": True},
                # institution_invites missing entirely
            ],
            "pg_indexes": [],
            "pg_policies": [],
            "table_constraints": [],
        }
    )
    monkeypatch.setattr(supabase, "_SupabaseMgmtClient", lambda token: client)
    result = supabase.check_institution_schema("fake-token")
    assert result.status == Status.FAIL
    assert "institution_invites does not exist" in result.summary


def test_rpc_privilege_mismatch_fails(monkeypatch):
    client = _FakeClient(
        query_responses={
            "prosecdef": [{"proname": "accept_institution_invite", "prosecdef": True, "args": "p_token text, p_user_id uuid"}],
            "routine_privileges": [
                {"grantee": "service_role", "privilege_type": "EXECUTE"},
                {"grantee": "anon", "privilege_type": "EXECUTE"},  # should NOT be granted
            ],
        }
    )
    monkeypatch.setattr(supabase, "_SupabaseMgmtClient", lambda token: client)
    result = supabase.check_rpc_security("fake-token")
    assert result.status == Status.FAIL
    assert "anon" in result.summary


def test_rpc_correct_privileges_pass(monkeypatch):
    client = _FakeClient(
        query_responses={
            "prosecdef": [{"proname": "accept_institution_invite", "prosecdef": True, "args": "p_token text, p_user_id uuid"}],
            "routine_privileges": [{"grantee": "service_role", "privilege_type": "EXECUTE"}],
        }
    )
    monkeypatch.setattr(supabase, "_SupabaseMgmtClient", lambda token: client)
    result = supabase.check_rpc_security("fake-token")
    assert result.status == Status.PASS


def _rpc_client(prosecdef, grantees):
    return _FakeClient(
        query_responses={
            "prosecdef": [{"proname": "accept_institution_invite", "prosecdef": prosecdef, "args": "p_token text, p_user_id uuid"}],
            "routine_privileges": [{"grantee": g, "privilege_type": "EXECUTE"} for g in grantees],
        }
    )


def test_rpc_security_invoker_correct_grants_pass(monkeypatch):
    """BUG 2 case 1: SECURITY INVOKER + correct grants -> PASS. SECURITY
    DEFINER is not required by the approved design."""
    monkeypatch.setattr(supabase, "_SupabaseMgmtClient", lambda token: _rpc_client(False, ["service_role"]))
    result = supabase.check_rpc_security("fake-token")
    assert result.status == Status.PASS


def test_rpc_security_invoker_anon_execute_fails(monkeypatch):
    """BUG 2 case 2: SECURITY INVOKER + anon EXECUTE -> FAIL."""
    monkeypatch.setattr(supabase, "_SupabaseMgmtClient", lambda token: _rpc_client(False, ["service_role", "anon"]))
    result = supabase.check_rpc_security("fake-token")
    assert result.status == Status.FAIL
    assert "anon" in result.summary


def test_rpc_security_invoker_authenticated_execute_fails(monkeypatch):
    """BUG 2 case 3: SECURITY INVOKER + authenticated EXECUTE -> FAIL."""
    monkeypatch.setattr(supabase, "_SupabaseMgmtClient", lambda token: _rpc_client(False, ["service_role", "authenticated"]))
    result = supabase.check_rpc_security("fake-token")
    assert result.status == Status.FAIL
    assert "authenticated" in result.summary


def test_rpc_security_invoker_missing_service_role_fails(monkeypatch):
    """BUG 2 case 4: SECURITY INVOKER + service_role missing -> FAIL."""
    monkeypatch.setattr(supabase, "_SupabaseMgmtClient", lambda token: _rpc_client(False, []))
    result = supabase.check_rpc_security("fake-token")
    assert result.status == Status.FAIL
    assert "service_role" in result.summary


def test_rpc_security_definer_true_with_correct_privileges_pass(monkeypatch):
    """BUG 2 case 5: correct privileges but SECURITY DEFINER true -> PASS
    (stronger-than-required mode, not a failure)."""
    monkeypatch.setattr(supabase, "_SupabaseMgmtClient", lambda token: _rpc_client(True, ["service_role"]))
    result = supabase.check_rpc_security("fake-token")
    assert result.status == Status.PASS
