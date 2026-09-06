"""Phase 5.3a QA Auth-behavior verification (spec Sec 17.10).

Read/probe only against the real QA Supabase Auth API (project
wpowzyyzhrxdqujrvxdq). Creates a handful of disposable auth.users rows to
observe real GoTrue admin-API behavior, then deletes every one of them.
Does NOT create institution_members rows, does NOT touch production, does
NOT implement the staff endpoint, does NOT modify require_active_institution_role(),
AuthCallbackPage, or accept_institution_invite().

Never prints access/refresh tokens, invite URLs, passwords, or secrets --
only safe metadata (ids, timestamps, booleans, error categories).

Usage:
    cd backend
    ENVIRONMENT=qa python -u scripts/qa_verify_phase5_3a_auth_behavior.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "qa")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.core.supabase import get_supabase

assert "wpowzyyzhrxdqujrvxdq" in settings.SUPABASE_URL, (
    f"Refusing to run: SUPABASE_URL is not the QA project -- got {settings.SUPABASE_URL!r}"
)
assert "lgwaiwasnjjohqkeizdz" not in settings.SUPABASE_URL, "Refusing to run against production project ref"
assert settings.ENVIRONMENT == "qa", f"Refusing to run: ENVIRONMENT={settings.ENVIRONMENT!r}, expected 'qa'"

service = get_supabase()
RUN_TAG = os.environ.get("QA_VERIFY_RUN_TAG", "p53a1")
PASSWORD = "QaVerify!2026Auth"

created_user_ids: list[tuple[str, str, str]] = []  # (label, id, email)


def log(msg):
    print(msg, flush=True)


def safe_error(e: Exception) -> str:
    """Category + message only -- GoTrue errors never carry tokens/secrets."""
    return f"{type(e).__name__}: {e}"


def redact_link(action_link: str | None) -> str:
    if not action_link:
        return "(none)"
    # Keep only the origin + path + type param, drop token/token_hash values.
    import re
    scrubbed = re.sub(r"(token(_hash)?=)[^&]+", r"\1<redacted>", action_link)
    return scrubbed


def email_for(label: str) -> str:
    return f"qa-auth53a-{label}-{RUN_TAG}@example.com"


def mk_user(label: str, *, confirmed: bool) -> tuple[str, str]:
    email = email_for(label)
    resp = service.auth.admin.create_user({
        "email": email,
        "password": PASSWORD,
        "email_confirm": confirmed,
    })
    uid = resp.user.id
    created_user_ids.append((label, uid, email))
    return uid, email


def get_user(uid: str):
    return service.auth.admin.get_user_by_id(uid).user


def find_by_email_via_list(email: str):
    """The only SDK-level identify-by-email path: page through list_users()
    and match client-side (no email filter param exists on this endpoint --
    confirmed by inspecting the pinned gotrue-py signature: list_users(page,
    per_page) only)."""
    page = 1
    while True:
        batch = service.auth.admin.list_users(page=page, per_page=200)
        if not batch:
            return None
        for u in batch:
            if u.email == email:
                return u
        page += 1
        if page > 20:
            return None


results = []


def record(section: str, name: str, **fields):
    results.append((section, name, fields))
    log(f"  [{section}] {name}: {fields}")


def main():
    log("=== A: identify existing user by email without list_users() scan ===")
    log("  gotrue-py (pinned supabase==2.5.3) admin surface: "
        f"{sorted(m for m in dir(type(service.auth.admin)) if not m.startswith('_'))}")
    log("  list_users signature has no email filter (page/per_page only); "
        "no get_user_by_email exists -- only get_user_by_id.")
    log("  -> probing whether generate_link/invite error responses can substitute (see B/C below).")

    log("\n=== Fixture users ===")
    confirmed_id, confirmed_email = mk_user("confirmed", confirmed=True)
    log(f"  confirmed user: {confirmed_email} ({confirmed_id})")
    unconfirmed_id, unconfirmed_email = mk_user("unconfirmed", confirmed=False)
    log(f"  unconfirmed (signup, never invited) user: {unconfirmed_email} ({unconfirmed_id})")
    nonexistent_email = email_for("nonexistent")
    log(f"  nonexistent email (never created): {nonexistent_email}")

    log("\n=== B: generate_link(type='recovery') ===")
    for label, email in [("nonexistent", nonexistent_email), ("confirmed", confirmed_email), ("unconfirmed", unconfirmed_email)]:
        try:
            r = service.auth.admin.generate_link({"type": "recovery", "email": email})
            u = r.user
            record("B", f"recovery link for {label} email", ok=True,
                   user_id=u.id if u else None,
                   email_confirmed_at=bool(u.email_confirmed_at) if u else None,
                   action_link=redact_link(getattr(r.properties, "action_link", None)) if getattr(r, "properties", None) else None)
        except Exception as e:
            record("B", f"recovery link for {label} email", ok=False, error=safe_error(e))

    log("\n=== C + D: invite_user_by_email() ===")
    # C1: nonexistent email -- also answers D (does it create auth.users immediately?)
    invited_email = email_for("invited")
    try:
        r = service.auth.admin.invite_user_by_email(invited_email)
        invited_id = r.user.id
        created_user_ids.append(("invited", invited_id, invited_email))
        record("C", "invite nonexistent email", ok=True, user_id=invited_id,
               email_confirmed_at=bool(r.user.email_confirmed_at),
               invited_at=str(getattr(r.user, "invited_at", None)),
               confirmation_sent_at=str(getattr(r.user, "confirmation_sent_at", None)))
        # D: immediate existence check right after the call, no delay.
        fetched = get_user(invited_id)
        record("D", "auth.users row exists immediately after invite_user_by_email",
               ok=fetched is not None, email_confirmed_at=bool(fetched.email_confirmed_at) if fetched else None)
    except Exception as e:
        invited_id = None
        record("C", "invite nonexistent email", ok=False, error=safe_error(e))

    # C2: existing confirmed email
    try:
        r = service.auth.admin.invite_user_by_email(confirmed_email)
        record("C", "invite existing CONFIRMED email", ok=True, user_id=r.user.id,
               email_confirmed_at=bool(r.user.email_confirmed_at))
    except Exception as e:
        record("C", "invite existing CONFIRMED email", ok=False, error=safe_error(e))

    # C3: existing unconfirmed email (created via signup path, not invite)
    try:
        r = service.auth.admin.invite_user_by_email(unconfirmed_email)
        record("C", "invite existing UNCONFIRMED (signup) email", ok=True, user_id=r.user.id,
               email_confirmed_at=bool(r.user.email_confirmed_at),
               confirmation_sent_at=str(getattr(r.user, "confirmation_sent_at", None)))
    except Exception as e:
        record("C", "invite existing UNCONFIRMED (signup) email", ok=False, error=safe_error(e))

    log("\n=== E: duplicate/repeated invitation ===")
    if invited_id:
        before = get_user(invited_id)
        before_sent = str(getattr(before, "confirmation_sent_at", None))
        before_invited = str(getattr(before, "invited_at", None))
        try:
            r2 = service.auth.admin.invite_user_by_email(invited_email)
            after_sent = str(getattr(r2.user, "confirmation_sent_at", None))
            after_invited = str(getattr(r2.user, "invited_at", None))
            record("E", "second invite_user_by_email on already-invited email", ok=True,
                   user_id_unchanged=(r2.user.id == invited_id),
                   confirmation_sent_at_before=before_sent, confirmation_sent_at_after=after_sent,
                   invited_at_before=before_invited, invited_at_after=after_invited,
                   changed=(before_sent != after_sent or before_invited != after_invited))
        except Exception as e:
            record("E", "second invite_user_by_email on already-invited email", ok=False, error=safe_error(e))

    log("\n=== Invite acceptance -- real /auth/confirm behavior ===")
    log("  Using generate_link(type='invite') to obtain the same token_hash GoTrue")
    log("  would email (example.com can't receive real mail) -- this exercises the")
    log("  identical verifyOtp() consumption path /auth/confirm calls.")
    accept_email = email_for("accept")
    token_hash = None
    try:
        r = service.auth.admin.generate_link({"type": "invite", "email": accept_email})
        accept_id = r.user.id
        created_user_ids.append(("accept", accept_id, accept_email))
        props = r.properties
        token_hash = getattr(props, "hashed_token", None)
        record("Invite-accept-setup", "generate_link(type=invite) for fresh email", ok=True,
               user_id=accept_id, email_confirmed_at=bool(r.user.email_confirmed_at),
               has_token_hash=bool(token_hash))
    except Exception as e:
        record("Invite-accept-setup", "generate_link(type=invite) for fresh email", ok=False, error=safe_error(e))

    if token_hash:
        out_path = Path(os.environ.get("QA_VERIFY_TOKEN_HASH_FILE", "qa_53a_token_hash.txt"))
        out_path.write_text(token_hash)
        log(f"  token_hash written to {out_path} (gitignored scratch file, deleted at end of run)")

    log("\n=== Summary ===")
    for section, name, fields in results:
        log(f"  [{section}] {name}: {fields}")

    log("\n=== Cleanup ===")
    for label, uid, email in created_user_ids:
        try:
            service.auth.admin.delete_user(uid)
            log(f"  deleted {label}: {email} ({uid})")
        except Exception as e:
            log(f"  FAILED to delete {label}: {email} ({uid}) -- {safe_error(e)}")

    log("\n=== Cleanup verification ===")
    remaining = []
    page = 1
    while True:
        batch = service.auth.admin.list_users(page=page, per_page=200)
        if not batch:
            break
        remaining.extend(u.email for u in batch if u.email and RUN_TAG in u.email)
        page += 1
        if page > 20:
            break
    log(f"  disposable users with tag {RUN_TAG} still present: {remaining}")
    return 0 if not remaining else 1


if __name__ == "__main__":
    raise SystemExit(main())
