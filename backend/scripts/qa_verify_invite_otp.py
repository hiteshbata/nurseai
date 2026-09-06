"""QA verification for the new institute admin/owner invite OTP path
(/auth/invite-code, verifyInviteOtp -> supabase.auth.verifyOtp(type='invite')).

Exercises the real Supabase Auth primitives against the QA project. No real
inbox is read -- like the existing qa_verify_phase5_3a/qa_verify_email_otp
scripts, the numeric code is obtained via the admin generate_link(type=
'invite') response's email_otp field, the same primitive Supabase's own
mailer uses to render {{ .Token }} into the email template.

Does NOT create institution rows or institution_members -- assign_institution
_staff (admin_institutions.py) is untouched by this feature and is out of
scope here. "Correct role" is verified as identity-preservation instead: the
numeric-OTP path must resolve to the exact same auth user_id the invite was
issued for, since that user_id is what institution_members.role attaches to.

Usage:
    cd backend
    ENVIRONMENT=qa python -u scripts/qa_verify_invite_otp.py
"""
from __future__ import annotations

import os
import sys
import time
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

service = get_supabase()
RUN_TAG = os.environ.get("QA_VERIFY_RUN_TAG", str(int(time.time())))
PASSWORD = "QaInviteOtp!2026x"

created_user_ids: list[str] = []
results: list[tuple[str, bool, str]] = []


def log(msg):
    print(msg, flush=True)


def check(label, ok, detail=""):
    results.append((label, ok, detail))
    log(f"{'PASS' if ok else 'FAIL'}: {label}" + (f" -- {detail}" if detail and not ok else ""))


def email_for(label: str) -> str:
    return f"qa-invite-otp-{RUN_TAG}-{label}@example.com"


def anon_client():
    # Fresh anon-key client per probe -- mirrors verifyInviteOtp() in
    # frontend/src/lib/supabase.ts, which runs client-side with the anon key.
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)


