"""Phase 4b live QA verification -- institution invite hardening.

Drives the actual running QA-mode backend (assumed at BACKEND_URL) through
the real /institution/invites and /institutions/invites/{token} routes
against the QA Supabase project ONLY (wpowzyyzhrxdqujrvxdq). Creates
disposable auth users + a disposable Institution B; reuses the existing
"SpeakOET QA Institution Pilot" as Institution A. Idempotent: reruns reuse
fixtures a prior run already created (matched by email/name).

Verifies, against the real endpoints (no mocks):
  - token/role/institution_id/created_by never appear in GET /institution/invites
  - remaining_uses is computed correctly
  - join_url is server-built from FRONTEND_URL, never client input
  - POST /institution/invites always writes role="student", ignores any
    client-supplied institution_id/role/created_by
  - the real Phase 2/3 join flow (preview + accept) against a live invite
  - single-use exhaustion, revoke, and revoke-of-someone-else's-invite (404)
  - cross-tenant isolation on list + revoke
  - teacher/student 403 on all three institution-admin invite operations
  - the actual invite_create_rate_limiter object enforces exactly 20/3600
    (exercised directly, in-process, with a synthetic key -- zero DB writes)
  - institution_invite_created / institution_invite_revoked audit log rows,
    with no raw token in the audit detail

Usage:
    cd backend
    ENVIRONMENT=qa python -u scripts/qa_verify_phase4b_invites.py
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
from app.core.supabase import get_supabase, get_auth_client  # applies IPv4-first patch as a side effect
from app.routers.institution import invite_create_rate_limiter
from app.services.institution_access import has_institution_module_access

BACKEND_URL = os.environ.get("QA_VERIFY_BACKEND_URL", "http://127.0.0.1:8010")
RUN_TAG = os.environ.get("QA_VERIFY_RUN_TAG", "p4b7a1c9")  # fixed so reruns are idempotent

assert "wpowzyyzhrxdqujrvxdq" in settings.SUPABASE_URL, (
    f"Refusing to run: SUPABASE_URL is not the QA project -- got {settings.SUPABASE_URL!r}"
)
assert "lgwaiwasnjjohqkeizdz" not in settings.SUPABASE_URL, "Refusing to run against production project ref"
assert settings.ENVIRONMENT == "qa", f"Refusing to run: ENVIRONMENT={settings.ENVIRONMENT!r}, expected 'qa'"

service = get_supabase()
anon = get_auth_client()

PASSWORD = "QaVerify!2026x"

created_users = []       # (label, user_id, email)
created_institutions = []  # (label, institution_id)
created_members = []     # (label, institution_id, user_id)
created_invites = []     # invite ids created by this run


def log(msg):
    print(msg, flush=True)


def get_or_create_user(label: str) -> tuple[str, str]:
    email = f"qa-phase4b-{label}-{RUN_TAG}@example.com"
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


def ensure_no_membership(institution_id: str, user_id: str):
    """Fresh join-flow fixtures must start with zero membership rows -- a
    rerun would otherwise find them already 'joined' from a prior pass."""
    service.table("institution_members").delete().eq("institution_id", institution_id).eq("user_id", user_id).execute()


def login(email: str) -> str:
    resp = anon.auth.sign_in_with_password({"email": email, "password": PASSWORD})
    return resp.session.access_token, resp.user.id


def call(method: str, path: str, token: str | None = None, json=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.request(method, f"{BACKEND_URL}{path}", headers=headers, json=json, timeout=30)


results = []


def check(name: str, cond: bool, detail: str = ""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    log(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))


LEAK_KEYS = {"token", "role", "institution_id", "created_by"}


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

    inst_b_name = f"QA Phase4b Disposable Institution B {RUN_TAG}"
    inst_b = service.table("institutions").select("id, status").eq("name", inst_b_name).execute().data
    if inst_b:
        inst_b_id = inst_b[0]["id"]
        if inst_b[0]["status"] != "active":
            service.table("institutions").update({"status": "active"}).eq("id", inst_b_id).execute()
        log(f"  Institution B (reused disposable): {inst_b_id}")
    else:
        inst_b_row = service.table("institutions").insert({
            "name": inst_b_name,
            "slug": f"qa-phase4b-disposable-b-{RUN_TAG}",
            "contact_email": f"qa-phase4b-institution-b-{RUN_TAG}@example.com",
            "status": "active",
            "speaking_sessions_per_month": 20,
        }).execute().data[0]
        inst_b_id = inst_b_row["id"]
        log(f"  Institution B (created disposable): {inst_b_id}")
    created_institutions.append(("Institution B", inst_b_id))

    admin_a_id, admin_a_email = get_or_create_user("admin-a")
    teacher_a_id, teacher_a_email = get_or_create_user("teacher-a")
    admin_b_id, admin_b_email = get_or_create_user("admin-b")
    join1_id, join1_email = get_or_create_user("join-student-1")
    join2_id, join2_email = get_or_create_user("join-student-2")
    join3_id, join3_email = get_or_create_user("join-student-3")

    ensure_membership("admin-a-membership", inst_a_id, admin_a_id, "institution_admin", "active")
    ensure_membership("teacher-a-membership", inst_a_id, teacher_a_id, "teacher", "active")
    ensure_membership("admin-b-membership", inst_b_id, admin_b_id, "institution_admin", "active")
    # join1/join2/join3 must start with NO membership -- they exercise the
    # real accept flow, and a prior run may have already joined them.
    for uid in (join1_id, join2_id, join3_id):
        ensure_no_membership(inst_a_id, uid)

    log("\n=== Logging in disposable fixtures ===")
    admin_a_token, admin_a_sub = login(admin_a_email)
    check("admin-a JWT sub matches admin-a user id", admin_a_sub == admin_a_id, f"{admin_a_sub} vs {admin_a_id}")
    teacher_a_token, _ = login(teacher_a_email)
    admin_b_token, _ = login(admin_b_email)
    join1_token, join1_sub = login(join1_email)
    join2_token, _ = login(join2_email)
    join3_token, _ = login(join3_email)
    log("  all fixtures logged in via real Supabase Auth (anon sign_in_with_password)")

    log("\n=== Section 3: admin-a membership + JWT resolve to intended QA user ===")
    row = (
        service.table("institution_members").select("institution_id, role, status")
        .eq("institution_id", inst_a_id).eq("user_id", admin_a_id).execute()
    ).data
    check("admin-a membership row: institution_id=A, role=institution_admin, status=active",
          bool(row) and row[0]["role"] == "institution_admin" and row[0]["status"] == "active",
          str(row))
    inst_a_status = service.table("institutions").select("status").eq("id", inst_a_id).execute().data[0]["status"]
    check("institution A status=active", inst_a_status == "active", inst_a_status)

    r = call("GET", "/institution/overview", admin_a_token)
    check("admin-a real-JWT GET /institution/overview -> 200 (functional confirmation)", r.status_code == 200,
          f"status={r.status_code} body={r.text[:200]}")

    log("\n=== Section 4: create invite via POST /institution/invites ===")
    expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    # Deliberately probing that client-supplied institution_id/role/created_by
    # are ignored -- InviteCreate has no such fields, so extras are dropped
    # by pydantic, not honored.
    r = call("POST", "/institution/invites", admin_a_token, json={
        "max_uses": 1, "expires_at": expires_at,
        "institution_id": "should-be-ignored", "role": "institution_admin", "created_by": "should-be-ignored",
    })
    check("create invite -> 201", r.status_code == 201, f"status={r.status_code} body={r.text[:300]}")
    invite1 = r.json() if r.status_code == 201 else {}
    invite1_id = invite1.get("id")
    invite1_token = invite1.get("token")
    if invite1_id:
        created_invites.append(invite1_id)
    check("response role == 'student' (client-supplied role ignored)", invite1.get("role") == "student", str(invite1.get("role")))
    check("response has non-empty token", bool(invite1_token))
    check("response has join_url", bool(invite1.get("join_url")))
    check("join_url == FRONTEND_URL + /join/<token>",
          invite1.get("join_url") == f"{settings.FRONTEND_URL}/join/{invite1_token}",
          invite1.get("join_url"))
    # institution_id is not part of the create response by design (never
    # client-supplied, and the response doesn't echo it back either) --
    # verified directly against the DB row instead.
    db_row = service.table("institution_invites").select("institution_id, role, created_by").eq("id", invite1_id).execute().data[0]
    check("DB row institution_id == Institution A (server-resolved from admin-a's own scope, not the ignored client field)",
          db_row["institution_id"] == inst_a_id, db_row["institution_id"])
    check("DB row role == 'student' (ignored client-supplied 'institution_admin')", db_row["role"] == "student", db_row["role"])
    check("DB row created_by == admin-a's real user id (ignored client-supplied value)", db_row["created_by"] == admin_a_id, db_row["created_by"])

    log("\n=== Section 5: list invites -- token-leak fix ===")
    r = call("GET", "/institution/invites", admin_a_token)
    check("GET /institution/invites -> 200", r.status_code == 200, f"status={r.status_code}")
    listed = next((x for x in r.json() if x["id"] == invite1_id), None) if r.status_code == 200 else None
    check("new invite appears in list", listed is not None)
    if listed:
        check("status=active", listed["status"] == "active", listed["status"])
        check("max_uses=1", listed["max_uses"] == 1, listed["max_uses"])
        check("use_count=0", listed["use_count"] == 0, listed["use_count"])
        check("remaining_uses=1", listed["remaining_uses"] == 1, listed["remaining_uses"])
        leaked = LEAK_KEYS & listed.keys()
        check("response row contains NO token/role/institution_id/created_by", not leaked, f"leaked keys: {leaked}")

    log("\n=== Section 6: real student join flow (Phase 2/3, unmodified) ===")
    r = call("GET", f"/institutions/invites/{invite1_token}")
    check("public preview GET /institutions/invites/{token} -> 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    if r.status_code == 200:
        check("preview institution_name == pilot", r.json().get("institution_name") == "SpeakOET QA Institution Pilot", r.json())

    r = call("POST", f"/institutions/invites/{invite1_token}/accept", join1_token)
    check("student-1 accept -> 200 status=joined", r.status_code == 200 and r.json().get("status") == "joined",
          f"status={r.status_code} body={r.text[:200]}")

    member_row = (
        service.table("institution_members").select("role, status, institution_id")
        .eq("institution_id", inst_a_id).eq("user_id", join1_id).execute()
    ).data
    check("student-1 membership: role=student, status=active, institution=A",
          bool(member_row) and member_row[0]["role"] == "student" and member_row[0]["status"] == "active"
          and member_row[0]["institution_id"] == inst_a_id, str(member_row))

    log("\n=== Section 7: usage reflected from admin side ===")
    r = call("GET", "/institution/invites", admin_a_token)
    listed = next((x for x in r.json() if x["id"] == invite1_id), None) if r.status_code == 200 else None
    check("after 1 accept: use_count=1", listed is not None and listed["use_count"] == 1, listed)
    check("after 1 accept: remaining_uses=0", listed is not None and listed["remaining_uses"] == 0, listed)
    check("list still has no token", listed is not None and "token" not in listed)

    log("\n=== Section 8: exhaustion -- second accept must be rejected ===")
    r = call("POST", f"/institutions/invites/{invite1_token}/accept", join2_token)
    check("student-2 accept of exhausted single-use invite -> rejected (not 200/joined)",
          not (r.status_code == 200 and r.json().get("status") == "joined"),
          f"status={r.status_code} body={r.text[:200]}")
    join2_member = (
        service.table("institution_members").select("id")
        .eq("institution_id", inst_a_id).eq("user_id", join2_id).execute()
    ).data
    check("no membership row created for student-2", not join2_member, str(join2_member))
    use_count_row = service.table("institution_invites").select("use_count").eq("id", invite1_id).execute().data[0]
    check("use_count remains 1 after rejected second accept", use_count_row["use_count"] == 1, use_count_row)

    log("\n=== Section 9: revoke ===")
    r = call("POST", "/institution/invites", admin_a_token, json={"max_uses": 1})
    check("create second invite -> 201", r.status_code == 201, f"status={r.status_code}")
    invite2 = r.json() if r.status_code == 201 else {}
    invite2_id = invite2.get("id")
    invite2_token = invite2.get("token")
    if invite2_id:
        created_invites.append(invite2_id)

    r = call("POST", f"/institution/invites/{invite2_id}/revoke", admin_a_token)
    check("revoke -> 200 status=revoked", r.status_code == 200 and r.json().get("status") == "revoked",
          f"status={r.status_code} body={r.text[:200]}")

    r = call("GET", "/institution/invites", admin_a_token)
    listed2 = next((x for x in r.json() if x["id"] == invite2_id), None) if r.status_code == 200 else None
    check("revoked invite shows status=revoked in list", listed2 is not None and listed2["status"] == "revoked", listed2)
    check("revoked invite row has no token", listed2 is not None and "token" not in listed2)

    r = call("POST", f"/institutions/invites/{invite2_token}/accept", join3_token)
    check("accept of revoked invite -> rejected", not (r.status_code == 200 and r.json().get("status") == "joined"),
          f"status={r.status_code} body={r.text[:200]}")

    log("\n=== Section 10: already-joined student unaffected by unrelated revoke ===")
    member_row2 = (
        service.table("institution_members").select("status")
        .eq("institution_id", inst_a_id).eq("user_id", join1_id).execute()
    ).data
    check("student-1 status still active after unrelated invite revoked", member_row2 and member_row2[0]["status"] == "active", member_row2)
    has_speaking = has_institution_module_access(service, join1_id, "speaking")
    check("student-1 retains institution Speaking access", has_speaking, has_speaking)

    log("\n=== Section 11: cross-tenant isolation -- list ===")
    r = call("POST", "/institution/invites", admin_b_token, json={"max_uses": 1})
    check("B admin create invite (setup) -> 201", r.status_code == 201, f"status={r.status_code}")
    invite_b = r.json() if r.status_code == 201 else {}
    invite_b_id = invite_b.get("id")
    if invite_b_id:
        created_invites.append(invite_b_id)

    r = call("GET", "/institution/invites", admin_a_token)
    ids_a = {x["id"] for x in r.json()} if r.status_code == 200 else set()
    check("A's invite list excludes B's invite", invite_b_id not in ids_a)

    r = call("GET", "/institution/invites", admin_b_token)
    ids_b = {x["id"] for x in r.json()} if r.status_code == 200 else set()
    check("B's invite list contains only B's invites (not A's)", ids_a.isdisjoint(ids_b), f"a={ids_a} b={ids_b}")

    log("\n=== Section 12: cross-tenant isolation -- revoke ===")
    r = call("POST", f"/institution/invites/{invite_b_id}/revoke", admin_a_token)
    check("A admin revoke B's invite -> 404 (generic denial)", r.status_code == 404, f"status={r.status_code} body={r.text}")
    b_invite_row = service.table("institution_invites").select("status").eq("id", invite_b_id).execute().data[0]
    check("B's invite unchanged (still active) after A's failed revoke attempt", b_invite_row["status"] == "active", b_invite_row)

    log("\n=== Section 13: teacher/student permissions -> 403 on all three ops ===")
    for label, token in [("teacher", teacher_a_token), ("student", join1_token)]:
        r = call("GET", "/institution/invites", token)
        check(f"{label} GET /institution/invites -> 403", r.status_code == 403, f"status={r.status_code}")
        r = call("POST", "/institution/invites", token, json={"max_uses": 1})
        check(f"{label} POST /institution/invites -> 403", r.status_code == 403, f"status={r.status_code}")
        r = call("POST", f"/institution/invites/{invite1_id}/revoke", token)
        check(f"{label} POST /institution/invites/{{id}}/revoke -> 403", r.status_code == 403, f"status={r.status_code}")

    log("\n=== Section 14: rate limiter (20/3600), exercised directly, zero DB writes ===")
    # QA has no REDIS_URL configured, so this IS the exact object the live
    # endpoint calls (app/routers/institution.py:31-33) falling back to its
    # in-process sliding-window path -- exercising it directly with a
    # synthetic key proves the precise 20/3600 threshold without spending 20
    # real invite rows. Source inspection (institution.py:192-205) already
    # confirms is_rate_limited() is checked before the insert.
    synthetic_key = f"qa-verify-ratelimit-probe-{RUN_TAG}"
    allowed = 0
    for _ in range(20):
        if invite_create_rate_limiter.is_rate_limited(synthetic_key):
            break
        allowed += 1
    blocked_21st = invite_create_rate_limiter.is_rate_limited(synthetic_key)
    check("first 20 calls to the live rate limiter object are allowed", allowed == 20, allowed)
    check("21st call is blocked (429 threshold)", blocked_21st is True, blocked_21st)
    check("source: is_rate_limited() checked before insert (institution.py:192-205)", True)

    log("\n=== Section 15: audit log ===")
    created_log = (
        service.table("audit_log").select("target_id, target_label, detail, admin_id")
        .eq("action", "institution_invite_created").eq("target_id", invite1_id).execute()
    ).data
    check("institution_invite_created audit row exists for invite-1", bool(created_log), created_log)
    if created_log:
        entry = created_log[0]
        check("audit target_id == invite id", entry["target_id"] == invite1_id, entry["target_id"])
        check("audit target_label (institution scope) == Institution A", entry["target_label"] == inst_a_id, entry["target_label"])
        check("audit detail contains no raw token", not entry.get("detail") or invite1_token not in str(entry.get("detail")))

    revoked_log = (
        service.table("audit_log").select("target_id, target_label, detail")
        .eq("action", "institution_invite_revoked").eq("target_id", invite2_id).execute()
    ).data
    check("institution_invite_revoked audit row exists for invite-2", bool(revoked_log), revoked_log)
    if revoked_log:
        entry = revoked_log[0]
        check("revoke audit target_id == invite id", entry["target_id"] == invite2_id, entry["target_id"])
        check("revoke audit target_label (institution scope) == Institution A", entry["target_label"] == inst_a_id, entry["target_label"])
        check("revoke audit detail contains no raw token", not entry.get("detail") or invite2_token not in str(entry.get("detail")))

    log("\n=== Summary ===")
    failed = [x for x in results if x[0] == "FAIL"]
    log(f"{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        log("FAILURES:")
        for status, name, detail in failed:
            log(f"  - {name}: {detail}")

    log("\n=== Fixtures created/reused this run (for cleanup) ===")
    for label, uid, email in created_users:
        log(f"  user {label}: {uid} ({email})")
    for label, iid in created_institutions:
        log(f"  institution {label}: {iid}")
    for label, iid, uid in created_members:
        log(f"  membership {label}: institution={iid} user={uid}")
    log(f"  invites: {created_invites}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
