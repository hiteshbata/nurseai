"""Phase 4a live QA verification -- controlled admin backend check.

Creates disposable auth users + institution memberships in the QA Supabase
project ONLY (wpowzyyzhrxdqujrvxdq), drives the running QA-mode backend
(assumed at BACKEND_URL) through the Phase 4 institution admin routes, then
prints a pass/fail summary. Reuses the existing "SpeakOET QA Institution
Pilot" institution as Institution A rather than creating a duplicate.
Idempotent: reruns reuse any fixtures a prior run already created (matched
by email/name), rather than creating duplicates.

Usage:
    cd backend
    ENVIRONMENT=qa python -u scripts/qa_verify_phase4_institution_admin.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "qa")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.core.config import settings
from app.core.supabase import get_supabase, get_auth_client  # applies IPv4-first patch as a side effect

BACKEND_URL = os.environ.get("QA_VERIFY_BACKEND_URL", "http://127.0.0.1:8010")
RUN_TAG = os.environ.get("QA_VERIFY_RUN_TAG", "e4410e72")  # fixed so reruns are idempotent

assert "wpowzyyzhrxdqujrvxdq" in settings.SUPABASE_URL, (
    f"Refusing to run: SUPABASE_URL is not the QA project -- got {settings.SUPABASE_URL!r}"
)
assert "lgwaiwasnjjohqkeizdz" not in settings.SUPABASE_URL, "Refusing to run against production project ref"

service = get_supabase()
anon = get_auth_client()

PASSWORD = "QaVerify!2026x"

created_users = []
created_institutions = []
created_members = []


def log(msg):
    print(msg, flush=True)


def get_or_create_user(label: str) -> tuple[str, str]:
    email = f"qa-phase4-{label}-{RUN_TAG}@example.com"
    existing = service.auth.admin.list_users()
    for u in existing:
        if u.email == email:
            created_users.append((label, u.id, email))
            log(f"  reused user {label}: {email} ({u.id})")
            return u.id, email
    resp = service.auth.admin.create_user({"email": email, "password": PASSWORD, "email_confirm": True})
    user_id = resp.user.id
    created_users.append((label, user_id, email))
    log(f"  created user {label}: {email} ({user_id})")
    return user_id, email


def ensure_membership(label: str, institution_id: str, user_id: str, role: str, status: str = "active"):
    existing = (
        service.table("institution_members").select("institution_id, role, status")
        .eq("institution_id", institution_id).eq("user_id", user_id).execute()
    ).data
    if existing:
        service.table("institution_members").update({"role": role, "status": status}).eq(
            "institution_id", institution_id).eq("user_id", user_id).execute()
        log(f"  membership (updated): {label} role={role} status={status}")
    else:
        service.table("institution_members").insert({
            "institution_id": institution_id, "user_id": user_id, "role": role, "status": status,
        }).execute()
        log(f"  membership (created): {label} role={role} status={status}")
    created_members.append((label, institution_id, user_id))


def login(email: str) -> str:
    resp = anon.auth.sign_in_with_password({"email": email, "password": PASSWORD})
    return resp.session.access_token


def call(method: str, path: str, token: str | None = None, json=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.request(method, f"{BACKEND_URL}{path}", headers=headers, json=json, timeout=30)


results = []


def check(name: str, cond: bool, detail: str = ""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    log(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))


def main():
    log("=== Fixture setup ===")

    inst_a = (
        service.table("institutions").select("id, name, status")
        .eq("name", "SpeakOET QA Institution Pilot").execute()
    ).data
    assert inst_a, "Expected existing pilot institution not found -- aborting"
    inst_a_id = inst_a[0]["id"]
    log(f"  Institution A (reused pilot): {inst_a_id}")
    if inst_a[0]["status"] != "active":
        service.table("institutions").update({"status": "active"}).eq("id", inst_a_id).execute()
        log("  Institution A was not active -- restored to active")

    inst_b_name = f"QA Phase4 Disposable Institution B {RUN_TAG}"
    inst_b = service.table("institutions").select("id, status").eq("name", inst_b_name).execute().data
    if inst_b:
        inst_b_id = inst_b[0]["id"]
        if inst_b[0]["status"] != "active":
            service.table("institutions").update({"status": "active"}).eq("id", inst_b_id).execute()
        log(f"  Institution B (reused disposable): {inst_b_id}")
    else:
        inst_b_row = service.table("institutions").insert({
            "name": inst_b_name,
            "slug": f"qa-phase4-disposable-b-{RUN_TAG}",
            "contact_email": f"qa-phase4-institution-b-{RUN_TAG}@example.com",
            "status": "active",
            "speaking_sessions_per_month": 20,
        }).execute().data[0]
        inst_b_id = inst_b_row["id"]
        log(f"  Institution B (created disposable): {inst_b_id}")
    created_institutions.append(("Institution B", inst_b_id))

    admin_a_id, admin_a_email = get_or_create_user("admin-a")
    teacher_a_id, teacher_a_email = get_or_create_user("teacher-a")
    student2_a_id, student2_a_email = get_or_create_user("student2-a")
    admin_b_id, admin_b_email = get_or_create_user("admin-b")

    ensure_membership("admin-a-membership", inst_a_id, admin_a_id, "institution_admin", "active")
    ensure_membership("teacher-a-membership", inst_a_id, teacher_a_id, "teacher", "active")
    ensure_membership("student2-a-membership", inst_a_id, student2_a_id, "student", "active")
    ensure_membership("admin-b-membership", inst_b_id, admin_b_id, "institution_admin", "active")

    existing_student_row = (
        service.table("institution_members").select("user_id")
        .eq("institution_id", inst_a_id).eq("role", "student").eq("status", "active")
        .neq("user_id", student2_a_id).execute()
    ).data
    existing_student_id = existing_student_row[0]["user_id"] if existing_student_row else None
    log(f"  existing real student in Institution A: {existing_student_id}")

    log("\n=== Logging in disposable fixtures ===")
    admin_a_token = login(admin_a_email)
    log("  admin-a logged in")
    teacher_a_token = login(teacher_a_email)
    log("  teacher-a logged in")
    admin_b_token = login(admin_b_email)
    log("  admin-b logged in")
    student2_a_token = login(student2_a_email)
    log("  student2-a logged in")

    log("\n=== Section 3: live authorization -- Institution A admin ===")
    r = call("GET", "/institution/overview", admin_a_token)
    check("A admin GET overview -> 200", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
    if r.status_code == 200:
        body = r.json()
        check("overview name matches Institution A", "SpeakOET QA Institution Pilot" in body.get("name", ""), body.get("name"))
        check("overview has active_student_count/usage/quota fields",
              {"active_student_count", "sessions_used_this_month", "speaking_sessions_per_month"} <= body.keys())

    r = call("GET", "/institution/students", admin_a_token)
    check("A admin GET students -> 200", r.status_code == 200, f"status={r.status_code}")
    roster_ids = {row["user_id"] for row in r.json()} if r.status_code == 200 else set()
    check("roster contains only Institution A students", roster_ids and roster_ids <= {existing_student_id, student2_a_id}, str(roster_ids))

    r = call("GET", "/institution/invites", admin_a_token)
    check("A admin GET invites -> 200", r.status_code == 200, f"status={r.status_code}")

    r = call("POST", "/institution/invites", admin_a_token, json={"max_uses": 1})
    check("A admin POST invites -> 201", r.status_code == 201, f"status={r.status_code} body={r.text[:300]}")
    invite_a_id = r.json()["id"] if r.status_code == 201 else None

    log("\n=== Section 4: cross-tenant isolation ===")
    r = call("POST", "/institution/invites", admin_b_token, json={"max_uses": 1})
    check("B admin POST invites -> 201 (setup)", r.status_code == 201, f"status={r.status_code}")
    invite_b_id = r.json()["id"] if r.status_code == 201 else None

    if invite_b_id:
        r = call("POST", f"/institution/invites/{invite_b_id}/revoke", admin_a_token)
        check("A admin revoke B's invite id -> 404 (generic denial, not 403/200)", r.status_code == 404, f"status={r.status_code} body={r.text}")

    r = call("GET", "/institution/invites", admin_a_token)
    if r.status_code == 200 and invite_b_id:
        ids = {row["id"] for row in r.json()}
        check("A's invite list excludes B's invite id", invite_b_id not in ids)

    log("\n=== Section 5: student authorization ===")
    for path in ["/institution/overview", "/institution/students", "/institution/invites"]:
        r = call("GET", path, student2_a_token)
        check(f"student GET {path} -> 403", r.status_code == 403, f"status={r.status_code}")

    log("\n=== Section 6: teacher authorization ===")
    r = call("GET", "/institution/overview", teacher_a_token)
    check("teacher GET overview -> 200", r.status_code == 200, f"status={r.status_code}")
    r = call("GET", "/institution/students", teacher_a_token)
    check("teacher GET students -> 200", r.status_code == 200, f"status={r.status_code}")
    r = call("GET", "/institution/invites", teacher_a_token)
    check("teacher GET invites -> 403", r.status_code == 403, f"status={r.status_code}")
    r = call("POST", "/institution/invites", teacher_a_token, json={"max_uses": 1})
    check("teacher POST invites -> 403 (no write)", r.status_code == 403, f"status={r.status_code}")

    log("\n=== Section 7: suspended institution (Institution B) ===")
    service.table("institutions").update({"status": "suspended"}).eq("id", inst_b_id).execute()
    r = call("GET", "/institution/overview", admin_b_token)
    check("B admin GET overview while suspended -> 403", r.status_code == 403, f"status={r.status_code}")
    service.table("institutions").update({"status": "active"}).eq("id", inst_b_id).execute()
    r = call("GET", "/institution/overview", admin_b_token)
    check("B admin GET overview after restore -> 200", r.status_code == 200, f"status={r.status_code}")

    log("\n=== Section 8: revoked administrator (Institution B admin) ===")
    service.table("institution_members").update({"status": "revoked"}).eq("institution_id", inst_b_id).eq("user_id", admin_b_id).execute()
    r = call("GET", "/institution/overview", admin_b_token)
    check("revoked B admin GET overview -> 403", r.status_code == 403, f"status={r.status_code}")
    r = call("GET", "/institution/students", admin_b_token)
    check("revoked B admin GET students -> 403", r.status_code == 403, f"status={r.status_code}")
    r = call("GET", "/institution/invites", admin_b_token)
    check("revoked B admin GET invites -> 403", r.status_code == 403, f"status={r.status_code}")
    # left revoked deliberately -- Institution B + this membership are disposable, deleted in cleanup

    log("\n=== Section 9: usage consistency ===")
    r = call("GET", "/institution/overview", admin_a_token)
    overview_total = r.json().get("sessions_used_this_month") if r.status_code == 200 else None
    r2 = call("GET", "/sessions/usage", student2_a_token)
    student2_usage = r2.json().get("sessions_used") if r2.status_code == 200 else None
    check("student2-a's own GET /sessions/usage -> 200", r2.status_code == 200, f"status={r2.status_code}")
    r3 = call("GET", "/institution/students", admin_a_token)
    roster_sum = sum(row["sessions_used_this_month"] for row in r3.json()) if r3.status_code == 200 else None
    check("overview total equals sum of roster per-student totals (same UTC month calc)", overview_total == roster_sum, f"overview={overview_total} roster_sum={roster_sum}")
    roster_student2_row = next((row for row in r3.json() if row["user_id"] == student2_a_id), None) if r3.status_code == 200 else None
    if roster_student2_row:
        check("roster's student2 usage matches student2's own GET /sessions/usage", roster_student2_row["sessions_used_this_month"] == student2_usage,
              f"roster={roster_student2_row['sessions_used_this_month']} own={student2_usage}")

    log("\n=== Summary ===")
    failed = [x for x in results if x[0] == "FAIL"]
    log(f"{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        log("FAILURES:")
        for status, name, detail in failed:
            log(f"  - {name}: {detail}")

    log("\n=== Fixtures created/reused (for cleanup) ===")
    log("Users:")
    for label, uid, email in created_users:
        log(f"  {label}: {uid} ({email})")
    log("Institutions:")
    for label, iid in created_institutions:
        log(f"  {label}: {iid}")
    log("Memberships:")
    for label, iid, uid in created_members:
        log(f"  {label}: institution={iid} user={uid}")
    if invite_a_id:
        log(f"Invite (Institution A, disposable): {invite_a_id}")
    if invite_b_id:
        log(f"Invite (Institution B, disposable): {invite_b_id}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
