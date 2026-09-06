"""Phase 5.4 Step 2 live QA verification -- staff-facing invitation
management (POST/GET/revoke /admin/institutions/{id}/invites...) plus
compatibility with the existing Phase 2 public preview/accept path.

Drives the running QA-mode backend (BACKEND_URL) through the real HTTP API
against the QA Supabase project ONLY (wpowzyyzhrxdqujrvxdq), using only
disposable fixtures, then prints a pass/fail summary and cleans up every row
it created. Same pattern as qa_verify_phase5_4_status_management.py.

Usage:
    cd backend
    ENVIRONMENT=qa .venv-qa/Scripts/python.exe -u scripts/qa_verify_phase5_4_step2_invitations.py
"""
from __future__ import annotations

import os
import sys
import time
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
created_invite_ids: list[str] = []
results: list[tuple[str, str, str]] = []


def log(msg):
    print(msg, flush=True)


def check(name: str, cond: bool, detail: str = ""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    log(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))


def fresh_email(label: str) -> str:
    return f"qa-p54s2-{label}-{RUN_TAG}@{FIXTURE_DOMAIN}"


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


def invite_row(invite_id: str) -> dict:
    return service.table("institution_invites").select("*").eq("id", invite_id).execute().data[0]


def invite_count(institution_id: str) -> int:
    return len((
        service.table("institution_invites").select("id").eq("institution_id", institution_id).execute()
    ).data or [])


def member_row(institution_id: str, user_id: str) -> dict | None:
    rows = (
        service.table("institution_members").select("*")
        .eq("institution_id", institution_id).eq("user_id", user_id).execute()
    ).data or []
    return rows[0] if rows else None


def membership_count(user_id: str) -> int:
    return len((
        service.table("institution_members").select("id").eq("user_id", user_id).execute()
    ).data or [])


