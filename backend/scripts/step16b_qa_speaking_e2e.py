"""Step 16B -- real QA speaking chat -> score validation for the raised
Gemini generation-budget constants (SPEAKING_SCORING_MAX_TOKENS_PREMIUM/FREE,
SEMANTIC_MAX_TOKENS). Adapted from scripts/step15_qa_speaking_e2e.py to take
the QA test account via env vars so it can be pointed at both a free-plan and
a premium-plan (pro/elite) user in the same run, exercising
speaking_scoring_free and speaking_scoring_premium respectively.

Usage:
    cd backend
    ENVIRONMENT=qa QA_EMAIL=test@gmail.com QA_PASSWORD=Test@123 \
        python -u scripts/step16b_qa_speaking_e2e.py premium
    ENVIRONMENT=qa python -u scripts/step16b_qa_speaking_e2e.py free
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
TIER = sys.argv[1] if len(sys.argv) > 1 else "free"
SCENARIO_ID = 3

if TIER == "premium":
    EMAIL = os.environ.get("QA_EMAIL", "test@gmail.com")
    PASSWORD = os.environ.get("QA_PASSWORD", "Test@123")
else:
    EMAIL = "qa-step15@example.com"
    PASSWORD = "QaStep15!2026x"

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
    log(f"=== tier={TIER} email={EMAIL} ===")
    user_id, email = get_or_create_user()

    auth_resp = anon.auth.sign_in_with_password({"email": email, "password": PASSWORD})
    access_token = auth_resp.session.access_token
    log(f"signed in. user_id={user_id}")

    headers = {"Authorization": f"Bearer {access_token}"}
    client = httpx.Client(base_url=BACKEND_URL, headers=headers, timeout=90.0)

    r = client.post("/sessions/check-and-increment")
    log(f"[check-and-increment] status={r.status_code} body={r.text[:500]}")
    r.raise_for_status()
    session_data = r.json()
    session_id = session_data.get("session_id")
    log(f"session_usage.id = {session_id}")
    assert session_id is not None, "no session id returned"

    result = {"tier": TIER, "user_id": user_id, "email": email, "session_id": session_id, "turns": []}

    history = []
    turns = [
        "Hello, I'm the nurse. Can you tell me how you're feeling today?",
        "I understand. Have you been checking your blood sugar levels regularly?",
        "Let's talk about your insulin injection routine, and why you're worried about it.",
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

    t0 = time.monotonic()
    r = client.post("/speaking/score", json={
        "session_id": session_id,
        "scenario_id": SCENARIO_ID,
        "history": history,
        "duration_seconds": 60,
    })
    elapsed_ms = round((time.monotonic() - t0) * 1000)
    log(f"[speaking/score] status={r.status_code} elapsed_ms={elapsed_ms} body={r.text[:1200]}")
    r.raise_for_status()
    result["score_response"] = r.json()
    result["elapsed_ms"] = elapsed_ms

    out_path = Path(f"qa-artifacts/step16b_{TIER}_result.json")
    out_path.write_text(json.dumps(result, indent=2))
    log(f"wrote {out_path}")


if __name__ == "__main__":
    main()
