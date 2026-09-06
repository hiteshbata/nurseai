"""Phase 5.4 Step 1 live QA verification -- institution status management
(POST /admin/institutions/{id}/status, PATCH's status field, and the
authorization fallout of a suspended institution).

Drives the running QA-mode backend (BACKEND_URL) through the real HTTP API
against the QA Supabase project ONLY (wpowzyyzhrxdqujrvxdq), using only
disposable fixtures, then prints a pass/fail summary and cleans up every row
it created. Same pattern as qa_verify_phase5_3b_staff_assignment.py.

Usage:
    cd backend
    ENVIRONMENT=qa .venv-qa/Scripts/python.exe -u scripts/qa_verify_phase5_4_status_management.py
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "qa")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.core.config import settings
from app.core.supabase import get_supabase, get_auth_client

BACKEND_URL = os.environ.get("QA_VERIFY_BACKEND_URL", "http://127.0.0.1:8010")
RUN_TAG = uuid.uuid4().hex[:8]

assert "wpowzyyzhrxdqujrvxdq" in settings.SUPABASE_URL, (
    f"Refusing to run: SUPABASE_URL is not the QA project -- got {settings.SUPABASE_URL!r}"
)
assert "lgwaiwasnjjohqkeizdz" not in settings.SUPABASE_URL, "Refusing to run against production project ref"
assert settings.ENVIRONMENT == "qa", f"Refusing to run: ENVIRONMENT={settings.ENVIRONMENT!r}, expected 'qa'"

service = get_supabase()
anon = get_auth_client()

PASSWORD = "QaVerify!2026x"
FIXTURE_DOMAIN = "mailinator.com"  # example.com is hard-rejected by QA mail relay (Phase 5.3b finding)

created_users: list[tuple[str, str, str]] = []          # (label, user_id, email)
created_institutions: list[tuple[str, str]] = []          # (label, institution_id)
results: list[tuple[str, str, str]] = []


def log(msg):
    print(msg, flush=True)


def check(name: str, cond: bool, detail: str = ""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    log(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))


def fresh_email(label: str) -> str:
    return f"qa-p54-{label}-{RUN_TAG}@{FIXTURE_DOMAIN}"


def get_or_create_user(label: str, role: str | None, confirm: bool = True) -> tuple[str, str]:
    email = fresh_email(label)
    resp = service.auth.admin.create_user({"email": email, "password": PASSWORD, "email_confirm": confirm})
    user_id = resp.user.id
    created_users.append((label, user_id, email))
    if role:
        service.table("user_roles").upsert({"user_id": user_id, "role": role}, on_conflict="user_id").execute()
    log(f"  created user {label}: {email} ({user_id}) role={role}")
    return user_id, email


def login(email: str) -> str:
    resp = anon.auth.sign_in_with_password({"email": email, "password": PASSWORD})
    return resp.session.access_token


def call(method: str, path: str, token: str | None = None, json=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.request(method, f"{BACKEND_URL}{path}", headers=headers, json=json, timeout=30)


def audit_rows(action: str, target_id: str) -> list[dict]:
    return (
        service.table("audit_log").select("action, target_id, target_label, detail, created_at")
        .eq("action", action).eq("target_id", target_id).order("created_at").execute()
    ).data or []


def institution_row(institution_id: str) -> dict:
    return service.table("institutions").select("*").eq("id", institution_id).execute().data[0]


def member_row(institution_id: str, user_id: str) -> dict | None:
    rows = (
        service.table("institution_members").select("*")
        .eq("institution_id", institution_id).eq("user_id", user_id).execute()
    ).data or []
    return rows[0] if rows else None


def create_institution(admin_token: str, label: str, slug_suffix: str, quota: int = 10) -> str:
    slug = f"qa-p54-{slug_suffix}-{RUN_TAG}"
    r = call("POST", "/admin/institutions", admin_token, json={
        "name": f"QA Phase 5.4 {label} {RUN_TAG}",
        "slug": slug,
        "contact_email": f"qa-p54-contact-{slug_suffix}-{RUN_TAG}@example.com",
        "status": "active",
        "modules": ["speaking"],
        "speaking_sessions_per_month": quota,
    })
    check(f"setup: create institution '{label}' -> 201", r.status_code == 201, f"status={r.status_code} body={r.text[:200]}")
    body = r.json() if r.status_code == 201 else {}
    check(f"setup: '{label}' status=active", body.get("status") == "active", str(body))
    check(f"setup: '{label}' has speaking module", "speaking" in body.get("enabled_modules", []), str(body))
    iid = body["id"]
    created_institutions.append((label, iid))
    return iid


def assign_staff(admin_token: str, institution_id: str, email: str, role: str = "institution_admin") -> None:
    r = call("POST", f"/admin/institutions/{institution_id}/staff", admin_token, json={"email": email, "role": role})
    check(f"setup: staff-assign {email} as {role} -> 2xx", r.status_code in (200, 201), f"status={r.status_code} body={r.text[:200]}")


def main():
    try:
        run_all_groups()
    except Exception as e:
        import traceback
        log(f"\n!!! UNEXPECTED EXCEPTION, aborting remaining groups but still cleaning up: {e}")
        traceback.print_exc()
        check("run completed without an unhandled exception", False, str(e))
    return finish()


def run_all_groups():
    log("=== Fixture setup: staff users (owner/admin/analyst/support/plain) ===")
    owner_id, owner_email = get_or_create_user("owner", "owner")
    admin_id, admin_email = get_or_create_user("admin", "admin")
    analyst_id, analyst_email = get_or_create_user("analyst", "analyst")
    support_id, support_email = get_or_create_user("support", "support")
    plain_id, plain_email = get_or_create_user("plainuser", None)
    owner_token = login(owner_email)
    admin_token = login(admin_email)
    analyst_token = login(analyst_email)
    support_token = login(support_email)
    plain_token = login(plain_email)

    # ════════════════════════════════════════════════════════════════════
    log("\n=== STEP 1: create disposable institution ===")
    inst = create_institution(admin_token, "primary", "primary")

    log("\n=== STEP 2: create disposable institution admin ===")
    ia_id, ia_email = get_or_create_user("inst-admin", None, confirm=True)
    assign_staff(admin_token, inst, ia_email, "institution_admin")
    row = member_row(inst, ia_id)
    check("STEP2: membership active institution_admin", bool(row) and row.get("status") == "active" and row.get("role") == "institution_admin", str(row))
    ia_token = login(ia_email)
    r = call("GET", "/institution/overview", ia_token)
    check("STEP2: institution admin can access /institution/overview", r.status_code == 200, f"status={r.status_code}")
    r = call("GET", "/sessions/usage", ia_token)
    check("STEP2: Speaking access works (institution_modules has speaking, limit=10)",
          r.status_code == 200 and "speaking" in r.json().get("institution_modules", []) and r.json().get("sessions_limit") == 10,
          f"status={r.status_code} body={r.text[:200]}")

    # ════════════════════════════════════════════════════════════════════
    log("\n=== STEP 3: suspend ===")
    r = call("POST", f"/admin/institutions/{inst}/status", admin_token, json={"status": "suspended"})
    check("STEP3: POST status=suspended -> 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    check("STEP3: response reflects status=suspended", r.status_code == 200 and r.json().get("status") == "suspended", str(r.json() if r.status_code == 200 else r.text[:200]))
    check("STEP3: institutions.status == suspended", institution_row(inst)["status"] == "suspended", "")

    audit1 = audit_rows("institution_status_changed", inst)
    check("STEP3: exactly one institution_status_changed audit row", len(audit1) == 1, str(audit1))
    if audit1:
        check("STEP3: audit detail old_status=active new_status=suspended",
              audit1[0]["detail"] == {"old_status": "active", "new_status": "suspended"}, str(audit1[0]))

    for path in ("/institution/overview", "/institution/students", "/institution/invites"):
        r = call("GET", path, ia_token)
        check(f"STEP3: GET {path} -> 403 after suspend", r.status_code == 403, f"status={r.status_code} body={r.text[:150]}")

    r = call("GET", "/sessions/usage", ia_token)
    check("STEP3: /sessions/usage still 200 (falls back to B2C)", r.status_code == 200, f"status={r.status_code}")
    usage = r.json() if r.status_code == 200 else {}
    check("STEP3: institution_modules empty (speaking access denied)", usage.get("institution_modules") == [], str(usage.get("institution_modules")))
    check("STEP3: is_institution_member == False", usage.get("is_institution_member") is False, str(usage.get("is_institution_member")))
    check("STEP3: sessions_limit no longer institution quota (10)", usage.get("sessions_limit") != 10, str(usage.get("sessions_limit")))
    check("STEP3: institution_admin_role no longer surfaced", usage.get("institution_admin_role") is None, str(usage.get("institution_admin_role")))

    # ════════════════════════════════════════════════════════════════════
    log("\n=== STEP 4: verify no-op suspend ===")
    r = call("POST", f"/admin/institutions/{inst}/status", admin_token, json={"status": "suspended"})
    check("STEP4: repeat status=suspended -> 200", r.status_code == 200, f"status={r.status_code}")
    check("STEP4: no database status change (still suspended)", institution_row(inst)["status"] == "suspended", "")
    audit2 = audit_rows("institution_status_changed", inst)
    check("STEP4: no new audit row (still exactly one)", len(audit2) == 1, str(audit2))

    # ════════════════════════════════════════════════════════════════════
    log("\n=== STEP 5: reactivate ===")
    r = call("POST", f"/admin/institutions/{inst}/status", admin_token, json={"status": "active"})
    check("STEP5: POST status=active -> 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    check("STEP5: institutions.status == active", institution_row(inst)["status"] == "active", "")

    audit3 = audit_rows("institution_status_changed", inst)
    check("STEP5: exactly one NEW audit row (two total)", len(audit3) == 2, str(audit3))
    if len(audit3) == 2:
        check("STEP5: second audit detail old_status=suspended new_status=active",
              audit3[1]["detail"] == {"old_status": "suspended", "new_status": "active"}, str(audit3[1]))

    for path in ("/institution/overview", "/institution/students", "/institution/invites"):
        r = call("GET", path, ia_token)
        check(f"STEP5: GET {path} -> 200 after reactivate", r.status_code == 200, f"status={r.status_code} body={r.text[:150]}")

    r = call("GET", "/sessions/usage", ia_token)
    usage = r.json() if r.status_code == 200 else {}
    check("STEP5: Speaking + quota restored (speaking in modules, limit=10)",
          r.status_code == 200 and "speaking" in usage.get("institution_modules", []) and usage.get("sessions_limit") == 10,
          f"status={r.status_code} body={r.text[:200]}")

    # ════════════════════════════════════════════════════════════════════
    log("\n=== STEP 6: PATCH compatibility ===")
    r = call("PATCH", f"/admin/institutions/{inst}", admin_token, json={"status": "suspended"})
    check("STEP6a: PATCH status-only active->suspended -> 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    check("STEP6a: institutions.status == suspended", institution_row(inst)["status"] == "suspended", "")
    audit4 = audit_rows("institution_status_changed", inst)
    check("STEP6a: one more status audit row (three total)", len(audit4) == 3, str(audit4))
    updated4 = audit_rows("institution_updated", inst)
    check("STEP6a: no institution_updated audit fired (status-only PATCH)", len(updated4) == 0, str(updated4))

    r = call("PATCH", f"/admin/institutions/{inst}", admin_token, json={"status": "suspended"})
    check("STEP6b: PATCH same status again -> 200", r.status_code == 200, f"status={r.status_code}")
    audit5 = audit_rows("institution_status_changed", inst)
    check("STEP6b: no new status audit row (still three)", len(audit5) == 3, str(audit5))

    new_name = f"QA Phase 5.4 renamed {RUN_TAG}"
    r = call("PATCH", f"/admin/institutions/{inst}", admin_token, json={"status": "active", "name": new_name})
    check("STEP6c: PATCH status+name -> 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    body = r.json() if r.status_code == 200 else {}
    check("STEP6c: name updated in response", body.get("name") == new_name, str(body))
    check("STEP6c: status updated in response", body.get("status") == "active", str(body))
    check("STEP6c: institutions row reflects both name and status", institution_row(inst)["name"] == new_name and institution_row(inst)["status"] == "active", "")
    audit6 = audit_rows("institution_status_changed", inst)
    check("STEP6c: one more status audit row (four total)", len(audit6) == 4, str(audit6))
    updated6 = audit_rows("institution_updated", inst)
    check("STEP6c: exactly one institution_updated audit row (name change)", len(updated6) == 1, str(updated6))
    if updated6:
        check("STEP6c: institution_updated detail carries only the name field", updated6[0]["detail"] == {"name": new_name}, str(updated6[0]))

    # ════════════════════════════════════════════════════════════════════
    log("\n=== STEP 7: authorization ===")
    r = call("POST", f"/admin/institutions/{inst}/status", owner_token, json={"status": "suspended"})
    check("STEP7: owner can change status -> 200", r.status_code == 200, f"status={r.status_code}")
    r = call("POST", f"/admin/institutions/{inst}/status", admin_token, json={"status": "active"})
    check("STEP7: admin can change status (reset) -> 200", r.status_code == 200, f"status={r.status_code}")

    r = call("POST", f"/admin/institutions/{inst}/status", analyst_token, json={"status": "suspended"})
    check("STEP7: analyst -> 403", r.status_code == 403, f"status={r.status_code}")
    r = call("POST", f"/admin/institutions/{inst}/status", support_token, json={"status": "suspended"})
    check("STEP7: support -> 403", r.status_code == 403, f"status={r.status_code}")
    r = call("POST", f"/admin/institutions/{inst}/status", plain_token, json={"status": "suspended"})
    check("STEP7: normal user -> 403", r.status_code == 403, f"status={r.status_code}")

    r = call("POST", f"/admin/institutions/{inst}/status", ia_token, json={"status": "suspended"})
    check("STEP7: institution_admin without staff role -> 403", r.status_code == 403, f"status={r.status_code}")

    check("STEP7: institution status unaffected by rejected 403 attempts (still active)", institution_row(inst)["status"] == "active", "")

    # ════════════════════════════════════════════════════════════════════
    log("\n=== STEP 8: unknown / invalid ===")
    r = call("POST", "/admin/institutions/00000000-0000-0000-0000-000000000000/status", admin_token, json={"status": "suspended"})
    check("STEP8: unknown institution id -> 404", r.status_code == 404, f"status={r.status_code}")

    r = call("POST", f"/admin/institutions/{inst}/status", admin_token, json={"status": "deleted"})
    check("STEP8: invalid status value -> 422", r.status_code == 422, f"status={r.status_code}")
    r = call("POST", f"/admin/institutions/{inst}/status", admin_token, json={"status": "pending"})
    check("STEP8: another invalid status value -> 422", r.status_code == 422, f"status={r.status_code}")

    # ════════════════════════════════════════════════════════════════════
    log("\n=== STEP 9: B2C regression ===")
    b2c_id, b2c_email = get_or_create_user("b2c-user", None, confirm=True)
    b2c_token = login(b2c_email)
    r = call("GET", "/sessions/usage", b2c_token)
    before_usage = r.json() if r.status_code == 200 else {}
    check("STEP9: B2C user baseline /sessions/usage -> 200", r.status_code == 200, f"status={r.status_code}")
    check("STEP9: B2C user has no institution membership", before_usage.get("is_institution_member") is False, str(before_usage))

    r = call("POST", f"/admin/institutions/{inst}/status", admin_token, json={"status": "suspended"})
    check("STEP9: suspend disposable institution (side-effect check)", r.status_code == 200, f"status={r.status_code}")

    r = call("GET", "/sessions/usage", b2c_token)
    after_usage = r.json() if r.status_code == 200 else {}
    check("STEP9: B2C user /sessions/usage unaffected by unrelated institution suspend",
          r.status_code == 200 and after_usage.get("sessions_limit") == before_usage.get("sessions_limit")
          and after_usage.get("is_institution_member") is False,
          f"before={before_usage} after={after_usage}")

    r = call("POST", f"/admin/institutions/{inst}/status", admin_token, json={"status": "active"})
    check("STEP9: reset disposable institution back to active", r.status_code == 200, f"status={r.status_code}")


def finish():
    log("\n=== Summary (pre-cleanup) ===")
    failed = [x for x in results if x[0] == "FAIL"]
    log(f"{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        log("FAILURES:")
        for status, name, detail in failed:
            log(f"  - {name}: {detail}")

    log("\n=== Cleanup ===")
    for label, iid in created_institutions:
        service.table("institution_members").delete().eq("institution_id", iid).execute()
        service.table("institution_modules").delete().eq("institution_id", iid).execute()
        service.table("audit_log").delete().eq("target_id", iid).execute()
        service.table("institutions").delete().eq("id", iid).execute()
        log(f"  deleted institution {label}: {iid}")
    for label, uid, email in created_users:
        try:
            service.table("audit_log").delete().eq("target_label", email).execute()
        except Exception:
            pass
        try:
            service.table("user_profiles").delete().eq("user_id", uid).execute()
            service.table("user_roles").delete().eq("user_id", uid).execute()
            service.table("users").delete().eq("id", uid).execute()
        except Exception as e:
            log(f"  WARN could not clean mirror rows for {label} ({email}): {e}")
        try:
            service.auth.admin.delete_user(uid)
            log(f"  deleted user {label}: {email}")
        except Exception as e:
            log(f"  WARN could not delete user {label} ({email}): {e}")

    remaining_inst = service.table("institutions").select("id").in_(
        "id", [iid for _, iid in created_institutions]
    ).execute().data if created_institutions else []
    check("cleanup: no disposable institution rows remain", remaining_inst == [], str(remaining_inst))

    remaining_members = service.table("institution_members").select("id").in_(
        "institution_id", [iid for _, iid in created_institutions]
    ).execute().data if created_institutions else []
    check("cleanup: no disposable membership rows remain", remaining_members == [], str(remaining_members))

    remaining_audit = service.table("audit_log").select("id").in_(
        "target_id", [iid for _, iid in created_institutions]
    ).execute().data if created_institutions else []
    check("cleanup: no disposable audit rows remain", remaining_audit == [], str(remaining_audit))

    remaining_mirrors = service.table("users").select("id").in_(
        "id", [uid for _, uid, _ in created_users]
    ).execute().data if created_users else []
    check("cleanup: no disposable public.users mirror rows remain", remaining_mirrors == [], str(remaining_mirrors))

    log("\n=== Final tally ===")
    final_failed = [x for x in results if x[0] == "FAIL"]
    log(f"{len(results) - len(final_failed)}/{len(results)} checks passed")
    if final_failed:
        log("FAILURES:")
        for status, name, detail in final_failed:
            log(f"  - {name}: {detail}")
    return 1 if final_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
