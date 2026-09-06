"""Phase 5.3a QA Auth-behavior verification, part 2.

invite_user_by_email() turned out to hard-fail (500 "Error sending invite
email") on every call in QA -- no working email provider configured there.
This supplements the primary script by using generate_link(type="invite"),
which creates the user without attempting to send mail, as a substitute to
observe: (C) invite-type generate_link on an existing confirmed user, and
(E) repeated invite-type generate_link on the same email (duplicate/pending
invite behavior). Same QA-only guardrails and cleanup as the primary script.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "qa")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.core.supabase import get_supabase

assert "wpowzyyzhrxdqujrvxdq" in settings.SUPABASE_URL
assert "lgwaiwasnjjohqkeizdz" not in settings.SUPABASE_URL
assert settings.ENVIRONMENT == "qa"

service = get_supabase()
RUN_TAG = "p53a2"
created = []


def log(msg):
    print(msg, flush=True)


def mk_confirmed(label):
    email = f"qa-auth53a2-{label}-{RUN_TAG}@example.com"
    r = service.auth.admin.create_user({"email": email, "password": "QaVerify!2026Auth", "email_confirm": True})
    created.append(r.user.id)
    return email, r.user.id


def main():
    log("=== C (generate_link substitute): invite-type link for existing CONFIRMED user ===")
    confirmed_email, confirmed_id = mk_confirmed("confirmed")
    try:
        r = service.auth.admin.generate_link({"type": "invite", "email": confirmed_email})
        log(f"  ok=True user_id={r.user.id} email_confirmed_at={bool(r.user.email_confirmed_at)}")
    except Exception as e:
        log(f"  ok=False error={type(e).__name__}: {e}")

    log("\n=== E (generate_link substitute): repeated invite-type link, same never-before-seen email ===")
    dup_email = f"qa-auth53a2-dup-{RUN_TAG}@example.com"
    try:
        r1 = service.auth.admin.generate_link({"type": "invite", "email": dup_email})
        uid = r1.user.id
        created.append(uid)
        log(f"  1st call: ok=True user_id={uid} invited_at={r1.user.invited_at} confirmation_sent_at={r1.user.confirmation_sent_at}")
    except Exception as e:
        log(f"  1st call: ok=False error={type(e).__name__}: {e}")
        uid = None

    try:
        r2 = service.auth.admin.generate_link({"type": "invite", "email": dup_email})
        log(f"  2nd call: ok=True user_id={r2.user.id} same_user_id={r2.user.id == uid} "
            f"invited_at={r2.user.invited_at} confirmation_sent_at={r2.user.confirmation_sent_at}")
    except Exception as e:
        log(f"  2nd call: ok=False error={type(e).__name__}: {e}")

    log("\n=== Cleanup ===")
    for uid in created:
        try:
            service.auth.admin.delete_user(uid)
            log(f"  deleted {uid}")
        except Exception as e:
            log(f"  FAILED to delete {uid}: {e}")

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
    log(f"  remaining tagged users: {remaining}")
    return 0 if not remaining else 1


if __name__ == "__main__":
    raise SystemExit(main())
