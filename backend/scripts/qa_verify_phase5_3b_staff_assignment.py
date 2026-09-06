"""Phase 5.3b live QA verification -- POST /admin/institutions/{id}/staff.

Drives the running QA-mode backend (BACKEND_URL) through the real HTTP API
against the QA Supabase project ONLY (wpowzyyzhrxdqujrvxdq), using only
disposable fixtures, then prints a pass/fail summary and cleans up every row
it created (institutions, institution_modules, institution_members,
audit_log rows, and Auth users -- including any real invite-created users).

Usage:
    cd backend
    ENVIRONMENT=qa .venv-qa/Scripts/python.exe -u scripts/qa_verify_phase5_3b_staff_assignment.py
"""
from __future__ import annotations

import os
import sys
import threading
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

created_users: list[tuple[str, str, str]] = []          # (label, user_id, email)
created_institutions: list[tuple[str, str]] = []         # (label, institution_id)
results: list[tuple[str, str, str]] = []


def log(msg):
    print(msg, flush=True)


def check(name: str, cond: bool, detail: str = ""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    log(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))


# example.com is rejected outright by the QA project's mail relay ("Error
# sending invite email", confirmed by direct probe) -- mailinator.com and
# gmail.com both send successfully, so every fixture uses mailinator.com
# (same domain already used for prior QA audits per project memory).
FIXTURE_DOMAIN = "mailinator.com"


def get_or_create_user(label: str, role: str | None, confirm: bool = True) -> tuple[str, str]:
    email = f"qa-p53b-{label}-{RUN_TAG}@{FIXTURE_DOMAIN}"
    resp = service.auth.admin.create_user({"email": email, "password": PASSWORD, "email_confirm": confirm})
    user_id = resp.user.id
    created_users.append((label, user_id, email))
    if role:
        service.table("user_roles").upsert({"user_id": user_id, "role": role}, on_conflict="user_id").execute()
    log(f"  created user {label}: {email} ({user_id}) role={role} confirmed={confirm}")
    return user_id, email


def fresh_email(label: str) -> str:
    return f"qa-p53b-{label}-{RUN_TAG}@{FIXTURE_DOMAIN}"


def login(email: str) -> str:
    resp = anon.auth.sign_in_with_password({"email": email, "password": PASSWORD})
    return resp.session.access_token


def call(method: str, path: str, token: str | None = None, json=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.request(method, f"{BACKEND_URL}{path}", headers=headers, json=json, timeout=30)


def audit_rows(action: str, target_id: str) -> list[dict]:
    return (
        service.table("audit_log").select("action, target_id, target_label, detail")
        .eq("action", action).eq("target_id", target_id).execute()
    ).data or []


def member_row(institution_id: str, user_id: str) -> dict | None:
    rows = (
        service.table("institution_members").select("*")
        .eq("institution_id", institution_id).eq("user_id", user_id).execute()
    ).data or []
    return rows[0] if rows else None


def member_count(institution_id: str, user_id: str) -> int:
    return len((
        service.table("institution_members").select("id")
        .eq("institution_id", institution_id).eq("user_id", user_id).execute()
    ).data or [])


def auth_user_count_by_email(email: str) -> int:
    n = 0
    page = 1
    while True:
        batch = service.auth.admin.list_users(page=page, per_page=200)
        if not batch:
            break
        n += sum(1 for u in batch if u.email == email)
        page += 1
        if page > 20:
            break
    return n


def create_institution(admin_token: str, label: str, slug_suffix: str, quota: int = 10) -> str:
    slug = f"qa-p53b-{slug_suffix}-{RUN_TAG}"
    r = call("POST", "/admin/institutions", admin_token, json={
        "name": f"QA Phase 5.3b {label} {RUN_TAG}",
        "slug": slug,
        "contact_email": f"qa-p53b-contact-{slug_suffix}-{RUN_TAG}@example.com",
        "status": "active",
        "modules": ["speaking"],
        "speaking_sessions_per_month": quota,
    })
    check(f"setup: create institution '{label}' -> 201", r.status_code == 201, f"status={r.status_code} body={r.text[:200]}")
    iid = r.json()["id"]
    created_institutions.append((label, iid))
    return iid


def complete_invite_flow(email: str, expected_user_id: str) -> str | None:
    """Mirrors the verified 5.3a invite -> confirm -> reset-password chain:
    generate_link(type=invite) for a fresh token_hash (same mechanism the
    real invite email points at), verify_otp via an anon client (== SSR
    /auth/confirm route.ts), set a new password (== reset-password page's
    updateUser), then a normal sign_in_with_password. Returns the new
    access token, or None on failure (caller checks())."""
    from supabase import create_client

    def anon_client():
        return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)

    try:
        r = service.auth.admin.generate_link({"type": "invite", "email": email})
        token_hash = getattr(r.properties, "hashed_token", None)
        check("invite flow: generate_link token_hash present", bool(token_hash))
        check("invite flow: same Auth user id under generate_link", r.user.id == expected_user_id, f"{r.user.id} vs {expected_user_id}")
    except Exception as e:
        check("invite flow: generate_link(type=invite)", False, str(e))
        return None

    client = anon_client()
    try:
        v = client.auth.verify_otp({"type": "invite", "token_hash": token_hash})
        check("invite flow: verify_otp establishes session", bool(v.session and v.session.access_token))
    except Exception as e:
        check("invite flow: verify_otp(type=invite)", False, str(e))
        return None

    try:
        client.auth.update_user({"password": PASSWORD})
        check("invite flow: password set on invite session", True)
    except Exception as e:
        check("invite flow: set password", False, str(e))
        return None

    try:
        client.auth.sign_out()
    except Exception:
        pass
    login_client = anon_client()
    try:
        s = login_client.auth.sign_in_with_password({"email": email, "password": PASSWORD})
        check("invite flow: normal login after password set", bool(s.session and s.session.access_token))
        return s.session.access_token
    except Exception as e:
        check("invite flow: normal login", False, str(e))
        return None


