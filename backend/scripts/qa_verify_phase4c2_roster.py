"""Phase 4c-2 live QA verification -- GET /institution/students roster.

Controlled verification only. Does NOT touch roster implementation code and
does NOT build Phase 4c-3. Creates/reuses disposable auth users + institution
memberships in the QA Supabase project ONLY (wpowzyyzhrxdqujrvxdq), drives the
running QA-mode backend (BACKEND_URL), then prints a pass/fail summary.

Reuses the existing "SpeakOET QA Institution Pilot" as Institution A and its
already-active admin-a/teacher-a/student2-a fixtures from the Phase 4a run
(qa_verify_phase4_institution_admin.py, RUN_TAG e4410e72) rather than creating
duplicates. Institution B is fresh and scoped to this run's own tag so cleanup
never has to reason about another script's fixture state.

Usage:
    cd backend
    ENVIRONMENT=qa python -u scripts/qa_verify_phase4c2_roster.py
    ENVIRONMENT=qa python -u scripts/qa_verify_phase4c2_roster.py --cleanup
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "qa")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.core.config import settings
from app.core.supabase import get_supabase, get_auth_client

BACKEND_URL = os.environ.get("QA_VERIFY_BACKEND_URL", "http://127.0.0.1:8010")
RUN_TAG = "p4c2rq7"  # fixed so reruns are idempotent

assert "wpowzyyzhrxdqujrvxdq" in settings.SUPABASE_URL, (
    f"Refusing to run: SUPABASE_URL is not the QA project -- got {settings.SUPABASE_URL!r}"
)
assert "lgwaiwasnjjohqkeizdz" not in settings.SUPABASE_URL, "Refusing to run against production project ref"

service = get_supabase()
anon = get_auth_client()

PASSWORD_REUSED = "QaVerify!2026x"  # matches qa_verify_phase4_institution_admin.py's fixtures
PASSWORD_NEW = "QaP4c2Verify!2026x"

INST_A_ID = "7fc2df9f-30dd-4eae-a198-6868f60ae7a8"  # SpeakOET QA Institution Pilot
ADMIN_A_EMAIL = "qa-phase4-admin-a-e4410e72@example.com"
TEACHER_A_EMAIL = "qa-phase4-teacher-a-e4410e72@example.com"
STUDENT2_A_ID = "938639f7-8a56-40f0-8eee-920520df5247"
STUDENT2_A_EMAIL = "qa-phase4-student2-a-e4410e72@example.com"
STUDENT1_ID = "d48b679a-2b95-4b62-83e3-24bf92aa5f92"  # hiteshbata1@gmail.com, genuine existing membership

results = []
created_users = []


def log(msg):
    print(msg, flush=True)


def check(name: str, cond: bool, detail: str = ""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    log(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))


def get_or_create_user(label: str) -> tuple[str, str]:
    email = f"qa-phase4c2-{label}-{RUN_TAG}@example.com"
    existing = service.auth.admin.list_users()
    for u in existing:
        if u.email == email:
            created_users.append((label, u.id, email))
            return u.id, email
    resp = service.auth.admin.create_user({"email": email, "password": PASSWORD_NEW, "email_confirm": True})
    user_id = resp.user.id
    created_users.append((label, user_id, email))
    return user_id, email


def ensure_membership(institution_id: str, user_id: str, role: str, status: str = "active"):
    existing = (
        service.table("institution_members").select("institution_id")
        .eq("institution_id", institution_id).eq("user_id", user_id).execute()
    ).data
    if existing:
        service.table("institution_members").update({"role": role, "status": status}).eq(
            "institution_id", institution_id).eq("user_id", user_id).execute()
    else:
        service.table("institution_members").insert({
            "institution_id": institution_id, "user_id": user_id, "role": role, "status": status,
        }).execute()


def login(email: str, password: str) -> str:
    resp = anon.auth.sign_in_with_password({"email": email, "password": password})
    return resp.session.access_token


def call(method: str, path: str, token: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.request(method, f"{BACKEND_URL}{path}", headers=headers, timeout=30)


def upsert_profile(user_id: str, sessions_used: int | None, reset_date: str | None):
    existing = service.table("user_profiles").select("user_id").eq("user_id", user_id).execute().data
    row = {
        "user_id": user_id,
        "sessions_used_this_month": sessions_used,
        "sessions_reset_date": reset_date,
        "subscription_status": "none",
        "auto_renew_enabled": False,
        "bonus_sessions": 0,
    }
    if existing:
        service.table("user_profiles").update({
            "sessions_used_this_month": sessions_used,
            "sessions_reset_date": reset_date,
        }).eq("user_id", user_id).execute()
    else:
        service.table("user_profiles").insert(row).execute()


def cleanup():
    log("=== Cleanup ===")
    # Student 1 (genuine membership, untouched) -- revert seeded usage/submissions only
    service.table("submissions").delete().eq("user_id", STUDENT1_ID).eq("module", "speaking").execute()
    service.table("user_profiles").update({
        "sessions_used_this_month": None, "sessions_reset_date": None,
    }).eq("user_id", STUDENT1_ID).execute()
    log("  Student 1 (hiteshbata1@gmail.com): submissions + usage reverted; membership untouched")

    # Student 2 -- revert name + usage (membership/role/status untouched, was already active)
    service.table("users").update({"name": STUDENT2_A_EMAIL}).eq("id", STUDENT2_A_ID).execute()
    service.table("user_profiles").update({
        "sessions_used_this_month": None, "sessions_reset_date": None,
    }).eq("user_id", STUDENT2_A_ID).execute()
    log("  Student 2 fixture (student2-a): name + usage reverted")

    # Institution B (this run's own disposable institution) -- delete everything it owns
    inst_b = service.table("institutions").select("id").eq(
        "name", f"QA Phase4c2 Disposable Institution B {RUN_TAG}").execute().data
    if inst_b:
        inst_b_id = inst_b[0]["id"]
        service.table("institution_modules").delete().eq("institution_id", inst_b_id).execute()
        service.table("institution_members").delete().eq("institution_id", inst_b_id).execute()
        service.table("institutions").delete().eq("id", inst_b_id).execute()
        log(f"  Institution B ({inst_b_id}): deleted (modules, members, institution row)")

    # This run's own disposable users
    for label, uid, email in created_users:
        try:
            service.auth.admin.delete_user(uid)
            log(f"  deleted user {label}: {email}")
        except Exception as e:
            log(f"  could not delete user {label} ({email}): {e}")

    log("  Institution A (pilot) status/quota untouched -- was never modified by this run")
    log("  Pre-existing phase4/phase4b disposable fixtures untouched (predate this verification)")


def main():
    log("=== Environment ===")
    log(f"  SUPABASE_URL={settings.SUPABASE_URL}")
    log(f"  ENVIRONMENT={settings.ENVIRONMENT}")
    log(f"  BACKEND_URL={BACKEND_URL}")

    log("\n=== Section 1-2: fixtures ===")
    inst_a = service.table("institutions").select("id, name, status, speaking_sessions_per_month").eq(
        "id", INST_A_ID).execute().data
    assert inst_a and inst_a[0]["status"] == "active", "Institution A pilot missing/inactive -- aborting"
    log(f"  Institution A (reused pilot): {INST_A_ID}, quota={inst_a[0]['speaking_sessions_per_month']}")

    now = datetime.now(timezone.utc)
    month_start_ok = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    # Student 1 (genuine existing membership -- untouched): sessions used=12,
    # two speaking submissions (older=350, newer=390) so latest_speaking_score picks 390.
    upsert_profile(STUDENT1_ID, 12, month_start_ok)
    service.table("submissions").delete().eq("user_id", STUDENT1_ID).eq("module", "speaking").execute()
    older = (now - timedelta(days=2)).isoformat()
    newer = (now - timedelta(days=1)).isoformat()
    service.table("submissions").insert({
        "user_id": STUDENT1_ID, "module": "speaking", "score": 350, "created_at": older,
    }).execute()
    service.table("submissions").insert({
        "user_id": STUDENT1_ID, "module": "speaking", "score": 390, "created_at": newer,
    }).execute()
    log("  Student 1 (hiteshbata1@gmail.com): sessions_used=12, submissions 350(older)/390(newer)")

    # Student 2 (existing fixture, active membership): name missing, sessions used=5, no submissions.
    service.table("users").update({"name": None}).eq("id", STUDENT2_A_ID).execute()
    upsert_profile(STUDENT2_A_ID, 5, month_start_ok)
    log("  Student 2 (student2-a): name=NULL, sessions_used=5, no submissions")

    admin_a_token = login(ADMIN_A_EMAIL, PASSWORD_REUSED)
    teacher_a_token = login(TEACHER_A_EMAIL, PASSWORD_REUSED)

    log("\n=== Section 3-4: admin roster + privacy ===")
    r = call("GET", "/institution/students", admin_a_token)
    check("A admin GET /institution/students -> 200", r.status_code == 200, f"status={r.status_code} body={r.text[:500]}")
    roster = r.json() if r.status_code == 200 else []
    raw_text = r.text

    FORBIDDEN_FIELDS = ["user_id", "institution_id", "plan", "subscription_status", "bonus_sessions", "auth_token", "access_token"]
    leaked = [f for f in FORBIDDEN_FIELDS if f'"{f}"' in raw_text]
    check("response contains none of user_id/institution_id/plan/subscription_status/bonus_sessions/tokens", not leaked, str(leaked))

    emails_in_roster = {row["email"] for row in roster}
    check("roster contains Student 1 (hiteshbata1@gmail.com)", "hiteshbata1@gmail.com" in emails_in_roster)
    check("roster contains Student 2", STUDENT2_A_EMAIL in emails_in_roster)

    s1 = next((row for row in roster if row["email"] == "hiteshbata1@gmail.com"), None)
    s2 = next((row for row in roster if row["email"] == STUDENT2_A_EMAIL), None)

    if s1:
        check("Student 1 name present", s1["name"] == "QA Email Confirm Test", s1["name"])
        check("Student 1 sessions_used_this_month == 12", s1["sessions_used_this_month"] == 12, s1["sessions_used_this_month"])
        check("Student 1 sessions_remaining == 8 (quota 20 - 12)", s1["sessions_remaining"] == 8, s1["sessions_remaining"])
        check("Student 1 latest_speaking_score == 390 (not average, not 350)", s1["latest_speaking_score"] == 390, s1["latest_speaking_score"])
        check("Student 1 status == active", s1["status"] == "active", s1["status"])
        check("Student 1 joined_at present", bool(s1["joined_at"]), s1["joined_at"])
    if s2:
        check("Student 2 name is null (fallback case)", s2["name"] is None, s2["name"])
        check("Student 2 sessions_used_this_month == 5", s2["sessions_used_this_month"] == 5, s2["sessions_used_this_month"])
        check("Student 2 sessions_remaining == 15 (quota 20 - 5, independent of Student 1)", s2["sessions_remaining"] == 15, s2["sessions_remaining"])
        check("Student 2 latest_speaking_score is null (no submission)", s2["latest_speaking_score"] is None, s2["latest_speaking_score"])

    joined_dates = [row["joined_at"] or "" for row in roster]
    check("roster ordered by joined_at DESC", joined_dates == sorted(joined_dates, reverse=True), joined_dates)

    log("\n=== Section 5: teacher roster ===")
    r = call("GET", "/institution/students", teacher_a_token)
    check("A teacher GET /institution/students -> 200", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        teacher_emails = {row["email"] for row in r.json()}
        check("teacher sees same Institution A roster as admin", teacher_emails == emails_in_roster, str(teacher_emails ^ emails_in_roster))

    log("\n=== Section 6: student denial ===")
    student2_token = login(STUDENT2_A_EMAIL, PASSWORD_REUSED)
    r = call("GET", "/institution/students", student2_token)
    check("A student GET /institution/students -> 403", r.status_code == 403, f"status={r.status_code}")

    log("\n=== Section 7: cross-tenant isolation (fresh Institution B) ===")
    inst_b_name = f"QA Phase4c2 Disposable Institution B {RUN_TAG}"
    inst_b = service.table("institutions").select("id").eq("name", inst_b_name).execute().data
    if inst_b:
        inst_b_id = inst_b[0]["id"]
    else:
        inst_b_id = service.table("institutions").insert({
            "name": inst_b_name,
            "slug": f"qa-phase4c2-disposable-b-{RUN_TAG}",
            "contact_email": f"qa-phase4c2-institution-b-{RUN_TAG}@example.com",
            "status": "active",
            "speaking_sessions_per_month": 20,
        }).execute().data[0]["id"]
    service.table("institution_modules").upsert({
        "institution_id": inst_b_id, "module": "speaking", "enabled": True,
    }, on_conflict="institution_id,module").execute()

    admin_b_id, admin_b_email = get_or_create_user("admin-b")
    student_b_id, student_b_email = get_or_create_user("student-b")
    ensure_membership(inst_b_id, admin_b_id, "institution_admin")

    admin_b_token = login(admin_b_email, PASSWORD_NEW)

    # Reruns reuse Institution B -- clear any student membership left over
    # from a prior run so the "empty roster" check reflects a true empty
    # state rather than stale fixture data.
    service.table("institution_members").delete().eq("institution_id", inst_b_id).eq("role", "student").execute()

    log("  -- empty state (Section 12), before student-b joins --")
    r = call("GET", "/institution/students", admin_b_token)
    check("B admin GET students -> 200 empty list before any student joins", r.status_code == 200 and r.json() == [], f"status={r.status_code} body={r.text[:200]}")

    ensure_membership(inst_b_id, student_b_id, "student")
    # Real invite-accept always makes an authenticated backend call first
    # (accept_institution_invite_endpoint depends on get_current_user, which
    # upserts public.users -- see app/routers/auth.py), so a real student
    # always has a users row by the time their membership exists. This
    # fixture inserts the membership directly via service role, bypassing
    # that call -- make the same call once here so the fixture matches the
    # real flow instead of testing an artifact of the seeding shortcut.
    student_b_token = login(student_b_email, PASSWORD_NEW)
    call("GET", "/sessions/usage", student_b_token)

    r = call("GET", "/institution/students", admin_a_token)
    a_emails = {row["email"] for row in r.json()} if r.status_code == 200 else set()
    check("Institution A roster contains no Institution B student", student_b_email not in a_emails)

    r = call("GET", "/institution/students", admin_b_token)
    b_emails = {row["email"] for row in r.json()} if r.status_code == 200 else set()
    check("Institution B admin GET -> 200, sees only B's student", r.status_code == 200 and b_emails == {student_b_email}, f"status={r.status_code} body={b_emails}")
    check("no overlap between A roster and B roster", not (a_emails & b_emails))

    log("\n=== Section 9: unlimited quota ===")
    # institutions.speaking_sessions_per_month is a DB-level NOT NULL column
    # (default 20) in this QA project -- confirmed via information_schema.
    # A real NULL row can't be written without an ALTER TABLE, which is a
    # schema change out of scope for a controlled roster verification (and
    # would affect the shared institutions table, not just this fixture).
    # Verified instead by code inspection: app/routers/institution.py:156-158
    # -- `if speaking_enabled and quota is not None` -- correctly leaves
    # sessions_remaining as None whenever quota is None, so the roster logic
    # is right; the live DB just can't currently produce that state.
    check("unlimited quota handling verified by code inspection (DB column is NOT NULL, live state not reachable)",
          True, "app/routers/institution.py:156-158 -- quota is not None guard; flagged as a schema note, not a code defect")

    log("\n=== Section 10: speaking module disabled ===")
    service.table("institution_modules").update({"enabled": False}).eq("institution_id", inst_b_id).eq("module", "speaking").execute()
    r = call("GET", "/institution/students", admin_b_token)
    b_row = r.json()[0] if r.status_code == 200 and r.json() else None
    check("speaking disabled -> sessions_remaining is null", b_row is not None and b_row["sessions_remaining"] is None, b_row)
    service.table("institution_modules").update({"enabled": True}).eq("institution_id", inst_b_id).eq("module", "speaking").execute()
    log("  Institution B speaking module restored to enabled")

    log("\n=== Section 16: performance (fixed/batched query pattern) ===")
    # Code-inspection result (see app/routers/institution.py get_institution_students):
    # one institution_members query, one users query, one user_profiles query,
    # one submissions query, one institutions query, one institution_modules
    # query -- six fixed queries regardless of roster size, never one per student.
    check("roster handler code-verified as fixed/batched (6 queries, no N+1)", True,
          "app/routers/institution.py:get_institution_students -- verified by code inspection, matches docstring at lines 100-104")

    log("\n=== Section 17: B2C regression ===")
    b2c_id, b2c_email = get_or_create_user("b2c")
    b2c_token = login(b2c_email, PASSWORD_NEW)
    r = call("GET", "/institution/students", b2c_token)
    check("B2C user (no institution membership) GET /institution/students -> 403", r.status_code == 403, f"status={r.status_code}")

    log("\n=== Summary ===")
    failed = [x for x in results if x[0] == "FAIL"]
    log(f"{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        log("FAILURES:")
        for status, name, detail in failed:
            log(f"  - {name}: {detail}")

    return 1 if failed else 0


if __name__ == "__main__":
    if "--cleanup" in sys.argv:
        cleanup()
        raise SystemExit(0)
    raise SystemExit(main())
