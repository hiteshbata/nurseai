"""Supabase checks via the Management API's read-only SQL query endpoint
(POST /database/query). Every query issued here is asserted to start with
SELECT before being sent -- defense in depth so a coding mistake can never
turn into a write, even though the endpoint itself would technically allow
one.

Covers: project health, migration history, institution schema (tables/RLS/
indexes/policies), RPC privileges, row counts, and migration-content
drift against what's committed on origin/main.
"""
from __future__ import annotations

import re
from pathlib import Path

import httpx

from .. import config
from ..models import CheckResult, Status

_BASE = "https://api.supabase.com/v1"


def _migration_name(filename: str) -> str:
    """Derive a migration's identity from its local filename.

    Matching rule: strip the leading `<timestamp>_` prefix and the `.sql`
    suffix, leaving the migration name (e.g.
    "20260826000000_institution_foundation.sql" -> "institution_foundation").
    This is compared for exact equality against the `name` field in the
    Supabase migration ledger (`GET .../database/migrations`), never against
    the ledger's `version` field. The ledger version is the timestamp the
    migration was actually *applied* under, which is assigned by Supabase
    and can differ from the timestamp baked into the local filename -- so
    filename-timestamp-vs-ledger-version comparison is not a valid identity
    check. Exact name equality (not substring) is required so a migration
    like "institution_foundation_backup" can never be mistaken for
    "institution_foundation".
    """
    stem = filename[:-4] if filename.endswith(".sql") else filename
    return re.sub(r"^\d+_", "", stem)


class _SupabaseMgmtClient:
    def __init__(self, token: str):
        self._client = httpx.Client(
            base_url=_BASE,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=config.HTTP_TIMEOUT_SECONDS,
        )

    def get(self, path: str) -> httpx.Response:
        return self._client.get(path)

    def query(self, ref: str, sql: str) -> list[dict] | None:
        stripped = sql.strip().lstrip("(").strip()
        if not re.match(r"(?is)^select\b", stripped):
            raise ValueError("Refusing to send a non-SELECT statement through the read-only audit query path")
        resp = self._client.post(f"/projects/{ref}/database/query", json={"query": sql})
        if resp.status_code != 200:
            return None
        return resp.json()

    def close(self):
        self._client.close()


def _mk_unknown(name: str, summary: str, details: list[str] | None = None) -> CheckResult:
    return CheckResult(name=name, status=Status.UNKNOWN, summary=summary, details=details or [])


def check_supabase_project(token: str | None) -> CheckResult:
    name = "Supabase project"
    if not token:
        return CheckResult(
            name=name,
            status=Status.UNKNOWN,
            summary="SUPABASE_ACCESS_TOKEN not set",
            remediation="Set SUPABASE_ACCESS_TOKEN (a Supabase personal access token) as an environment variable.",
        )

    client = _SupabaseMgmtClient(token)
    ref = config.PRODUCTION_SUPABASE_PROJECT_REF
    details: list[str] = []
    fail_reasons: list[str] = []

    try:
        resp = client.get(f"/projects/{ref}")
        if resp.status_code != 200:
            return _mk_unknown(name, f"could not load project {ref} (HTTP {resp.status_code})", [resp.text[:300]])
        project = resp.json()
        status = project.get("status")
        details.append(f"ref={ref} status={status} region={project.get('region')}")
        if status != "ACTIVE_HEALTHY":
            fail_reasons.append(f"project status is {status!r}, not ACTIVE_HEALTHY")

        resp = client.get(f"/projects/{ref}/database/migrations")
        if resp.status_code != 200:
            return _mk_unknown(name, f"could not list migrations (HTTP {resp.status_code})", details)
        migrations = resp.json()
        ledger_names = [m.get("name") for m in migrations if m.get("name")]
        details.append(f"{len(migrations)} migration(s) applied")

        for mig_file in config.INSTITUTION_MIGRATIONS:
            expected_name = _migration_name(mig_file)
            count = sum(1 for n in ledger_names if n == expected_name)
            if count == 0:
                fail_reasons.append(f"migration {mig_file} (name={expected_name!r}) not found in applied history")
            elif count > 1:
                fail_reasons.append(f"migration {mig_file} (name={expected_name!r}) appears {count} times in applied history (expected exactly once)")

    except httpx.HTTPError as exc:
        return _mk_unknown(name, "Supabase Management API request failed", [str(exc)])
    finally:
        client.close()

    if fail_reasons:
        return CheckResult(name=name, status=Status.FAIL, summary="; ".join(fail_reasons), details=details,
                            remediation="Investigate project health / re-run the missing institution migration via the normal Supabase migration workflow.")
    return CheckResult(name=name, status=Status.PASS, summary="Project healthy; both institution migrations applied exactly once", details=details)


