"""Phase 5.2 live QA verification -- POST/PATCH /admin/institutions.

Creates disposable auth users + user_roles + one disposable institution in
the QA Supabase project ONLY (wpowzyyzhrxdqujrvxdq), drives the running
QA-mode backend (assumed at BACKEND_URL) through the real HTTP API, then
prints a pass/fail summary and cleans up every row it created.

Usage:
    cd backend
    ENVIRONMENT=qa .venv-qa/Scripts/python.exe -u scripts/qa_verify_phase5_2_admin_institutions.py
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

service = get_supabase()
anon = get_auth_client()

PASSWORD = "QaVerify!2026x"

created_users: list[tuple[str, str, str]] = []   # (label, user_id, email)
created_institutions: list[tuple[str, str]] = []  # (label, institution_id)
results: list[tuple[str, str, str]] = []


def log(msg):
    print(msg, flush=True)


def check(name: str, cond: bool, detail: str = ""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    log(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))


def get_or_create_user(label: str, role: str | None) -> tuple[str, str]:
    email = f"qa-phase52-{label}-{RUN_TAG}@example.com"
    resp = service.auth.admin.create_user({"email": email, "password": PASSWORD, "email_confirm": True})
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


def audit_log_rows(action: str, target_id: str) -> list[dict]:
    return (
        service.table("audit_log").select("action, target_id, detail")
        .eq("action", action).eq("target_id", target_id).execute()
    ).data or []


def main():
    log("=== Fixture setup: staff users ===")
    admin_id, admin_email = get_or_create_user("admin", "admin")
    analyst_id, analyst_email = get_or_create_user("analyst", "analyst")
    support_id, support_email = get_or_create_user("support", "support")
    student_id, student_email = get_or_create_user("student", None)  # role "user" == B2C/student, no user_roles row

    admin_token = login(admin_email)
    analyst_token = login(analyst_email)
    support_token = login(support_email)
    student_token = login(student_email)
    log("  all staff/non-staff fixtures logged in")

    slug = f"qa-phase52-{RUN_TAG}"
    name = f"QA Phase 5.2 Disposable {RUN_TAG}"
    contact_email = f"qa-phase52-contact-{RUN_TAG}@example.com"

    # ── Security: non-admin/owner roles cannot create ──────────────────
    log("\n=== Security: create-authorization ===")
    for label, token in [("analyst", analyst_token), ("support", support_token), ("student/B2C", student_token)]:
        r = call("POST", "/admin/institutions", token, json={
            "name": name, "slug": f"{slug}-{label}", "contact_email": contact_email,
            "modules": ["speaking"], "speaking_sessions_per_month": 10,
        })
        check(f"{label} POST /admin/institutions -> 403", r.status_code == 403, f"status={r.status_code}")

    r = call("GET", "/admin/institutions", None)
    check("unauthenticated GET /admin/institutions -> 401/403", r.status_code in (401, 403), f"status={r.status_code}")

    # ── Create (real create, as admin) ─────────────────────────────────
    log("\n=== Create ===")
    r = call("POST", "/admin/institutions", admin_token, json={
        "name": name, "slug": slug, "contact_email": contact_email,
        "modules": ["speaking"], "speaking_sessions_per_month": 10, "status": "active",
    })
    check("admin POST /admin/institutions -> 201", r.status_code == 201, f"status={r.status_code} body={r.text[:300]}")
    if r.status_code != 201:
        log("FATAL: cannot continue without a created institution")
        return finish()

    body = r.json()
    institution_id = body["id"]
    created_institutions.append(("disposable", institution_id))
    check("response enabled_modules == ['speaking']", body.get("enabled_modules") == ["speaking"], str(body.get("enabled_modules")))
    check("response speaking_sessions_per_month == 10", body.get("speaking_sessions_per_month") == 10, str(body.get("speaking_sessions_per_month")))
    check("response status == active", body.get("status") == "active", str(body.get("status")))

    # DB-level verification
    row = service.table("institutions").select("*").eq("id", institution_id).execute().data
    check("DB institution row exists", bool(row), str(row))
    if row:
        row = row[0]
        check("DB status == active", row.get("status") == "active", str(row.get("status")))
        check("DB speaking_sessions_per_month == 10", row.get("speaking_sessions_per_month") == 10, str(row.get("speaking_sessions_per_month")))

    modules = service.table("institution_modules").select("module, enabled").eq("institution_id", institution_id).execute().data or []
    enabled_modules = sorted(m["module"] for m in modules if m["enabled"])
    check("institution_modules contains exactly ['speaking'] enabled", enabled_modules == ["speaking"], str(modules))

    members = service.table("institution_members").select("*").eq("institution_id", institution_id).execute().data or []
    check("no institution_members row created by institution creation", members == [], str(members))

    r = call("GET", "/admin/institutions", admin_token)
    check("GET /admin/institutions -> 200", r.status_code == 200, f"status={r.status_code}")
    listed_ids = {i["id"] for i in r.json()} if r.status_code == 200 else set()
    check("list contains new institution", institution_id in listed_ids, str(institution_id in listed_ids))

    r = call("GET", f"/admin/institutions/{institution_id}", admin_token)
    check("GET detail -> 200", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        d = r.json()
        check("detail slug/name/quota/modules correct",
              d.get("slug") == slug and d.get("name") == name and d.get("speaking_sessions_per_month") == 10
              and d.get("enabled_modules") == ["speaking"],
              str(d))

    audit_rows = audit_log_rows("institution_created", institution_id)
    check("audit_log has institution_created entry", bool(audit_rows), str(audit_rows))

    # institution_admin (non-staff) cannot reach /admin/institutions at all
    log("\n=== Security: institution_admin (non-staff) blocked ===")
    inst_admin_id, inst_admin_email = get_or_create_user("instadmin", None)
    service.table("institution_members").insert({
        "institution_id": institution_id, "user_id": inst_admin_id, "role": "institution_admin", "status": "active",
    }).execute()
    inst_admin_token = login(inst_admin_email)
    r = call("GET", "/admin/institutions", inst_admin_token)
    check("institution_admin (non-staff) GET /admin/institutions -> 403", r.status_code == 403, f"status={r.status_code}")
    r = call("GET", f"/admin/institutions/{institution_id}", inst_admin_token)
    check("institution_admin (non-staff) GET detail -> 403", r.status_code == 403, f"status={r.status_code}")

    # analyst/support/student cannot create (already checked above); confirm read-only roles CAN read
    log("\n=== Security: analyst/support CAN read (read floor) ===")
    r = call("GET", "/admin/institutions", analyst_token)
    check("analyst GET /admin/institutions -> 200 (read floor)", r.status_code == 200, f"status={r.status_code}")
    r = call("GET", "/admin/institutions", support_token)
    check("support GET /admin/institutions -> 403 (below analyst read floor)", r.status_code == 403, f"status={r.status_code}")

    # ── Validation ──────────────────────────────────────────────────────
    log("\n=== Validation ===")
    r = call("POST", "/admin/institutions", admin_token, json={
        "name": "bad quota", "slug": f"{slug}-badquota", "contact_email": contact_email,
        "modules": ["speaking"], "speaking_sessions_per_month": 0,
    })
    check("quota<=0 -> 422", r.status_code == 422, f"status={r.status_code}")

    r = call("POST", "/admin/institutions", admin_token, json={
        "name": "bad module", "slug": f"{slug}-badmodule", "contact_email": contact_email,
        "modules": ["not_a_real_module"], "speaking_sessions_per_month": 10,
    })
    check("invalid module -> 422", r.status_code == 422, f"status={r.status_code}")
    # Neither of these reaches the RPC (pydantic Literal + Field(gt=0) reject
    # them before the request body is even accepted) -- see atomicity section.

    r = call("POST", "/admin/institutions", admin_token, json={
        "name": "dup slug", "slug": slug, "contact_email": contact_email,
        "modules": ["speaking"], "speaking_sessions_per_month": 10,
    })
    check("duplicate slug -> 409", r.status_code == 409, f"status={r.status_code} body={r.text[:200]}")

    # ── Atomicity ────────────────────────────────────────────────────────
    log("\n=== Atomicity ===")
    before_count = service.table("institutions").select("id", count="exact").execute().count
    r = call("POST", "/admin/institutions", admin_token, json={
        "name": "dup slug atomic check", "slug": slug, "contact_email": contact_email,
        "modules": ["speaking", "reading"], "speaking_sessions_per_month": 10,
    })
    after_count = service.table("institutions").select("id", count="exact").execute().count
    check("duplicate-slug attempt (reaches RPC, aborts inside the transaction) creates no row",
          before_count == after_count, f"before={before_count} after={after_count} status={r.status_code}")
    dup_rows = service.table("institutions").select("id").eq("slug", slug).execute().data
    check("exactly one institution row has this slug (no partial/duplicate)", len(dup_rows) == 1, str(dup_rows))
    check("original institution's modules unaffected by aborted duplicate attempt",
          sorted(m["module"] for m in service.table("institution_modules").select("module, enabled").eq("institution_id", institution_id).eq("enabled", True).execute().data) == ["speaking"],
          "unexpected module drift")

    # ── PATCH ────────────────────────────────────────────────────────────
    log("\n=== PATCH ===")
    new_email = f"qa-phase52-patched-{RUN_TAG}@example.com"
    r = call("PATCH", f"/admin/institutions/{institution_id}", admin_token, json={
        "name": name + " Patched",
        "logo_url": "https://example.com/logo.png",
        "contact_email": new_email,
        "modules": ["speaking", "reading"],
        "speaking_sessions_per_month": 25,
    })
    check("PATCH -> 200", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")

    r = call("GET", f"/admin/institutions/{institution_id}", admin_token)
    d = r.json() if r.status_code == 200 else {}
    check("PATCH persisted: name", d.get("name") == name + " Patched", str(d.get("name")))
    check("PATCH persisted: logo_url", d.get("logo_url") == "https://example.com/logo.png", str(d.get("logo_url")))
    check("PATCH persisted: contact_email", d.get("contact_email") == new_email, str(d.get("contact_email")))
    check("PATCH persisted: modules == ['reading','speaking']", d.get("enabled_modules") == ["reading", "speaking"], str(d.get("enabled_modules")))
    check("PATCH persisted: quota == 25", d.get("speaking_sessions_per_month") == 25, str(d.get("speaking_sessions_per_month")))

    audit_updated = audit_log_rows("institution_updated", institution_id)
    check("audit_log has institution_updated entry", bool(audit_updated), str(audit_updated))
    audit_quota = audit_log_rows("institution_quota_changed", institution_id)
    check("audit_log has institution_quota_changed entry", bool(audit_quota), str(audit_quota))
    audit_module = audit_log_rows("institution_module_changed", institution_id)
    check("audit_log has institution_module_changed entry (reading enabled)", bool(audit_module), str(audit_module))

    # client-supplied institution_id in PATCH body must be ignored / not accepted
    log("\n=== PATCH: path id authoritative ===")
    other_label, other_id = created_institutions[0]
    r = call("PATCH", f"/admin/institutions/{institution_id}", admin_token, json={
        "institution_id": "00000000-0000-0000-0000-000000000000",
        "name": name + " Patched Again",
    })
    check("PATCH with body institution_id -> 200 (extra field ignored, not 422)", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    r2 = call("GET", f"/admin/institutions/{institution_id}", admin_token)
    check("target institution (path id) is the one actually updated", r2.status_code == 200 and r2.json().get("name") == name + " Patched Again", str(r2.json() if r2.status_code == 200 else r2.text))
    ghost = service.table("institutions").select("id").eq("id", "00000000-0000-0000-0000-000000000000").execute().data
    check("body institution_id (all-zero uuid) was not used as a target -- no such row exists", ghost == [], str(ghost))

    # PATCH validation
    log("\n=== PATCH validation ===")
    r = call("PATCH", f"/admin/institutions/{institution_id}", admin_token, json={"speaking_sessions_per_month": 0})
    check("PATCH quota<=0 -> 422", r.status_code == 422, f"status={r.status_code}")
    r = call("PATCH", f"/admin/institutions/{institution_id}", admin_token, json={"modules": ["not_a_real_module"]})
    check("PATCH invalid module -> 422", r.status_code == 422, f"status={r.status_code}")

    # duplicate slug on PATCH
    second_slug = f"{slug}-second"
    r = call("POST", "/admin/institutions", admin_token, json={
        "name": "second disposable", "slug": second_slug, "contact_email": contact_email,
        "modules": [], "speaking_sessions_per_month": 5,
    })
    check("second disposable institution created for dup-slug PATCH test -> 201", r.status_code == 201, f"status={r.status_code}")
    second_id = r.json()["id"] if r.status_code == 201 else None
    if second_id:
        created_institutions.append(("disposable-2", second_id))
        r = call("PATCH", f"/admin/institutions/{second_id}", admin_token, json={"slug": slug})
        check("PATCH to duplicate slug -> 409", r.status_code == 409, f"status={r.status_code} body={r.text[:200]}")

    # ── No tokens/secrets in responses ──────────────────────────────────
    log("\n=== No secrets leaked ===")
    r = call("GET", f"/admin/institutions/{institution_id}", admin_token)
    text = r.text.lower()
    check("detail response has no service_role/token/secret substrings",
          not any(s in text for s in ("service_role", "secret", "access_token", "refresh_token")), "leak check")

    return finish()


def finish():
    log("\n=== Summary ===")
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
            service.auth.admin.delete_user(uid)
            log(f"  deleted user {label}: {email}")
        except Exception as e:
            log(f"  WARN could not delete user {label} ({email}): {e}")

    # confirm gone
    remaining = service.table("institutions").select("id").in_(
        "id", [iid for _, iid in created_institutions]
    ).execute().data
    check("cleanup verified: no disposable institution rows remain", remaining == [], str(remaining))

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