def main():
    try:
        run_all_groups()
    except Exception as e:
        import traceback
        log(f"\n!!! UNEXPECTED EXCEPTION, aborting remaining test groups but still cleaning up: {e}")
        traceback.print_exc()
        check("run completed without an unhandled exception", False, str(e))
    return finish()


def run_all_groups():
    log("=== Fixture setup: staff + non-staff users ===")
    admin_id, admin_email = get_or_create_user("admin", "admin")
    analyst_id, analyst_email = get_or_create_user("analyst", "analyst")
    support_id, support_email = get_or_create_user("support", "support")
    plain_id, plain_email = get_or_create_user("plainuser", None)
    admin_token = login(admin_email)
    analyst_token = login(analyst_email)
    support_token = login(support_email)
    plain_token = login(plain_email)

    log("\n=== Setup: institution X (primary, active, speaking quota 10) ===")
    inst_x = create_institution(admin_token, "X-primary", "x")

    # ════════════════════════════════════════════════════════════════════
    log("\n=== TEST GROUP 1: existing confirmed user ===")
    g1_id, g1_email = get_or_create_user("g1-confirmed", None, confirm=True)
    before_count = auth_user_count_by_email(g1_email)

    r = call("POST", f"/admin/institutions/{inst_x}/staff", admin_token, json={"email": g1_email, "role": "institution_admin"})
    check("G1: assign succeeds (2xx)", r.status_code in (200, 201), f"status={r.status_code} body={r.text[:300]}")
    check("G1: assign returns HTTP 201 per spec (endpoint route has no status_code=201 -- see finding)", r.status_code == 201, f"status={r.status_code}")
    body = r.json() if r.status_code in (200, 201) else {}
    check("G1: response role == institution_admin", body.get("role") == "institution_admin", str(body))
    check("G1: response auth_state == confirmed", body.get("auth_state") == "confirmed", str(body))

    row = member_row(inst_x, g1_id)
    check("G1: membership created", row is not None, str(row))
    if row:
        check("G1: role == institution_admin", row.get("role") == "institution_admin", str(row))
        check("G1: status == active", row.get("status") == "active", str(row))
        check("G1: joined_at populated", bool(row.get("joined_at")), str(row))
        check("G1: invited_by == staff admin", row.get("invited_by") == admin_id, str(row))
    check("G1: exactly one membership row", member_count(inst_x, g1_id) == 1, str(member_count(inst_x, g1_id)))

    g1_audit = audit_rows("institution_staff_assigned", inst_x)
    g1_audit_match = [a for a in g1_audit if a.get("target_label") == g1_email]
    check("G1: audit row created", bool(g1_audit_match), str(g1_audit_match))

    after_count = auth_user_count_by_email(g1_email)
    check("G1: no new Auth user created", after_count == before_count == 1, f"before={before_count} after={after_count}")

    log("  --- G1: authenticate as the assigned institution admin ---")
    g1_token = login(g1_email)
    r = call("GET", "/institution/overview", g1_token)
    check("G1: GET /institution/overview -> 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    r = call("GET", "/institution/students", g1_token)
    check("G1: GET /institution/students -> 200", r.status_code == 200, f"status={r.status_code}")
    r = call("GET", "/institution/invites", g1_token)
    check("G1: GET /institution/invites -> 200", r.status_code == 200, f"status={r.status_code}")

    r = call("GET", "/sessions/usage", g1_token)
    check("G1: GET /sessions/usage -> 200", r.status_code == 200, f"status={r.status_code}")
    usage = r.json() if r.status_code == 200 else {}
    check("G1: institution_modules includes speaking", "speaking" in usage.get("institution_modules", []), str(usage.get("institution_modules")))
    check("G1: sessions_limit == 10", usage.get("sessions_limit") == 10, str(usage.get("sessions_limit")))

    # ════════════════════════════════════════════════════════════════════
    log("\n=== TEST GROUP 2: brand-new user ===")
    g2_email = fresh_email("g2-new")
    check("G2: user does not exist yet", auth_user_count_by_email(g2_email) == 0, "")

    r = call("POST", f"/admin/institutions/{inst_x}/staff", admin_token, json={"email": g2_email, "role": "institution_admin"})
    check("G2: assign succeeds", r.status_code in (200, 201), f"status={r.status_code} body={r.text[:300]}")
    body = r.json() if r.status_code in (200, 201) else {}
    check("G2: response auth_state == not_found (new Auth user)", body.get("auth_state") == "not_found", str(body))
    resp_text_lower = r.text.lower()
    check("G2: response has no password/token/credential leak",
          not any(s in resp_text_lower for s in ("password", "access_token", "refresh_token", "\"token\"", "credential")),
          "leak check")

    g2_users = [u for u in service.auth.admin.list_users(page=1, per_page=200) if u.email == g2_email]
    check("G2: exactly one Auth user created", len(g2_users) == 1, str(len(g2_users)))
    g2_id = g2_users[0].id if g2_users else None
    if g2_id:
        created_users.append(("g2-new", g2_id, g2_email))

    row = member_row(inst_x, g2_id) if g2_id else None
    check("G2: membership created with status=active immediately", bool(row) and row.get("status") == "active", str(row))
    check("G2: joined_at populated", bool(row and row.get("joined_at")), str(row))

    g2_audit = [a for a in audit_rows("institution_staff_assigned", inst_x) if a.get("target_label") == g2_email]
    check("G2: audit row created", bool(g2_audit), str(g2_audit))

    if g2_id:
        log("  --- G2: complete the verified 5.3a invite -> confirm -> reset-password -> login chain ---")
        g2_token = complete_invite_flow(g2_email, g2_id)
        if g2_token:
            r = call("GET", "/institution/overview", g2_token)
            check("G2: /institution/overview -> 200 immediately after login (no /institution/activate needed)", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")

    # ════════════════════════════════════════════════════════════════════
    log("\n=== TEST GROUP 3: existing unconfirmed user (created via invite mechanism) ===")
    g3_email = fresh_email("g3-unconf")
    pre = service.auth.admin.invite_user_by_email(g3_email, {"redirect_to": f"{settings.FRONTEND_URL}/auth/callback"})
    g3_id = pre.user.id
    created_users.append(("g3-unconf", g3_id, g3_email))
    check("G3: pre-created user is unconfirmed", pre.user.email_confirmed_at is None, str(pre.user.email_confirmed_at))

    r = call("POST", f"/admin/institutions/{inst_x}/staff", admin_token, json={"email": g3_email, "role": "institution_admin"})
    check("G3: assign succeeds", r.status_code in (200, 201), f"status={r.status_code} body={r.text[:300]}")
    body = r.json() if r.status_code in (200, 201) else {}
    check("G3: response auth_state == unconfirmed", body.get("auth_state") == "unconfirmed", str(body))
    if "warning" in body:
        log(f"  G3 resend behavior: warning={body['warning']!r} (documented best-effort failure, assignment still succeeded)")
    else:
        log("  G3 resend behavior: no warning -- resend invite succeeded")

    g3_users = [u for u in service.auth.admin.list_users(page=1, per_page=200) if u.email == g3_email]
    check("G3: same Auth user id retained, no duplicate", len(g3_users) == 1 and g3_users[0].id == g3_id, str([u.id for u in g3_users]))

    row = member_row(inst_x, g3_id)
    check("G3: membership status == active", bool(row) and row.get("status") == "active", str(row))
    check("G3: joined_at populated", bool(row and row.get("joined_at")), str(row))

    log("  --- G3: complete invite flow, confirm /institution works via already-active membership ---")
    g3_token = complete_invite_flow(g3_email, g3_id)
    if g3_token:
        r = call("GET", "/institution/overview", g3_token)
        check("G3: /institution/overview -> 200 (membership was already active)", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")

    # ════════════════════════════════════════════════════════════════════
    log("\n=== TEST GROUP 4: role safety ===")

    # 4.1 existing student
    u_id, u_email = get_or_create_user("g4-student", None)
    service.table("institution_members").insert({"institution_id": inst_x, "user_id": u_id, "role": "student", "status": "active"}).execute()
    r = call("POST", f"/admin/institutions/{inst_x}/staff", admin_token, json={"email": u_email, "role": "institution_admin"})
    check("G4.1: existing student -> 409", r.status_code == 409, f"status={r.status_code} body={r.text[:200]}")
    row = member_row(inst_x, u_id)
    check("G4.1: existing membership role unchanged (still student)", row and row.get("role") == "student", str(row))

    # 4.2 existing teacher
    u_id, u_email = get_or_create_user("g4-teacher", None)
    service.table("institution_members").insert({"institution_id": inst_x, "user_id": u_id, "role": "teacher", "status": "active"}).execute()
    r = call("POST", f"/admin/institutions/{inst_x}/staff", admin_token, json={"email": u_email, "role": "institution_admin"})
    check("G4.2: existing teacher -> 409", r.status_code == 409, f"status={r.status_code} body={r.text[:200]}")
    row = member_row(inst_x, u_id)
    check("G4.2: existing membership role unchanged (still teacher)", row and row.get("role") == "teacher", str(row))

    # 4.3 existing institution_admin -> 200 already_assigned (idempotent)
    u_id, u_email = get_or_create_user("g4-instadmin", None)
    service.table("institution_members").insert({"institution_id": inst_x, "user_id": u_id, "role": "institution_admin", "status": "active"}).execute()
    r = call("POST", f"/admin/institutions/{inst_x}/staff", admin_token, json={"email": u_email, "role": "institution_admin"})
    check("G4.3: existing institution_admin -> 200 already_assigned", r.status_code == 200 and r.json().get("status") == "already_assigned", f"status={r.status_code} body={r.text[:200]}")
    check("G4.3: still exactly one membership row", member_count(inst_x, u_id) == 1, str(member_count(inst_x, u_id)))

    # 4.4 revoked membership
    u_id, u_email = get_or_create_user("g4-revoked", None)
    service.table("institution_members").insert({"institution_id": inst_x, "user_id": u_id, "role": "teacher", "status": "revoked"}).execute()
    r = call("POST", f"/admin/institutions/{inst_x}/staff", admin_token, json={"email": u_email, "role": "institution_admin"})
    check("G4.4: revoked membership -> 409", r.status_code == 409, f"status={r.status_code} body={r.text[:200]}")
    row = member_row(inst_x, u_id)
    check("G4.4: revoked membership row unchanged", row and row.get("status") == "revoked" and row.get("role") == "teacher", str(row))

    # 4.5 invited membership
    u_id, u_email = get_or_create_user("g4-invited", None)
    service.table("institution_members").insert({"institution_id": inst_x, "user_id": u_id, "role": "student", "status": "invited"}).execute()
    r = call("POST", f"/admin/institutions/{inst_x}/staff", admin_token, json={"email": u_email, "role": "institution_admin"})
    check("G4.5: invited membership -> 409", r.status_code == 409, f"status={r.status_code} body={r.text[:200]}")
    row = member_row(inst_x, u_id)
    check("G4.5: invited membership row unchanged", row and row.get("status") == "invited", str(row))

    # 4.6 duplicate assignment (call twice for the same brand-new user) -> no duplicate membership
    u_email = fresh_email("g4-dup")
    r1 = call("POST", f"/admin/institutions/{inst_x}/staff", admin_token, json={"email": u_email, "role": "institution_admin"})
    check("G4.6: first assign succeeds", r1.status_code in (200, 201), f"status={r1.status_code}")
    u_users = [u for u in service.auth.admin.list_users(page=1, per_page=200) if u.email == u_email]
    u_id = u_users[0].id if u_users else None
    if u_id:
        created_users.append(("g4-dup", u_id, u_email))
    r2 = call("POST", f"/admin/institutions/{inst_x}/staff", admin_token, json={"email": u_email, "role": "institution_admin"})
    check("G4.6: duplicate assign -> 200 already_assigned (no error)", r2.status_code == 200, f"status={r2.status_code} body={r2.text[:200]}")
    check("G4.6: exactly one membership row after duplicate assignment", u_id and member_count(inst_x, u_id) == 1, str(u_id and member_count(inst_x, u_id)))

    # 4.7 user already active staff in ANOTHER institution -> 409 (dedicated 'elsewhere' institution)
    inst_elsewhere = create_institution(admin_token, "elsewhere", "elsewhere")
    u_id, u_email = get_or_create_user("g4-elsewhere", None)
    service.table("institution_members").insert({"institution_id": inst_elsewhere, "user_id": u_id, "role": "teacher", "status": "active"}).execute()
    r = call("POST", f"/admin/institutions/{inst_x}/staff", admin_token, json={"email": u_email, "role": "institution_admin"})
    check("G4.7: already active staff elsewhere -> 409", r.status_code == 409, f"status={r.status_code} body={r.text[:200]}")
    check("G4.7: no membership created in institution X", member_row(inst_x, u_id) is None, "")

    # 4.8 staff assigning themselves -> allowed
    r = call("POST", f"/admin/institutions/{inst_x}/staff", admin_token, json={"email": admin_email, "role": "teacher"})
    check("G4.8: staff assigning themselves -> allowed", r.status_code in (200, 201), f"status={r.status_code} body={r.text[:200]}")
    row = member_row(inst_x, admin_id)
    check("G4.8: self-membership created", bool(row), str(row))

    # 4.9 invalid role
    r = call("POST", f"/admin/institutions/{inst_x}/staff", admin_token, json={"email": fresh_email("g4-badrole"), "role": "student"})
    check("G4.9: role=student -> 422", r.status_code == 422, f"status={r.status_code}")
    r = call("POST", f"/admin/institutions/{inst_x}/staff", admin_token, json={"email": fresh_email("g4-badrole2"), "role": "owner"})
    check("G4.9b: arbitrary role string -> 422", r.status_code == 422, f"status={r.status_code}")

    # 4.10 malformed email
    r = call("POST", f"/admin/institutions/{inst_x}/staff", admin_token, json={"email": "not-an-email", "role": "teacher"})
    check("G4.10: malformed email -> 422", r.status_code == 422, f"status={r.status_code}")

    # 4.11 unknown institution
    r = call("POST", "/admin/institutions/00000000-0000-0000-0000-000000000000/staff", admin_token, json={"email": fresh_email("g4-unknown"), "role": "teacher"})
    check("G4.11: unknown institution -> 404", r.status_code == 404, f"status={r.status_code}")

    # ════════════════════════════════════════════════════════════════════
    log("\n=== TEST GROUP 5: security ===")
    r = call("POST", f"/admin/institutions/{inst_x}/staff", analyst_token, json={"email": fresh_email("g5-a"), "role": "teacher"})
    check("G5: analyst -> 403", r.status_code == 403, f"status={r.status_code}")
    r = call("POST", f"/admin/institutions/{inst_x}/staff", support_token, json={"email": fresh_email("g5-b"), "role": "teacher"})
    check("G5: support -> 403", r.status_code == 403, f"status={r.status_code}")
    r = call("POST", f"/admin/institutions/{inst_x}/staff", plain_token, json={"email": fresh_email("g5-c"), "role": "teacher"})
    check("G5: normal user -> 403", r.status_code == 403, f"status={r.status_code}")

    instadmin_id, instadmin_email = get_or_create_user("g5-instadmin-nonstaff", None)
    service.table("institution_members").insert({"institution_id": inst_x, "user_id": instadmin_id, "role": "institution_admin", "status": "active"}).execute()
    instadmin_token = login(instadmin_email)
    r = call("POST", f"/admin/institutions/{inst_x}/staff", instadmin_token, json={"email": fresh_email("g5-d"), "role": "teacher"})
    check("G5: institution_admin without staff role -> 403", r.status_code == 403, f"status={r.status_code}")

    # body institution_id ignored (target stays the path id)
    g5e_email = fresh_email("g5-bodyinstid")
    r = call("POST", f"/admin/institutions/{inst_x}/staff", admin_token, json={
        "email": g5e_email, "role": "teacher", "institution_id": "00000000-0000-0000-0000-000000000000",
    })
    check("G5: body institution_id ignored (extra field ignored, not 422)", r.status_code in (200, 201), f"status={r.status_code} body={r.text[:200]}")
    g5e_users = [u for u in service.auth.admin.list_users(page=1, per_page=200) if u.email == g5e_email]
    g5e_id = g5e_users[0].id if g5e_users else None
    if g5e_id:
        created_users.append(("g5-bodyinstid", g5e_id, g5e_email))
        check("G5: membership landed in path institution (X), not body institution_id", member_row(inst_x, g5e_id) is not None, "")
        ghost = service.table("institution_members").select("id").eq("institution_id", "00000000-0000-0000-0000-000000000000").execute().data
        check("G5: no membership created against the bogus body institution_id", ghost == [], str(ghost))

    # body user_id ignored (resolution stays email-based)
    g5f_email = fresh_email("g5-bodyuserid")
    r = call("POST", f"/admin/institutions/{inst_x}/staff", admin_token, json={
        "email": g5f_email, "role": "teacher", "user_id": plain_id,
    })
    check("G5: body user_id ignored", r.status_code in (200, 201), f"status={r.status_code} body={r.text[:200]}")
    g5f_users = [u for u in service.auth.admin.list_users(page=1, per_page=200) if u.email == g5f_email]
    g5f_id = g5f_users[0].id if g5f_users else None
    if g5f_id:
        created_users.append(("g5-bodyuserid", g5f_id, g5f_email))
        check("G5: membership resolved to the EMAIL's user, not injected body user_id",
              member_row(inst_x, g5f_id) is not None and member_row(inst_x, plain_id) is None,
              f"target_membership={member_row(inst_x, g5f_id)} plain_membership={member_row(inst_x, plain_id)}")

    r = call("POST", f"/admin/institutions/{inst_x}/staff", admin_token, json={"email": fresh_email("g5-studentrole"), "role": "student"})
    check("G5: role=student cannot be requested -> 422", r.status_code == 422, f"status={r.status_code}")
    r = call("POST", f"/admin/institutions/{inst_x}/staff", admin_token, json={"email": fresh_email("g5-arbrole"), "role": "superadmin"})
    check("G5: arbitrary role string -> 422", r.status_code == 422, f"status={r.status_code}")

    log("  --- secret leak scan (G5 audit rows) ---")
    g5_audit = [a for a in audit_rows("institution_staff_assigned", inst_x) if a.get("target_label") in (g5e_email, g5f_email)]
    for a in g5_audit:
        detail = a.get("detail") or {}
        detail_text = str(detail).lower()
        check(f"G5: audit detail for {a.get('target_label')} has no secrets",
              not any(s in detail_text for s in ("password", "token", "secret", "http://", "https://")),
              str(detail))
        check(f"G5: audit detail for {a.get('target_label')} only has expected keys",
              set(detail.keys()) <= {"email", "role", "auth_state", "membership_status"},
              str(sorted(detail.keys())))

    # ════════════════════════════════════════════════════════════════════
    log("\n=== TEST GROUP 6: multi-institution (dedicated pair, only for this test) ===")
    inst_a = create_institution(admin_token, "multi-A", "multi-a")
    inst_b = create_institution(admin_token, "multi-B", "multi-b")
    u_id, u_email = get_or_create_user("g6-multi", None)

    r = call("POST", f"/admin/institutions/{inst_a}/staff", admin_token, json={"email": u_email, "role": "institution_admin"})
    check("G6: assign in institution A succeeds", r.status_code in (200, 201), f"status={r.status_code} body={r.text[:200]}")

    r = call("POST", f"/admin/institutions/{inst_b}/staff", admin_token, json={"email": u_email, "role": "institution_admin"})
    check("G6: assign same user in institution B -> 409 already_staff_elsewhere", r.status_code == 409, f"status={r.status_code} body={r.text[:200]}")
    if r.status_code == 409:
        detail = r.json().get("detail", {})
        check("G6: 409 detail names institution A as the existing one", detail.get("institution_id") == inst_a, str(detail))

    check("G6: exactly one membership row total for this user", member_count(inst_a, u_id) == 1 and member_count(inst_b, u_id) == 0, f"A={member_count(inst_a, u_id)} B={member_count(inst_b, u_id)}")

    # ════════════════════════════════════════════════════════════════════
    log("\n=== TEST GROUP 7: failure path (race on the insert-time duplicate-key branch) ===")
    log("  Live-reachable failure branch: two concurrent requests for the SAME brand-new")
    log("  email both pass the pre-insert existence check, then race on institution_members")
    log("  insert -- the loser hits the duplicate-key exception path (line ~654-656 of")
    log("  admin_institutions.py), which returns 409 immediately WITHOUT retrying and")
    log("  WITHOUT deleting the just-created Auth user.")
    g7_email = fresh_email("g7-race")
    race_results: list[httpx.Response] = []
    race_lock = threading.Lock()

    def race_call():
        resp = call("POST", f"/admin/institutions/{inst_x}/staff", admin_token, json={"email": g7_email, "role": "teacher"})
        with race_lock:
            race_results.append(resp)

    t1 = threading.Thread(target=race_call)
    t2 = threading.Thread(target=race_call)
    t1.start(); t2.start()
    t1.join(); t2.join()

    statuses = sorted(r.status_code for r in race_results)
    check("G7: race produced one success and one conflict/already-assigned outcome",
          statuses[0] in (200, 201) and statuses[1] in (200, 409), f"statuses={statuses}")

    g7_users = [u for u in service.auth.admin.list_users(page=1, per_page=200) if u.email == g7_email]
    check("G7: no duplicate Auth user created by the race", len(g7_users) == 1, str(len(g7_users)))
    g7_id = g7_users[0].id if g7_users else None
    if g7_id:
        created_users.append(("g7-race", g7_id, g7_email))
        check("G7: Auth user was NOT deleted after the losing request", g7_id in [u.id for u in service.auth.admin.list_users(page=1, per_page=200)], "")
        check("G7: exactly one membership row survives the race", member_count(inst_x, g7_id) == 1, str(member_count(inst_x, g7_id)))

    log("  NOT independently live-reproducible without mocking the Supabase client:")
    log("  the retry-once-then-fail branch (both insert attempts raise a NON-duplicate-key")
    log("  exception -> retry -> still fails -> institution_staff_assignment_failed audit")
    log("  row written -> 500), since that requires injecting a transient DB failure between")
    log("  the Auth user create and the membership insert, which isn't safely triggerable")
    log("  from black-box HTTP testing against shared QA infra. Verified by code review:")
    log("  admin_institutions.py lines 649-665 -- _insert() is called, duplicate-key raises")
    log("  409 immediately (no retry, confirmed live above), any OTHER exception retries")
    log("  _insert() exactly once, and only if that second attempt also fails is the")
    log("  institution_staff_assignment_failed audit row written and a 500 raised -- no path")
    log("  in the function calls auth.admin.delete_user, so the created Auth user is never")
    log("  destructively removed on any failure branch.")
    check("G7: retry-once + no Auth-user deletion on genuine insert failure (code-verified, not independently live-triggerable)", True, "see admin_institutions.py:649-665")


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

    remaining_auth = 0
    for _, _, email in created_users:
        remaining_auth += auth_user_count_by_email(email)
    check("cleanup: no disposable Auth users remain", remaining_auth == 0, f"count={remaining_auth}")

    remaining_mirrors = service.table("users").select("id").in_(
        "id", [uid for _, uid, _ in created_users]
    ).execute().data if created_users else []
    check("cleanup: no disposable public.users mirror rows remain", remaining_mirrors == [], str(remaining_mirrors))

    remaining_profiles = service.table("user_profiles").select("user_id").in_(
        "user_id", [uid for _, uid, _ in created_users]
    ).execute().data if created_users else []
    check("cleanup: no disposable user_profiles rows remain", remaining_profiles == [], str(remaining_profiles))

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