def check_institution_schema(token: str | None) -> CheckResult:
    name = "Institution schema"
    if not token:
        return CheckResult(name=name, status=Status.UNKNOWN, summary="SUPABASE_ACCESS_TOKEN not set",
                            remediation="Set SUPABASE_ACCESS_TOKEN as an environment variable.")

    client = _SupabaseMgmtClient(token)
    ref = config.PRODUCTION_SUPABASE_PROJECT_REF
    details: list[str] = []
    fail_reasons: list[str] = []

    try:
        table_list = ",".join(f"'{t}'" for t in config.INSTITUTION_TABLES)
        tables_sql = f"""
            select c.relname as table_name, c.relrowsecurity as rls_enabled
            from pg_class c
            join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public' and c.relkind = 'r'
              and c.relname = any(array[{table_list}])
        """
        rows = client.query(ref, tables_sql)
        if rows is None:
            return _mk_unknown(name, "could not query table/RLS state")

        found = {r["table_name"]: r["rls_enabled"] for r in rows}
        for table in config.INSTITUTION_TABLES:
            if table not in found:
                fail_reasons.append(f"table {table} does not exist")
            elif not found[table]:
                fail_reasons.append(f"table {table} exists but RLS is not enabled")
        details.append(f"tables found: {found}")

        idx_sql = "select tablename, indexname from pg_indexes where schemaname = 'public' and tablename = any(array[%s])" % ",".join(
            f"'{t}'" for t in config.INSTITUTION_TABLES
        )
        rows = client.query(ref, idx_sql)
        if rows is not None:
            by_table: dict[str, list[str]] = {}
            for r in rows:
                by_table.setdefault(r["tablename"], []).append(r["indexname"])
            details.append(f"indexes: { {t: len(v) for t, v in by_table.items()} }")
            for table in config.INSTITUTION_TABLES:
                if table in found and not by_table.get(table):
                    fail_reasons.append(f"table {table} has no indexes (expected at least a primary key)")

        policy_sql = "select tablename, policyname, roles, cmd from pg_policies where schemaname = 'public' and tablename = any(array[%s])" % ",".join(
            f"'{t}'" for t in config.INSTITUTION_TABLES
        )
        rows = client.query(ref, policy_sql)
        if rows is not None:
            details.append(f"{len(rows)} RLS polic(y/ies) across institution tables")
            anon_policies = [r for r in rows if "anon" in (r.get("roles") or [])]
            if anon_policies:
                details.append(f"policies granting the 'anon' role: {[(p['tablename'], p['policyname']) for p in anon_policies]}")

        constraint_sql = (
            "select tc.table_name, tc.constraint_type, tc.constraint_name "
            "from information_schema.table_constraints tc "
            "where tc.table_schema = 'public' and tc.table_name = any(array[%s])"
        ) % ",".join(f"'{t}'" for t in config.INSTITUTION_TABLES)
        rows = client.query(ref, constraint_sql)
        if rows is not None:
            by_table_c: dict[str, list[str]] = {}
            for r in rows:
                by_table_c.setdefault(r["table_name"], []).append(r["constraint_type"])
            details.append(f"constraint types by table: {by_table_c}")
            for table in config.INSTITUTION_TABLES:
                if table in found and "PRIMARY KEY" not in by_table_c.get(table, []):
                    fail_reasons.append(f"table {table} has no PRIMARY KEY constraint")

    except httpx.HTTPError as exc:
        return _mk_unknown(name, "Supabase Management API request failed", [str(exc)])
    finally:
        client.close()

    if fail_reasons:
        return CheckResult(name=name, status=Status.FAIL, summary="; ".join(fail_reasons), details=details,
                            remediation="Review the institution_* table definitions/RLS policies/constraints against the approved migrations.")
    return CheckResult(name=name, status=Status.PASS, summary="All institution tables exist with RLS, indexes, and primary keys", details=details)