def create_institution(admin_token: str, label: str, slug_suffix: str, modules=None, quota: int = 10) -> str:
    slug = f"qa-p54s2-{slug_suffix}-{RUN_TAG}"
    r = call("POST", "/admin/institutions", admin_token, json={
        "name": f"QA Phase 5.4 Step2 {label} {RUN_TAG}",
        "slug": slug,
        "contact_email": f"qa-p54s2-contact-{slug_suffix}-{RUN_TAG}@example.com",
        "status": "active",
        "modules": modules if modules is not None else ["speaking"],
        "speaking_sessions_per_month": quota,
    })
    check(f"setup: create institution '{label}' -> 201", r.status_code == 201, f"status={r.status_code} body={r.text[:200]}")
    body = r.json() if r.status_code == 201 else {}
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
    log("=== Fixture setup: staff users (admin/analyst/support/plain) ===")
    admin_id, admin_email = get_or_create_user("admin", "admin")
    analyst_id, analyst_email = get_or_create_user("analyst", "analyst")
    support_id, support_email = get_or_create_user("support", "support")
    plain_id, plain_email = get_or_create_user("plainuser", None)
    admin_token = login(admin_email)
    analyst_token = login(analyst_email)
    support_token = login(support_email)
    plain_token = login(plain_email)

    # ════════════════════════════════════════════════════════════════════
    log("\n=== SECTION 1: disposable institution + staff admin ===")
    inst_a = create_institution(admin_token, "A", "a", modules=["speaking"], quota=10)
    ia_id, ia_email = get_or_create_user("inst-admin", None, confirm=True)
    assign_staff(admin_token, inst_a, ia_email, "institution_admin")
    row = member_row(inst_a, ia_id)
    check("S1: membership active institution_admin", bool(row) and row.get("status") == "active" and row.get("role") == "institution_admin", str(row))
    ia_token = login(ia_email)

    # ════════════════════════════════════════════════════════════════════
    log("\n=== SECTION 2: create bounded invitation (max_uses=1) ===")
    expires_bounded = "2099-01-01T00:00:00Z"
    r = call("POST", f"/admin/institutions/{inst_a}/invites", admin_token, json={
        "max_uses": 1, "expires_at": expires_bounded,
    })
    check("S2: create -> 201", r.status_code == 201, f"status={r.status_code} body={r.text[:200]}")
    body = r.json() if r.status_code == 201 else {}
    check("S2: role=student", body.get("role") == "student", str(body))
    bounded_token = body.get("token")
    bounded_invite_id = body.get("id")
    if bounded_invite_id:
        created_invite_ids.append(bounded_invite_id)
    check("S2: token returned", bool(bounded_token), str(body))
    check("S2: join_url returned", bool(body.get("join_url")), str(body))
    expected_join_url = f"{settings.FRONTEND_URL}/join/{bounded_token}" if bounded_token else None
    check("S2: join_url matches {FRONTEND_URL}/join/{token} shape (prod join-page pattern)",
          body.get("join_url") == expected_join_url,
          f"got={body.get('join_url')} expected={expected_join_url}")

    db_row = invite_row(bounded_invite_id) if bounded_invite_id else {}
    check("S2: exactly one invitation row created", invite_count(inst_a) == 1, f"count={invite_count(inst_a)}")
    check("S2: max_uses=1", db_row.get("max_uses") == 1, str(db_row))
    check("S2: use_count=0", db_row.get("use_count") == 0, str(db_row))
    check("S2: remaining_uses=1 (derived)", (db_row.get("max_uses") or 0) - (db_row.get("use_count") or 0) == 1, str(db_row))
    check("S2: expires_at correct", str(db_row.get("expires_at", "")).startswith("2099-01-01"), str(db_row.get("expires_at")))

    audit_created = audit_rows("institution_invite_created", bounded_invite_id) if bounded_invite_id else []
    check("S2: audit event institution_invite_created exists", len(audit_created) == 1, str(audit_created))
    if audit_created:
        detail_str = str(audit_created[0].get("detail"))
        check("S2: audit detail contains NO token", bounded_token not in detail_str, detail_str)
        check("S2: audit detail contains NO join_url", body.get("join_url") not in detail_str, detail_str)

    # ════════════════════════════════════════════════════════════════════
    log("\n=== SECTION 3: token privacy on list ===")
    r = call("GET", f"/admin/institutions/{inst_a}/invites", analyst_token)
    check("S3: list -> 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    listed = r.json() if r.status_code == 200 else []
    found = next((x for x in listed if x.get("id") == bounded_invite_id), None)
    check("S3: bounded invite present in list", found is not None, str(listed))
    if found:
        leaked_keys = [k for k in ("token", "join_url", "created_by") if k in found]
        check("S3: list row has no token/join_url/created_by", leaked_keys == [], str(found))
        allowed_keys = {"id", "status", "max_uses", "use_count", "remaining_uses", "expires_at", "created_at"}
        extra_keys = set(found.keys()) - allowed_keys
        check("S3: list row has no unnecessary internal identifiers", extra_keys == set(), str(found))
    list_text = r.text
    check("S3: raw token does not appear anywhere in list response", bounded_token not in list_text, "")

    # ════════════════════════════════════════════════════════════════════
    log("\n=== SECTION 4: public preview compatibility ===")
    r = call("GET", f"/institutions/invites/{bounded_token}")
    check("S4: public preview -> 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    preview = r.json() if r.status_code == 200 else {}
    check("S4: institution name correct", preview.get("institution_name", "").startswith("QA Phase 5.4 Step2 A"), str(preview))
    check("S4: enabled modules correct (speaking only)", preview.get("modules") == ["speaking"], str(preview))
    allowed_preview_keys = {"institution_name", "logo_url", "modules", "expires_at"}
    check("S4: no internal fields leaked", set(preview.keys()) <= allowed_preview_keys, str(preview))
    check("S4: preview does not leak institution_id/token/id", not any(k in preview for k in ("id", "institution_id", "token", "status")), str(preview))

    # ════════════════════════════════════════════════════════════════════
    log("\n=== SECTION 5: full student acceptance ===")
    student1_id, student1_email = get_or_create_user("student1", None, confirm=True)
    student1_token = login(student1_email)

    r = call("GET", f"/institutions/invites/{bounded_token}")
    check("S5: preview before accept -> 200", r.status_code == 200, f"status={r.status_code}")

    r = call("POST", f"/institutions/invites/{bounded_token}/accept", student1_token)
    check("S5: accept -> 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    accept_body = r.json() if r.status_code == 200 else {}
    check("S5: accept status=joined", accept_body.get("status") == "joined", str(accept_body))

    mrow = member_row(inst_a, student1_id)
    check("S5: membership role=student", bool(mrow) and mrow.get("role") == "student", str(mrow))
    check("S5: membership status=active", bool(mrow) and mrow.get("status") == "active", str(mrow))
    check("S5: institution_id correct", bool(mrow) and mrow.get("institution_id") == inst_a, str(mrow))

    db_row = invite_row(bounded_invite_id)
    check("S5: use_count becomes 1", db_row.get("use_count") == 1, str(db_row))
    remaining = (db_row.get("max_uses") or 0) - (db_row.get("use_count") or 0)
    check("S5: remaining_uses becomes 0", remaining == 0, str(db_row))

    r = call("GET", "/sessions/usage", student1_token)
    usage = r.json() if r.status_code == 200 else {}
    check("S5: student receives Speaking institution access",
          r.status_code == 200 and "speaking" in usage.get("institution_modules", []),
          f"status={r.status_code} body={r.text[:200]}")
    check("S5: Reading/Listening/Writing/Mock remain blocked (institution_modules == ['speaking'] only)",
          usage.get("institution_modules") == ["speaking"], str(usage.get("institution_modules")))
    check("S5: no other institution membership created (exactly 1 total)", membership_count(student1_id) == 1, "")

    # ════════════════════════════════════════════════════════════════════
    log("\n=== SECTION 6: exhaustion (max_uses=1 already used) ===")
    student2_id, student2_email = get_or_create_user("student2", None, confirm=True)
    student2_token = login(student2_email)

    r = call("POST", f"/institutions/invites/{bounded_token}/accept", student2_token)
    check("S6: second accept attempt -> generic 400 'invalid/unusable'", r.status_code == 400, f"status={r.status_code} body={r.text[:200]}")
    check("S6: no membership created for student2", member_row(inst_a, student2_id) is None, "")
    db_row = invite_row(bounded_invite_id)
    check("S6: use_count remains 1", db_row.get("use_count") == 1, str(db_row))

    # ════════════════════════════════════════════════════════════════════
    log("\n=== SECTION 7: unlimited invitation ===")
    r = call("POST", f"/admin/institutions/{inst_a}/invites", admin_token, json={"max_uses": None, "expires_at": None})
    check("S7: create -> 201", r.status_code == 201, f"status={r.status_code} body={r.text[:200]}")
    body = r.json() if r.status_code == 201 else {}
    unlimited_token = body.get("token")
    unlimited_invite_id = body.get("id")
    if unlimited_invite_id:
        created_invite_ids.append(unlimited_invite_id)
    check("S7: max_uses=null", body.get("max_uses") is None, str(body))
    check("S7: token returned", bool(unlimited_token), str(body))

    r = call("GET", f"/admin/institutions/{inst_a}/invites", analyst_token)
    listed = r.json() if r.status_code == 200 else []
    found = next((x for x in listed if x.get("id") == unlimited_invite_id), None)
    check("S7: remaining_uses=null in list (unlimited shown correctly)", bool(found) and found.get("remaining_uses") is None and found.get("max_uses") is None, str(found))
    check("S7: token returned only once (not present in list)", found is not None and "token" not in found, str(found))

    r = call("GET", f"/institutions/invites/{unlimited_token}")
    check("S7: public preview works", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")

    # ════════════════════════════════════════════════════════════════════
    log("\n=== SECTION 8: expiration ===")
    from datetime import datetime, timedelta, timezone
    soon = (datetime.now(timezone.utc) + timedelta(seconds=4)).isoformat()
    r = call("POST", f"/admin/institutions/{inst_a}/invites", admin_token, json={"max_uses": None, "expires_at": soon})
    check("S8: create with near-future expiry -> 201", r.status_code == 201, f"status={r.status_code} body={r.text[:200]}")
    body = r.json() if r.status_code == 201 else {}
    expiring_token = body.get("token")
    expiring_invite_id = body.get("id")
    if expiring_invite_id:
        created_invite_ids.append(expiring_invite_id)

    log("  waiting 6s for invite to expire...")
    time.sleep(6)

    r = call("GET", f"/admin/institutions/{inst_a}/invites", analyst_token)
    listed = r.json() if r.status_code == 200 else []
    found = next((x for x in listed if x.get("id") == expiring_invite_id), None)
    check("S8: admin list still shows the row post-expiry (status/expires_at unchanged by read, matching existing contract)",
          bool(found) and found.get("status") == "active", str(found))

    r = call("GET", f"/institutions/invites/{expiring_token}")
    check("S8: public preview rejects expired invite -> 404", r.status_code == 404, f"status={r.status_code} body={r.text[:200]}")

    student3_id, student3_email = get_or_create_user("student3", None, confirm=True)
    student3_token = login(student3_email)
    r = call("POST", f"/institutions/invites/{expiring_token}/accept", student3_token)
    check("S8: accept attempt on expired invite -> 400", r.status_code == 400, f"status={r.status_code} body={r.text[:200]}")
    check("S8: no membership created from expired invite", member_row(inst_a, student3_id) is None, "")

    # ════════════════════════════════════════════════════════════════════
    log("\n=== SECTION 9: revoke ===")
    r = call("POST", f"/admin/institutions/{inst_a}/invites", admin_token, json={"max_uses": None, "expires_at": None})
    check("S9: create second disposable invite -> 201", r.status_code == 201, f"status={r.status_code}")
    body = r.json() if r.status_code == 201 else {}
    revoke_token = body.get("token")
    revoke_invite_id = body.get("id")
    if revoke_invite_id:
        created_invite_ids.append(revoke_invite_id)

    r = call("POST", f"/admin/institutions/{inst_a}/invites/{revoke_invite_id}/revoke", admin_token)
    check("S9: revoke -> 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    db_row = invite_row(revoke_invite_id)
    check("S9: DB status=revoked", db_row.get("status") == "revoked", str(db_row))
    audit_revoked = audit_rows("institution_invite_revoked", revoke_invite_id)
    check("S9: audit event institution_invite_revoked exists", len(audit_revoked) == 1, str(audit_revoked))

    r = call("GET", f"/admin/institutions/{inst_a}/invites", analyst_token)
    check("S9: token never returned from list", revoke_token not in r.text, "")

    r = call("GET", f"/institutions/invites/{revoke_token}")
    check("S9: public preview -> generic not-found for revoked invite", r.status_code == 404, f"status={r.status_code} body={r.text[:200]}")

    # ════════════════════════════════════════════════════════════════════
    log("\n=== SECTION 10: cross-tenant revoke ===")
    inst_b = create_institution(admin_token, "B", "b", modules=["speaking"], quota=5)
    r = call("POST", f"/admin/institutions/{inst_b}/invites", admin_token, json={"max_uses": None, "expires_at": None})
    check("S10: create invite in institution B -> 201", r.status_code == 201, f"status={r.status_code}")
    body = r.json() if r.status_code == 201 else {}
    b_invite_id = body.get("id")
    if b_invite_id:
        created_invite_ids.append(b_invite_id)

    r = call("POST", f"/admin/institutions/{inst_a}/invites/{b_invite_id}/revoke", admin_token)
    check("S10: revoke B's invite via A's path -> 404", r.status_code == 404, f"status={r.status_code} body={r.text[:200]}")
    db_row = invite_row(b_invite_id)
    check("S10: B invite remains unchanged (still active)", db_row.get("status") == "active", str(db_row))
    audit_cross = audit_rows("institution_invite_revoked", b_invite_id)
    check("S10: no audit event for a successful revoke", len(audit_cross) == 0, str(audit_cross))
    check("S10: 404 body carries no institution-B-specific info", "institution_id" not in r.text and inst_b not in r.text, r.text[:200])

    # ════════════════════════════════════════════════════════════════════
    log("\n=== SECTION 11: authorization ===")
    r = call("POST", f"/admin/institutions/{inst_a}/invites", admin_token, json={"max_uses": None, "expires_at": None})
    check("S11: admin create allowed -> 201", r.status_code == 201, f"status={r.status_code}")
    admin_check_invite = r.json().get("id") if r.status_code == 201 else None
    if admin_check_invite:
        created_invite_ids.append(admin_check_invite)
        r2 = call("POST", f"/admin/institutions/{inst_a}/invites/{admin_check_invite}/revoke", admin_token)
        check("S11: admin revoke allowed -> 200", r2.status_code == 200, f"status={r2.status_code}")
    r = call("GET", f"/admin/institutions/{inst_a}/invites", admin_token)
    check("S11: admin list allowed -> 200", r.status_code == 200, f"status={r.status_code}")

    r = call("GET", f"/admin/institutions/{inst_a}/invites", analyst_token)
    check("S11: analyst list allowed -> 200", r.status_code == 200, f"status={r.status_code}")
    r = call("POST", f"/admin/institutions/{inst_a}/invites", analyst_token, json={"max_uses": None, "expires_at": None})
    check("S11: analyst create denied -> 403", r.status_code == 403, f"status={r.status_code}")
    r = call("POST", f"/admin/institutions/{inst_a}/invites/{bounded_invite_id}/revoke", analyst_token)
    check("S11: analyst revoke denied -> 403", r.status_code == 403, f"status={r.status_code}")

    r = call("GET", f"/admin/institutions/{inst_a}/invites", support_token)
    check("S11: support list denied -> 403", r.status_code == 403, f"status={r.status_code}")
    r = call("POST", f"/admin/institutions/{inst_a}/invites", support_token, json={"max_uses": None, "expires_at": None})
    check("S11: support create denied -> 403", r.status_code == 403, f"status={r.status_code}")
    r = call("POST", f"/admin/institutions/{inst_a}/invites/{bounded_invite_id}/revoke", support_token)
    check("S11: support revoke denied -> 403", r.status_code == 403, f"status={r.status_code}")

    for path, method, kw in [
        (f"/admin/institutions/{inst_a}/invites", "GET", {}),
        (f"/admin/institutions/{inst_a}/invites", "POST", {"json": {"max_uses": None, "expires_at": None}}),
        (f"/admin/institutions/{inst_a}/invites/{bounded_invite_id}/revoke", "POST", {}),
    ]:
        r = call(method, path, plain_token, **kw)
        check(f"S11: normal B2C user denied on {method} {path.split('/')[-1]} -> 403", r.status_code == 403, f"status={r.status_code}")

    for path, method, kw in [
        (f"/admin/institutions/{inst_a}/invites", "GET", {}),
        (f"/admin/institutions/{inst_a}/invites", "POST", {"json": {"max_uses": None, "expires_at": None}}),
        (f"/admin/institutions/{inst_a}/invites/{bounded_invite_id}/revoke", "POST", {}),
    ]:
        r = call(method, path, ia_token, **kw)
        check(f"S11: institution_admin (no staff role) denied on {method} {path.split('/')[-1]} -> 403", r.status_code == 403, f"status={r.status_code}")

    # ════════════════════════════════════════════════════════════════════
    log("\n=== SECTION 12: validation ===")
    before_count = invite_count(inst_a)
    r = call("POST", f"/admin/institutions/{inst_a}/invites", admin_token, json={"max_uses": 0})
    check("S12: max_uses=0 -> 422", r.status_code == 422, f"status={r.status_code} body={r.text[:150]}")
    r = call("POST", f"/admin/institutions/{inst_a}/invites", admin_token, json={"max_uses": -1})
    check("S12: max_uses<0 -> 422", r.status_code == 422, f"status={r.status_code} body={r.text[:150]}")
    r = call("POST", f"/admin/institutions/{inst_a}/invites", admin_token, json={"max_uses": "abc"})
    check("S12: non-integer max_uses -> 422", r.status_code == 422, f"status={r.status_code} body={r.text[:150]}")
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    r = call("POST", f"/admin/institutions/{inst_a}/invites", admin_token, json={"expires_at": past})
    check("S12: past expiration -> 422", r.status_code == 422, f"status={r.status_code} body={r.text[:150]}")
    r = call("POST", "/admin/institutions/00000000-0000-0000-0000-000000000000/invites", admin_token, json={"max_uses": 1})
    check("S12: invalid institution -> 404", r.status_code == 404, f"status={r.status_code} body={r.text[:150]}")
    after_count = invite_count(inst_a)
    check("S12: no invite row created by any failed validation", before_count == after_count, f"before={before_count} after={after_count}")

    # ════════════════════════════════════════════════════════════════════
    log("\n=== SECTION 13: rate limiter (dedicated identity, 20/hour) ===")
    rl_admin_id, rl_admin_email = get_or_create_user("rl-admin", "admin")
    rl_admin_token = login(rl_admin_email)
    rl_created = []
    allowed_count = 0
    for i in range(20):
        r = call("POST", f"/admin/institutions/{inst_a}/invites", rl_admin_token, json={"max_uses": None, "expires_at": None})
        if r.status_code == 201:
            allowed_count += 1
            iid = r.json().get("id")
            rl_created.append(iid)
            created_invite_ids.append(iid)
        else:
            log(f"  unexpected status on call {i+1}: {r.status_code} {r.text[:150]}")
    check("S13: first 20 calls allowed", allowed_count == 20, f"allowed={allowed_count}")

    r = call("POST", f"/admin/institutions/{inst_a}/invites", rl_admin_token, json={"max_uses": None, "expires_at": None})
    check("S13: 21st call -> 429", r.status_code == 429, f"status={r.status_code} body={r.text[:150]}")

    # ════════════════════════════════════════════════════════════════════
    log("\n=== SECTION 14: token security sweep ===")
    all_tokens = [t for t in (bounded_token, unlimited_token, expiring_token, revoke_token) if t]
    r_list = call("GET", f"/admin/institutions/{inst_a}/invites", analyst_token)
    r_preview = call("GET", f"/institutions/invites/{unlimited_token}")
    audit_all = (
        service.table("audit_log").select("detail")
        .in_("action", ["institution_invite_created", "institution_invite_revoked"])
        .execute()
    ).data or []
    audit_text = str(audit_all)
    leaks = []
    for t in all_tokens:
        if t in r_list.text:
            leaks.append(f"list:{t[:8]}")
        if t != unlimited_token and t in r_preview.text:
            leaks.append(f"preview:{t[:8]}")
        if t in audit_text:
            leaks.append(f"audit:{t[:8]}")
    check("S14: raw tokens not leaked in list/preview/audit_log", leaks == [], str(leaks))

    # ════════════════════════════════════════════════════════════════════
    log("\n=== SECTION 15: regression ===")
    import subprocess
    py = sys.executable
    r1 = subprocess.run([py, "-m", "pytest", "tests/test_admin_institutions.py", "-q"], cwd=str(Path(__file__).resolve().parents[1]), capture_output=True, text=True)
    check("S15: pytest test_admin_institutions.py -q passes", r1.returncode == 0, (r1.stdout[-1500:] + r1.stderr[-500:]))
    r2 = subprocess.run([py, "-m", "pytest", "tests", "-k", "institution", "-q"], cwd=str(Path(__file__).resolve().parents[1]), capture_output=True, text=True)
    check("S15: pytest tests -k institution -q passes", r2.returncode == 0, (r2.stdout[-1500:] + r2.stderr[-500:]))
    r3 = subprocess.run([py, "-c", "import app.main"], cwd=str(Path(__file__).resolve().parents[1]), capture_output=True, text=True)
    check("S15: python -c 'import app.main' succeeds", r3.returncode == 0, (r3.stdout[-800:] + r3.stderr[-800:]))

    globals()["_inst_a"] = inst_a
    globals()["_inst_b"] = inst_b


def finish():
    log("\n=== Summary (pre-cleanup) ===")
    failed = [x for x in results if x[0] == "FAIL"]
    log(f"{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        log("FAILURES:")
        for status, name, detail in failed:
            log(f"  - {name}: {detail}")

    log("\n=== SECTION 16: cleanup ===")
    inst_ids = [iid for _, iid in created_institutions]
    if inst_ids:
        service.table("institution_invites").delete().in_("institution_id", inst_ids).execute()
        service.table("institution_members").delete().in_("institution_id", inst_ids).execute()
        service.table("institution_modules").delete().in_("institution_id", inst_ids).execute()
        service.table("audit_log").delete().in_("target_id", inst_ids).execute()
        if created_invite_ids:
            service.table("audit_log").delete().in_("target_id", created_invite_ids).execute()
        service.table("audit_log").delete().in_("target_label", inst_ids).execute()
        service.table("institutions").delete().in_("id", inst_ids).execute()
        log(f"  deleted institutions: {inst_ids}")

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

    remaining_inst = service.table("institutions").select("id").in_("id", inst_ids).execute().data if inst_ids else []
    check("cleanup: no disposable institution rows remain", remaining_inst == [], str(remaining_inst))
    remaining_invites = service.table("institution_invites").select("id").in_("institution_id", inst_ids).execute().data if inst_ids else []
    check("cleanup: no disposable invite rows remain", remaining_invites == [], str(remaining_invites))
    remaining_members = service.table("institution_members").select("id").in_("institution_id", inst_ids).execute().data if inst_ids else []
    check("cleanup: no disposable membership rows remain", remaining_members == [], str(remaining_members))
    remaining_audit = service.table("audit_log").select("id").in_("target_id", inst_ids).execute().data if inst_ids else []
    check("cleanup: no disposable audit rows remain (institution-targeted)", remaining_audit == [], str(remaining_audit))
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
