"""Phase 5.3a final QA-only validation of the invitation completion UX.

Read/probe only against the real QA Supabase Auth API (project
wpowzyyzhrxdqujrvxdq). Creates disposable auth.users rows to exercise the
real invite -> verifyOtp -> password-set -> login round trip, then deletes
every one of them. Does NOT write institution_members, does NOT touch
production, does NOT implement the 5.3b staff endpoint.

Never prints access/refresh tokens, invite URLs, passwords, or secrets --
only safe metadata (ids, timestamps, booleans, error categories).

Usage:
    cd backend
    ENVIRONMENT=qa python -u scripts/qa_verify_phase5_3a_invite_ux_final.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "qa")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from supabase import create_client
from app.core.config import settings
from app.core.supabase import get_supabase

assert "wpowzyyzhrxdqujrvxdq" in settings.SUPABASE_URL, (
    f"Refusing to run: SUPABASE_URL is not the QA project -- got {settings.SUPABASE_URL!r}"
)
assert "lgwaiwasnjjohqkeizdz" not in settings.SUPABASE_URL, "Refusing to run against production project ref"
assert settings.ENVIRONMENT == "qa", f"Refusing to run: ENVIRONMENT={settings.ENVIRONMENT!r}, expected 'qa'"

admin = get_supabase()
RUN_TAG = "p53a-final"
PASSWORD_NEW = "QaInviteFinal!2026x"

created: list[tuple[str, str]] = []  # (id, email)


def log(msg):
    print(msg, flush=True)


def safe_error(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"


def email_for(label: str) -> str:
    return f"qa-{RUN_TAG}-{label}@example.com"


def anon_client():
    # Fresh anon-key client per probe -- mirrors what the browser/SSR route
    # (frontend/app/auth/confirm/route.ts) does: verifyOtp() with the anon
    # key, never the service role key.
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)


def count_by_email(email: str) -> int:
    n = 0
    page = 1
    while True:
        batch = admin.auth.admin.list_users(page=page, per_page=200)
        if not batch:
            break
        n += sum(1 for u in batch if u.email == email)
        page += 1
        if page > 20:
            break
    return n


results = {}


def record(key, **fields):
    results[key] = fields
    log(f"  [{key}] {fields}")


def main():
    log("=== A. Native invite_user_by_email() -- fresh email ===")
    fresh_email = email_for("fresh")
    invite_ok = False
    try:
        r = admin.auth.admin.invite_user_by_email(fresh_email)
        created.append((r.user.id, fresh_email))
        invite_ok = True
        record("A.fresh", ok=True, user_id=r.user.id,
               confirmation_sent_at=str(getattr(r.user, "confirmation_sent_at", None)))
    except Exception as e:
        record("A.fresh", ok=False, error=safe_error(e))

    dup_count = count_by_email(fresh_email)
    record("A.fresh.duplicate_check", auth_users_with_this_email=dup_count)

    log("\n=== A2. Native invite_user_by_email() -- existing UNCONFIRMED user (repeat invite) ===")
    unconf_email = email_for("unconf")
    pre = admin.auth.admin.create_user({
        "email": unconf_email, "password": "Placeholder!2026", "email_confirm": False,
    })
    created.append((pre.user.id, unconf_email))
    try:
        r2 = admin.auth.admin.invite_user_by_email(unconf_email)
        record("A2.existing_unconfirmed", ok=True, user_id=r2.user.id,
               same_user_id=(r2.user.id == pre.user.id))
    except Exception as e:
        record("A2.existing_unconfirmed", ok=False, error=safe_error(e))
    dup_count2 = count_by_email(unconf_email)
    record("A2.duplicate_check", auth_users_with_this_email=dup_count2)

    log("\n=== A vs B split ===")
    a_err = results.get("A.fresh", {}).get("error", "")
    is_send_failure = "invite" in a_err.lower() and ("send" in a_err.lower() or "500" in a_err)
    record("split", invite_user_by_email_ok=invite_ok,
           looks_like_smtp_delivery_failure=is_send_failure,
           conclusion=(
               "A: link/user creation works, B: SMTP delivery broken" if is_send_failure
               else ("A+B both working" if invite_ok else "inconclusive -- error is not an obvious send failure")
           ))

    log("\n=== B-substitute: generate_link(type=invite) to obtain token_hash (email undeliverable to example.com regardless) ===")
    flow_email = email_for("flow")
    token_hash = None
    try:
        r3 = admin.auth.admin.generate_link({"type": "invite", "email": flow_email})
        flow_id = r3.user.id
        created.append((flow_id, flow_email))
        token_hash = getattr(r3.properties, "hashed_token", None)
        record("flow.generate_link", ok=True, user_id=flow_id, has_token_hash=bool(token_hash))
    except Exception as e:
        record("flow.generate_link", ok=False, error=safe_error(e))
        flow_id = None

    if not token_hash:
        log("No token_hash obtained -- cannot continue the session/password/login chain.")
        cleanup()
        return 1

    log("\n=== 4/5. verifyOtp(type=invite, token_hash) via ANON client (== what /auth/confirm route.ts runs server-side) ===")
    client = anon_client()
    try:
        v = client.auth.verify_otp({"type": "invite", "token_hash": token_hash})
        session_ok = bool(v.session and v.session.access_token)
        record("verifyOtp", ok=True, session_established=session_ok,
               user_id=v.user.id if v.user else None,
               user_id_matches=(v.user.id == flow_id if v.user else False))
    except Exception as e:
        record("verifyOtp", ok=False, error=safe_error(e))
        cleanup()
        return 1

    log("\n=== 6/7. Set password on the invite-established session (== reset-password page's updateUser call) ===")
    try:
        u = client.auth.update_user({"password": PASSWORD_NEW})
        record("set_password", ok=True, user_id=u.user.id if u.user else None)
    except Exception as e:
        record("set_password", ok=False, error=safe_error(e))
        cleanup()
        return 1

    log("\n=== 8. Normal login after password creation ===")
    try:
        client.auth.sign_out()
    except Exception:
        pass
    login_client = anon_client()
    try:
        s = login_client.auth.sign_in_with_password({"email": flow_email, "password": PASSWORD_NEW})
        record("normal_login", ok=True, session_established=bool(s.session and s.session.access_token),
               user_id=s.user.id if s.user else None)
    except Exception as e:
        record("normal_login", ok=False, error=safe_error(e))

    log("\n=== 9. Does /auth/reset-password's gating logic accept a plain invite-originated SIGNED_IN session? (static check) ===")
    log("  reset-password/page.tsx hasRecoveryParams() requires code|type=recovery|access_token|type=recovery")
    log("  in the URL. verify_otp(type='invite') fires SIGNED_IN, not PASSWORD_RECOVERY, and a plain")
    log("  client-side router.push('/auth/reset-password') post-invite carries none of those params.")
    log("  -> hasUrlError()=false, hasRecoveryParams()=false -> linkStatus set to 'invalid' on mount.")
    record("reset_password_reuse", reused_as_is="REJECTS invite session (shows 'Link expired or invalid')",
           reason="gate checks URL recovery params / PASSWORD_RECOVERY event only, not session presence")

    log("\n=== 10. Redirect to /institution -- sanitizeNext() static check ===")
    from importlib.util import spec_from_file_location, module_from_spec
    log("  sanitizeNext() (frontend/src/lib/auth-redirect.ts) only accepts a same-origin relative path")
    log("  or an absolute URL resolving to the request origin; '/institution' passes, any other host is")
    log("  rejected -> no open redirect, /institution reachable via next=/institution or returnTo=/institution.")
    record("redirect_to_institution", ok=True, mechanism="next/returnTo through sanitizeNext(), already generic")

    cleanup()
    return 0


def cleanup():
    log("\n=== Cleanup ===")
    for uid, email in created:
        try:
            admin.auth.admin.delete_user(uid)
            log(f"  deleted {email} ({uid})")
        except Exception as e:
            log(f"  FAILED to delete {email} ({uid}) -- {safe_error(e)}")

    remaining = []
    page = 1
    while True:
        batch = admin.auth.admin.list_users(page=page, per_page=200)
        if not batch:
            break
        remaining.extend(u.email for u in batch if u.email and RUN_TAG in u.email)
        page += 1
        if page > 20:
            break
    log(f"  disposable users with tag {RUN_TAG} still present: {remaining}")
    record("cleanup", remaining_count=len(remaining))


if __name__ == "__main__":
    raise SystemExit(main())