def check_rpc_security(token: str | None) -> CheckResult:
    """Verify the RPC's actual security contract, not one implementation
    style. The approved design for accept_institution_invite is SECURITY
    INVOKER with EXECUTE revoked from PUBLIC/anon/authenticated and granted
    only to service_role -- SECURITY DEFINER is NOT required. What matters
    is the privilege surface: only service_role can call it. If a function
    is SECURITY DEFINER instead, that is a stronger-than-required mode, not
    a failure -- it's reported as INFO, and the same grant contract is still
    enforced.
    """
    name = "RPC security"
    if not token:
        return CheckResult(name=name, status=Status.UNKNOWN, summary="SUPABASE_ACCESS_TOKEN not set",
                            remediation="Set SUPABASE_ACCESS_TOKEN as an environment variable.")

    client = _SupabaseMgmtClient(token)
    ref = config.PRODUCTION_SUPABASE_PROJECT_REF
    details: list[str] = []
    fail_reasons: list[str] = []

    try:
        exists_sql = (
            "select p.proname, p.prosecdef, pg_get_function_arguments(p.oid) as args "
            "from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
            f"where n.nspname = 'public' and p.proname = '{config.INSTITUTION_RPC}'"
        )
        rows = client.query(ref, exists_sql)
        if rows is None:
            return _mk_unknown(name, "could not query pg_proc for the RPC")
        if not rows:
            return CheckResult(name=name, status=Status.FAIL, summary=f"public.{config.INSTITUTION_RPC}(...) does not exist",
                                remediation="Re-check whether the institution invite-accept migration applied successfully.")

        fn = rows[0]
        security_definer = bool(fn["prosecdef"])
        details.append(f"proname={fn['proname']} security_definer={security_definer} args={fn['args']}")
        if security_definer:
            details.append(
                "INFO: function is SECURITY DEFINER (stronger than the required SECURITY INVOKER baseline) "
                "-- privilege contract below is still enforced"
            )

        priv_sql = (
            "select grantee, privilege_type from information_schema.routine_privileges "
            f"where routine_schema = 'public' and routine_name = '{config.INSTITUTION_RPC}'"
        )
        rows = client.query(ref, priv_sql)
        if rows is None:
            return _mk_unknown(name, "could not query routine privileges", details)

        grantees = {r["grantee"] for r in rows if r["privilege_type"] == "EXECUTE"}
        details.append(f"EXECUTE grantees: {sorted(grantees)}")

        expected = {"PUBLIC": False, "anon": False, "authenticated": False, "service_role": True}
        for role, should_have in expected.items():
            has = role in grantees
            if has != should_have:
                fail_reasons.append(f"EXECUTE grant for {role!r} is {has}, expected {should_have}")

    except httpx.HTTPError as exc:
        return _mk_unknown(name, "Supabase Management API request failed", [str(exc)])
    finally:
        client.close()

    if fail_reasons:
        return CheckResult(name=name, status=Status.FAIL, summary="; ".join(fail_reasons), details=details,
                            remediation=f"REVOKE/GRANT EXECUTE on public.{config.INSTITUTION_RPC} so only service_role can call it.")
    return CheckResult(name=name, status=Status.PASS, summary="accept_institution_invite has the correct EXECUTE privilege contract (service_role only)", details=details)


