"""Step 15 continued -- Admin Inspector, RLS-as-student, session isolation.

Validation-only, no application code touched. Reuses the qa-step15 user
created by step15_qa_speaking_e2e.py (now granted the admin staff role for
this check) and drives the real running QA-mode backend + a second,
minimal (single-turn) speaking session for isolation.

Usage:
    cd backend
    ENVIRONMENT=qa python -u scripts/step15b_qa_admin_rls_isolation.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "qa")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.core.config import settings
from app.core.supabase import get_supabase, get_auth_client

BACKEND_URL = os.environ.get("QA_VERIFY_BACKEND_URL", "http://127.0.0.1:8010")
EMAIL = "qa-step15@example.com"
PASSWORD = "QaStep15!2026x"
SCENARIO_ID = 3
SUBMISSION_ID = 15
SESSION_A_ID = 11

assert "wpowzyyzhrxdqujrvxdq" in settings.SUPABASE_URL
assert "lgwaiwasnjjohqkeizdz" not in settings.SUPABASE_URL

service = get_supabase()
anon = get_auth_client()


def log(msg):
    print(msg, flush=True)


def main():
    auth_resp = anon.auth.sign_in_with_password({"email": EMAIL, "password": PASSWORD})
    access_token = auth_resp.session.access_token
    headers = {"Authorization": f"Bearer {access_token}"}
    client = httpx.Client(base_url=BACKEND_URL, headers=headers, timeout=60.0)

    log("=== STEP 12: Admin Inspector ===")
    r = client.get("/admin/speaking-evidence/sessions", params={"pipeline": "legacy", "limit": 5})
    log(f"[sessions] status={r.status_code}")
    log(json.dumps(r.json(), indent=2)[:1500])

    r = client.get(f"/admin/speaking-evidence/legacy/{SUBMISSION_ID}/evidence")
    log(f"[evidence] status={r.status_code}")
    body = r.json()
    log(f"session.pipeline={body.get('session', {}).get('pipeline')}")
    log(f"session.session_usage_id linkage (from code, not in response body directly)")
    log(f"scenario.title={body.get('scenario', {}).get('title') if body.get('scenario') else None}")
    log(f"transcript turns={len(body.get('transcript', []))}")
    log(f"reconstruction_note={body.get('session', {}).get('reconstruction_note')}")
    ev = body.get("evidence", {})
    log(f"evidence keys={list(ev.keys())}")
    unified = body.get("unified", {})
    log(f"unified keys={list(unified.keys())}")
    log(f"integrity_violations={body.get('integrity_violations')}")
    Path("qa-artifacts/step15_admin_evidence.json").write_text(json.dumps(body, indent=2))

    log("\n=== STEP 15: RLS as normal (non-admin-scoped-table) student JWT ===")
    rls_url = f"{settings.SUPABASE_URL}/rest/v1/session_semantic_state?session_usage_id=eq.{SESSION_A_ID}&select=session_usage_id"
    r2 = httpx.get(rls_url, headers={
        "apikey": settings.SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {access_token}",
    })
    log(f"[student JWT select session_semantic_state] status={r2.status_code} body={r2.text[:300]}")

    log("\n=== STEP 16: session isolation (lightweight second session) ===")
    r = client.post("/sessions/check-and-increment")
    log(f"[check-and-increment B] status={r.status_code} body={r.text[:300]}")
    r.raise_for_status()
    session_b_id = r.json()["session_id"]
    log(f"session_usage.id (B) = {session_b_id}")

    r = client.post("/speaking/chat", json={
        "session_id": session_b_id,
        "scenario_id": SCENARIO_ID,
        "message": "Hi, I'm the nurse. How are you feeling today?",
        "history": [],
    })
    log(f"[speaking/chat B] status={r.status_code}")
    r.raise_for_status()

    Path("qa-artifacts/step15_session_b.json").write_text(json.dumps({"session_b_id": session_b_id}))
    log("wrote qa-artifacts/step15_session_b.json")


if __name__ == "__main__":
    main()