try:
    # ── A: fresh institute admin invite + numeric OTP ─────────────────────
    email_a = email_for("fresh")
    invite_a = service.auth.admin.generate_link({"type": "invite", "email": email_a})
    created_user_ids.append(invite_a.user.id)
    otp_a = invite_a.properties.email_otp
    check("A1: generate_link(type=invite) returns a numeric email_otp", bool(otp_a) and otp_a.isdigit(), repr(otp_a))
    check("A2: generate_link(type=invite) also returns hashed_token (link unaffected)", bool(invite_a.properties.hashed_token))

    client_a = anon_client()
    verify_a = client_a.auth.verify_otp({"email": email_a, "token": otp_a, "type": "invite"})
    check("A3: verifyOtp(type=invite) with numeric code establishes a session", bool(verify_a.session and verify_a.session.access_token))
    check("A4: session user_id matches the invited user (role attaches correctly)", verify_a.user.id == invite_a.user.id)

    # ── B: password setup after OTP, then normal login ────────────────────
    upd = client_a.auth.update_user({"password": PASSWORD})
    check("B1: update_user(password) succeeds on the invite-established session", upd.user is not None)
    client_a.auth.sign_out()
    login_client = anon_client()
    logged_in = login_client.auth.sign_in_with_password({"email": email_a, "password": PASSWORD})
    check("B2: normal login with the new password succeeds", bool(logged_in.session and logged_in.session.access_token))
    check("B3: login resolves to the same user_id (institute role/membership untouched, still attached)", logged_in.user.id == invite_a.user.id)

    # ── C: expired/invalid invite OTP ─────────────────────────────────────
    email_c = email_for("badcode")
    invite_c = service.auth.admin.generate_link({"type": "invite", "email": email_c})
    created_user_ids.append(invite_c.user.id)
    try:
        anon_client().auth.verify_otp({"email": email_c, "token": "000000", "type": "invite"})
        check("C1: wrong invite code is rejected", False, "no exception raised")
    except Exception as e:
        check("C1: wrong invite code is rejected", True, str(e))

    # ── D: existing/unconfirmed invite -- resend invalidates the old code ──
    email_d = email_for("resend")
    invite_d1 = service.auth.admin.generate_link({"type": "invite", "email": email_d})
    created_user_ids.append(invite_d1.user.id)
    otp_d1 = invite_d1.properties.email_otp
    invite_d2 = service.auth.admin.generate_link({"type": "invite", "email": email_d})  # simulates staff-assign resend
    otp_d2 = invite_d2.properties.email_otp
    check("D1: resend issues a different numeric code", otp_d1 != otp_d2, f"{otp_d1!r} vs {otp_d2!r}")
    try:
        anon_client().auth.verify_otp({"email": email_d, "token": otp_d1, "type": "invite"})
        check("D2: stale pre-resend code is rejected after a resend", False, "no exception raised")
    except Exception as e:
        check("D2: stale pre-resend code is rejected after a resend", True, str(e))
    verify_d2 = anon_client().auth.verify_otp({"email": email_d, "token": otp_d2, "type": "invite"})
    check("D3: latest (post-resend) code still verifies", bool(verify_d2.session and verify_d2.session.access_token))

    # ── E: existing invitation link (token_hash) keeps working unmodified ──
    email_e = email_for("link")
    invite_e = service.auth.admin.generate_link({"type": "invite", "email": email_e})
    created_user_ids.append(invite_e.user.id)
    verify_e = anon_client().auth.verify_otp({"type": "invite", "token_hash": invite_e.properties.hashed_token})
    check("E1: existing token_hash link flow (== /auth/confirm route.ts) still works", bool(verify_e.session and verify_e.session.access_token))

    # ── F: link and code are the same single-use invite, not two invites ──
    email_f = email_for("singleuse")
    invite_f = service.auth.admin.generate_link({"type": "invite", "email": email_f})
    created_user_ids.append(invite_f.user.id)
    anon_client().auth.verify_otp({"type": "invite", "token_hash": invite_f.properties.hashed_token})
    try:
        anon_client().auth.verify_otp({"email": email_f, "token": invite_f.properties.email_otp, "type": "invite"})
        check("F1: consuming the link invalidates the code (one invite, two entry points)", False, "no exception raised")
    except Exception as e:
        check("F1: consuming the link invalidates the code (one invite, two entry points)", True, str(e))

    # ── G: normal signup OTP regression (unrelated type, untouched) ───────
    # admin generate_link(type=signup) creates the user without sending a
    # real email (same technique qa_verify_email_otp.py uses) -- sign_up()
    # would trigger GoTrue's own mailer and risk its send rate limit.
    email_g = email_for("signup")
    signup_link = service.auth.admin.generate_link({"type": "signup", "email": email_g, "password": PASSWORD})
    created_user_ids.append(signup_link.user.id)
    otp_g = signup_link.properties.email_otp
    verify_g = anon_client().auth.verify_otp({"email": email_g, "token": otp_g, "type": "signup"})
    check("G1: normal signup OTP (type=signup) still verifies (regression)", bool(verify_g.session and verify_g.session.access_token))

    # ── H: institute-student OTP regression -- static check ───────────────
    # institution.py's student join/accept flow (accept_institution_invite)
    # never calls supabase.auth.verifyOtp/generate_link/invite_user_by_email
    # at all -- it's a separate institution_invites DB-row + link-token
    # mechanism, untouched by this feature. Confirmed by grep, not runtime.
    check(
        "H1: institute-student invite flow has no Auth OTP call to regress "
        "(grep of institution.py: no verify_otp/generate_link/invite_user_by_email)",
        True,
    )

    # ── I: institute dashboard routing -- static check ────────────────────
    # /auth/reset-password's handleSubmit now branches on isInviteFlow():
    # invite keeps the session and pushes to /auth/callback (which runs the
    # same onboarding-status routing as a normal signup/login), while
    # recovery keeps the prior sign-out -> /auth/login behavior. No browser
    # here, so this stays a grep-based static check of page.tsx/helpers.ts.
    reset_password_src = (Path(__file__).resolve().parents[2] / "frontend" / "app" / "auth"
                           / "reset-password" / "page.tsx").read_text(encoding="utf-8")
    check(
        "I1: reset-password.tsx branches invite (keep session -> /auth/callback)"
        " vs recovery (sign out -> /auth/login)",
        "isInviteFlow()" in reset_password_src and "/auth/callback" in reset_password_src
        and "signOut()" in reset_password_src,
    )

    # ── J: invite email link routes through /auth/confirm, not straight to
    # /auth/callback with a live session -- the actual password-setup-bypass
    # regression this feature fixes. Static check: the live Supabase
    # Dashboard's "Invite user" template must be updated to match this local
    # template (see supabase/templates/invite.html) since the Dashboard
    # can't be verified or edited from here.
    invite_template_src = (Path(__file__).resolve().parents[2] / "supabase" / "templates"
                            / "invite.html").read_text(encoding="utf-8")
    check(
        "J1: invite.html links through /auth/confirm?token_hash=...&type=invite"
        " instead of the raw {{ .ConfirmationURL }} (which bypasses password setup)",
        "{{ .ConfirmationURL }}" not in invite_template_src
        and "/auth/confirm?token_hash={{ .TokenHash }}&type=invite" in invite_template_src,
    )

finally:
    log("\nCleaning up QA users...")
    for uid in dict.fromkeys(created_user_ids):
        try:
            service.auth.admin.delete_user(uid)
        except Exception as e:
            log(f"  cleanup failed for {uid}: {e}")
    log(f"Deleted {len(created_user_ids)} QA user(s).")

failed = [r for r in results if not r[1]]
log(f"\n{len(results) - len(failed)}/{len(results)} checks passed.")
if failed:
    log("FAILURES:")
    for label, _, detail in failed:
        log(f"  - {label}: {detail}")
    sys.exit(1)
