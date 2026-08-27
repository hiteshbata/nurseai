"""
Structural lock-in test (Test 8 in the Phase 1 spec: self-escalation
protection). A normal authenticated user must never be able to change their
own institution role/status/module grants/quota via the client -- verified
by asserting the migration grants the institution tables NO authenticated-role
policies or column grants at all (service-role, which bypasses RLS entirely,
is the only writer). Same convention as user_skill_bridge/skill_relationships/
content_skill_map (see 20260826000000_institution_foundation.sql's header).

This mirrors the structural-invariant tests in test_subscription_lifecycle.py:
it locks a security property already established in the reviewed migration
so a future edit that accidentally adds a client-writable policy breaks a
test instead of silently reopening the self-escalation hole.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "supabase" / "migrations" / "20260826000000_institution_foundation.sql"
)

INSTITUTION_TABLES = (
    "institutions",
    "institution_members",
    "institution_modules",
    "institution_invites",
)


def _migration_sql() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def test_migration_file_exists():
    assert MIGRATION_PATH.exists(), f"expected migration at {MIGRATION_PATH}"


def test_no_policy_or_grant_statements_for_any_institution_table():
    sql = _migration_sql()
    assert "CREATE POLICY" not in sql.upper()
    assert "GRANT " not in sql.upper()
    assert "TO AUTHENTICATED" not in sql.upper()


def test_every_institution_table_has_rls_enabled():
    sql = _migration_sql()
    for table in INSTITUTION_TABLES:
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in sql, (
            f"{table} must have RLS enabled -- entitlement columns "
            "(role/status/enabled/quota) must never be client-writable"
        )


def test_entitlement_columns_have_no_client_default_that_grants_access():
    # role/status default to the LEAST privileged value -- a row a client
    # could theoretically get inserted (it can't, no INSERT grant exists,
    # but this is a defense-in-depth check) never defaults to an elevated
    # role or an already-active/enabled state.
    sql = _migration_sql()
    assert "role text NOT NULL DEFAULT 'student'" in sql
    assert "status text NOT NULL DEFAULT 'invited'" in sql  # institution_members
    assert "enabled boolean NOT NULL DEFAULT false" in sql  # institution_modules


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
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
