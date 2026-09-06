"""Step 15 -- real QA end-to-end validation: legacy Speaking -> submission ->
session_semantic_state -> Admin Speaking Evidence Inspector.

Validation-only. No application code touched. Follows the same idempotent
disposable-user pattern as scripts/qa_verify_phase4_institution_admin.py:
create/reuse one fixed-label QA user via the service-role admin client,
sign in with anon.sign_in_with_password to get a real JWT, then drive the
actual running QA-mode backend through its real HTTP endpoints.

Usage:
    cd backend
    ENVIRONMENT=qa python -u scripts/step15_qa_speaking_e2e.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "qa")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.core.config import settings
from app.core.supabase import get_supabase, get_auth_client

BACKEND_URL = os.environ.get("QA_VERIFY_BACKEND_URL", "http://127.0.0.1:8010")
RUN_TAG = "step15"
EMAIL = f"qa-{RUN_TAG}@example.com"
PASSWORD = "QaStep15!2026x"
SCENARIO_ID = 3

assert "wpowzyyzhrxdqujrvxdq" in settings.SUPABASE_URL, (
    f"Refusing to run: SUPABASE_URL is not the QA project -- got {settings.SUPABASE_URL!r}"
)
assert "lgwaiwasnjjohqkeizdz" not in settings.SUPABASE_URL, "Refusing to run against production project ref"

service = get_supabase()
anon = get_auth_client()


def log(msg):
    print(msg, flush=True)


def get_or_create_user() -> tuple[str, str]:
    existing = service.auth.admin.list_users()
    for u in existing:
        if u.email == EMAIL:
            log(f"reused QA user: {EMAIL} ({u.id})")
            return u.id, EMAIL
    resp = service.auth.admin.create_user({"email": EMAIL, "password": PASSWORD, "email_confirm": True})
    log(f"created QA user: {EMAIL} ({resp.user.id})")
    return resp.user.id, EMAIL


def main():
    user_id, email = get_or_create_user()

    auth_resp = anon.auth.sign_in_with_password({"email": email, "password": PASSWORD})
    access_token = auth_resp.session.access_token
    log(f"signed in. user_id={user_id}")

    headers = {"Authorization": f"Bearer {access_token}"}
    client = httpx.Client(base_url=BACKEND_URL, headers=headers, timeout=60.0)

    # Step 2: real session creation via the actual endpoint (no body needed)
    r = client.post("/sessions/check-and-increment")
    log(f"[check-and-increment] status={r.status_code} body={r.text[:500]}")
    r.raise_for_status()
    session_data = r.json()
    session_id = session_data.get("session_id")
    log(f"session_usage.id = {session_id}")
    assert session_id is not None, "no session id returned"

    result = {"user_id": user_id, "email": email, "session_id": session_id, "turns": []}

    # Step 4: real legacy speaking chat turns.
    # PatientChatRequest: `message` is the new nurse turn, `history` is the
    # prior turns only (chat_with_patient appends the current turn itself).
    history = []
    turns = [
        "Hello, I'm the nurse. Can you tell me how you're feeling today?",
        "I understand. Have you been checking your blood sugar levels regularly?",
        "Let's talk about your insulin injection routine.",
    ]
    for msg in turns:
        r = client.post("/speaking/chat", json={
            "session_id": session_id,
            "scenario_id": SCENARIO_ID,
            "message": msg,
            "history": history,
        })
        log(f"[speaking/chat] status={r.status_code}")
        r.raise_for_status()
        data = r.json()
        history = data["updated_history"]
        patient_reply = data.get("patient_reply", "")
        result["turns"].append({"nurse": msg, "patient": patient_reply[:200]})
        time.sleep(1)

    result["history"] = history

    # Step 8: real score call
    r = client.post("/speaking/score", json={
        "session_id": session_id,
        "scenario_id": SCENARIO_ID,
        "history": history,
        "duration_seconds": 60,
    })
    log(f"[speaking/score] status={r.status_code} body={r.text[:800]}")
    r.raise_for_status()
    result["score_response"] = r.json()

    Path("qa-artifacts/step15_result.json").write_text(json.dumps(result, indent=2))
    log("wrote qa-artifacts/step15_result.json")


if __name__ == "__main__":
    main()