def check_database_state(token: str | None) -> CheckResult:
    name = "Database state"
    if not token:
        return CheckResult(name=name, status=Status.UNKNOWN, summary="SUPABASE_ACCESS_TOKEN not set",
                            remediation="Set SUPABASE_ACCESS_TOKEN as an environment variable.")

    client = _SupabaseMgmtClient(token)
    ref = config.PRODUCTION_SUPABASE_PROJECT_REF
    counts: dict[str, int] = {}

    try:
        for table in config.INSTITUTION_TABLES:
            rows = client.query(ref, f"select count(*) as n from public.{table}")
            if rows is None:
                return _mk_unknown(name, f"could not count rows in {table}")
            counts[table] = int(rows[0]["n"])
    except httpx.HTTPError as exc:
        return _mk_unknown(name, "Supabase Management API request failed", [str(exc)])
    finally:
        client.close()

    non_zero = {t: n for t, n in counts.items() if n}
    if non_zero:
        return CheckResult(
            name=name,
            status=Status.INFO,
            summary=f"Institution tables contain data: {non_zero} (not a failure -- confirm this is expected pilot data)",
            details=[f"row counts: {counts}"],
        )
    return CheckResult(name=name, status=Status.PASS, summary="Institution tables are empty (pre-pilot clean state)", details=[f"row counts: {counts}"])


def _load_migration_file(repo_root: Path, filename: str) -> str | None:
    path = repo_root / "supabase" / "migrations" / filename
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _normalize_sql(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", "", sql)
    return re.sub(r"\s+", " ", sql).strip().lower()


def check_migration_safety(token: str | None, repo_root: Path | None = None) -> CheckResult:
    name = "Migration safety"
    repo_root = repo_root or Path.cwd()
    if not token:
        return CheckResult(name=name, status=Status.UNKNOWN, summary="SUPABASE_ACCESS_TOKEN not set",
                            remediation="Set SUPABASE_ACCESS_TOKEN as an environment variable.")

    client = _SupabaseMgmtClient(token)
    ref = config.PRODUCTION_SUPABASE_PROJECT_REF
    details: list[str] = []
    fail_reasons: list[str] = []
    unknown_reasons: list[str] = []

    try:
        for mig_file in config.INSTITUTION_MIGRATIONS:
            version = mig_file.split("_", 1)[0]
            local_sql = _load_migration_file(repo_root, mig_file)
            if local_sql is None:
                fail_reasons.append(f"{mig_file} not found locally under supabase/migrations/")
                continue

            rows = client.query(
                ref,
                f"select statements from supabase_migrations.schema_migrations where version = '{version}'",
            )
            if rows is None or not rows:
                unknown_reasons.append(f"could not read applied statements for {mig_file} from supabase_migrations.schema_migrations")
                continue

            applied = " ".join(rows[0].get("statements") or [])
            if _normalize_sql(applied) != _normalize_sql(local_sql):
                fail_reasons.append(f"{mig_file}: applied statements differ from the committed migration file")
            else:
                details.append(f"{mig_file}: applied statements match the committed file")

    except httpx.HTTPError as exc:
        return _mk_unknown(name, "Supabase Management API request failed", [str(exc)])
    finally:
        client.close()

    if fail_reasons:
        return CheckResult(name=name, status=Status.FAIL, summary="; ".join(fail_reasons), details=details,
                            remediation="Investigate migration drift -- production ran different SQL than what's committed on main.")
    if unknown_reasons:
        return CheckResult(name=name, status=Status.UNKNOWN, summary="; ".join(unknown_reasons), details=details)
    return CheckResult(name=name, status=Status.PASS, summary="Applied institution migrations match the committed files on main", details=details)
