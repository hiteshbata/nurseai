"""Tests for backend/app/routers/admin_speaking_evidence.py (Step 6: Admin
Speaking Evidence Inspector).

Same style as test_rbac.py/test_admin_cron_auth.py: route functions called
directly with a mocked get_supabase, no FastAPI TestClient, no live DB.
"""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402
import app.services.ai_scoring as ai_scoring  # noqa: E402
from app.routers import admin as admin_module  # noqa: E402
from app.routers import admin_speaking_evidence as evidence_module  # noqa: E402
from app.routers.auth import UserInfo  # noqa: E402
from app.services.speaking_evidence import build_speaking_evidence  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


async def _no_semantic_call(*args, **kwargs):
    """get_speaking_evidence is now async (Step 7 -- it runs the semantic
    enrichment pass). These route-wiring/reconstruction tests care about
    session lookup and evidence serialization, not semantic-classifier
    correctness (see test_semantic_evidence.py for that) -- stub _call_ai so
    no real network/DB call happens, matching provider_failure's existing
    documented contract (semantic layer stays a no-op, conservative default)."""
    return {"provider_failure": True}


# ── Fake Supabase client ────────────────────────────────────────────────
# Mirrors test_content_studio.py's _FakeQuery/_FakeSupabase shape: a
# table/select/eq/order/limit/execute chain over an in-memory row dict.

class _FakeQuery:
    def __init__(self, rows):
        self._rows = list(rows)

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._rows = [r for r in self._rows if r.get(col) == val]
        return self

    def order(self, col, desc=False):
        self._rows = sorted(self._rows, key=lambda r: r.get(col) or "", reverse=desc)
        return self

    def limit(self, n):
        self._rows = self._rows[:n]
        return self

    def execute(self):
        return type("Result", (), {"data": self._rows})()


class _FakeSupabase:
    def __init__(self, tables):
        self._tables = tables

    def table(self, name):
        return _FakeQuery(self._tables.get(name, []))


_INTERLOCUTOR_CARD = {
    "mood": "anxious",
    "emotional_triggers": ["surgery"],
    "questions_to_ask": ["operation"],
}

_SCENARIO_ROW = {"id": 1, "title": "Pre-op anxiety", "setting": "Ward", "interlocutor_card": _INTERLOCUTOR_CARD}

_HISTORY = [
    {"role": "patient", "content": "I'm really worried about the operation."},
    {"role": "nurse", "content": "I can understand why you're worried."},
]


def _tables(**overrides):
    base = {"scenarios": [_SCENARIO_ROW], "session_transcripts": [], "realtime_session_metrics": [], "submissions": []}
    base.update(overrides)
    return base


class RequireAdminGateTests(unittest.TestCase):
    """Item 1: non-admin cannot access; reuses admin.py's existing RBAC
    dependency rather than inventing a second auth mechanism."""

    def test_reuses_admin_modules_require_admin(self):
        self.assertIs(evidence_module.require_admin, admin_module.require_admin)

    def test_non_admin_rejected(self):
        user = UserInfo(id="u1", email="u1@example.com", name="U1")
        supabase = _FakeSupabase({"user_roles": [{"user_id": "u1", "role": "support"}]})
        with patch.object(admin_module, "get_supabase", return_value=supabase):
            with self.assertRaises(HTTPException) as ctx:
                evidence_module.require_admin(current_user=user)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_admin_passes(self):
        user = UserInfo(id="u1", email="u1@example.com", name="U1")
        supabase = _FakeSupabase({"user_roles": [{"user_id": "u1", "role": "admin"}]})
        with patch.object(admin_module, "get_supabase", return_value=supabase):
            result = evidence_module.require_admin(current_user=user)
        self.assertEqual(result.id, "u1")


class LegacyHistoryReconstructionTests(unittest.TestCase):
    def test_well_formed_transcript_splits_cleanly(self):
        answer = "Nurse: Hello, how are you?\nPatient: I'm worried about surgery.\nNurse: I understand."
        history, note = evidence_module._reconstruct_legacy_history(answer)
        self.assertIsNone(note)
        self.assertEqual(history, [
            {"role": "nurse", "content": "Hello, how are you?"},
            {"role": "patient", "content": "I'm worried about surgery."},
            {"role": "nurse", "content": "I understand."},
        ])

    def test_empty_answer_returns_note_not_crash(self):
        history, note = evidence_module._reconstruct_legacy_history(None)
        self.assertEqual(history, [])
        self.assertIsNotNone(note)

    def test_malformed_answer_returns_note_not_fabricated_turns(self):
        history, note = evidence_module._reconstruct_legacy_history("just some free text, no role prefixes")
        self.assertEqual(history, [])
        self.assertIsNotNone(note)


class RealtimeSessionEvidenceTests(unittest.TestCase):
    def test_valid_realtime_session_reconstructs_and_matches_direct_call(self):
        tables = _tables(session_transcripts=[
            {"session_usage_id": 42, "user_id": "u1", "scenario_id": 1,
             "transcript": [{"role": "patient", "text": "I'm really worried about the operation."}],
             "created_at": "2026-08-01T00:00:00Z"},
            {"session_usage_id": 42, "user_id": "u1", "scenario_id": 1,
             "transcript": [{"role": "nurse", "text": "I can understand why you're worried."}],
             "created_at": "2026-08-01T00:00:05Z"},
        ], realtime_session_metrics=[{"session_usage_id": 42, "duration_seconds": 30.0}])
        supabase = _FakeSupabase(tables)
        with patch.object(evidence_module, "get_supabase", return_value=supabase), \
             patch.object(admin_module, "get_supabase", return_value=_FakeSupabase({"user_roles": [{"user_id": "a1", "role": "admin"}]})), \
             patch.object(ai_scoring, "_call_ai", _no_semantic_call):
            admin_user = evidence_module.require_admin(current_user=UserInfo(id="a1", email="a@x.com", name="A"))
            result = _run(evidence_module.get_speaking_evidence(
                pipeline=evidence_module.Pipeline.realtime, session_id=42, current_user=admin_user,
            ))

        self.assertEqual(result["session"]["pipeline"], "realtime")
        self.assertEqual(result["session"]["user_id"], "u1")
        self.assertEqual(result["session"]["duration_seconds"], 30.0)
        self.assertEqual(result["transcript"], _HISTORY)
        self.assertEqual(result["scenario"]["title"], "Pre-op anxiety")

        expected = build_speaking_evidence(_INTERLOCUTOR_CARD, _HISTORY).model_dump()
        self.assertEqual(result["evidence"], expected)

    def test_missing_realtime_session_is_404(self):
        supabase = _FakeSupabase(_tables())
        with patch.object(evidence_module, "get_supabase", return_value=supabase):
            with self.assertRaises(HTTPException) as ctx:
                _run(evidence_module.get_speaking_evidence(
                    pipeline=evidence_module.Pipeline.realtime, session_id=999, current_user=None,
                ))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_session_isolation_does_not_leak_other_sessions_rows(self):
        tables = _tables(session_transcripts=[
            {"session_usage_id": 1, "user_id": "userA", "scenario_id": 1,
             "transcript": [{"role": "nurse", "text": "session one"}], "created_at": "t1"},
            {"session_usage_id": 2, "user_id": "userB", "scenario_id": 1,
             "transcript": [{"role": "nurse", "text": "session two"}], "created_at": "t2"},
        ])
        supabase = _FakeSupabase(tables)
        with patch.object(evidence_module, "get_supabase", return_value=supabase), \
             patch.object(ai_scoring, "_call_ai", _no_semantic_call):
            result = _run(evidence_module.get_speaking_evidence(
                pipeline=evidence_module.Pipeline.realtime, session_id=1, current_user=None,
            ))
        self.assertEqual(result["session"]["user_id"], "userA")
        self.assertEqual(result["transcript"], [{"role": "nurse", "content": "session one"}])


class LegacySessionEvidenceTests(unittest.TestCase):
    def test_valid_legacy_session_reconstructs_and_matches_direct_call(self):
        tables = _tables(submissions=[
            {"id": 7, "user_id": "u1", "scenario_id": 1, "module": "speaking",
             "answer": "Patient: I'm really worried about the operation.\nNurse: I can understand why you're worried.",
             "created_at": "2026-08-01T00:00:00Z"},
        ])
        supabase = _FakeSupabase(tables)
        with patch.object(evidence_module, "get_supabase", return_value=supabase), \
             patch.object(ai_scoring, "_call_ai", _no_semantic_call):
            result = _run(evidence_module.get_speaking_evidence(
                pipeline=evidence_module.Pipeline.legacy, session_id=7, current_user=None,
            ))

        self.assertEqual(result["session"]["pipeline"], "legacy")
        self.assertIsNone(result["session"]["reconstruction_note"])
        self.assertEqual(result["transcript"], _HISTORY)
        expected = build_speaking_evidence(_INTERLOCUTOR_CARD, _HISTORY).model_dump()
        self.assertEqual(result["evidence"], expected)

    def test_missing_legacy_session_is_404(self):
        supabase = _FakeSupabase(_tables())
        with patch.object(evidence_module, "get_supabase", return_value=supabase):
            with self.assertRaises(HTTPException) as ctx:
                _run(evidence_module.get_speaking_evidence(
                    pipeline=evidence_module.Pipeline.legacy, session_id=999, current_user=None,
                ))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_minimal_legacy_session_no_answer_does_not_crash(self):
        tables = _tables(submissions=[
            {"id": 8, "user_id": "u1", "scenario_id": None,
             "module": "speaking", "answer": None, "created_at": "2026-08-01T00:00:00Z"},
        ])
        supabase = _FakeSupabase(tables)
        with patch.object(evidence_module, "get_supabase", return_value=supabase):
            result = _run(evidence_module.get_speaking_evidence(
                pipeline=evidence_module.Pipeline.legacy, session_id=8, current_user=None,
            ))
        self.assertEqual(result["transcript"], [])
        self.assertIsNone(result["scenario"])
        self.assertIsNotNone(result["session"]["reconstruction_note"])
        self.assertEqual(result["evidence"]["interaction_metrics"]["turn_counts"]["total"], 0)


class EvidenceSerializationTests(unittest.TestCase):
    def test_speaking_evidence_serializes_to_expected_top_level_keys(self):
        evidence = build_speaking_evidence(_INTERLOCUTOR_CARD, _HISTORY)
        dumped = evidence.model_dump()
        self.assertEqual(set(dumped.keys()), {
            "candidate_events", "patient_events", "concern_outcomes",
            "state_transitions", "jargon_evidence", "interaction_metrics",
            "hidden_info_outcomes",
        })
        # Round-trips through model_dump twice identically (pure/stateless).
        self.assertEqual(dumped, evidence.model_dump())


class SessionListTests(unittest.TestCase):
    def test_list_splits_by_pipeline_and_dedupes_realtime_reconnects(self):
        tables = _tables(
            session_transcripts=[
                {"session_usage_id": 1, "user_id": "u1", "scenario_id": 1, "created_at": "t2"},
                {"session_usage_id": 1, "user_id": "u1", "scenario_id": 1, "created_at": "t1"},
                {"session_usage_id": 2, "user_id": "u2", "scenario_id": 1, "created_at": "t3"},
            ],
            submissions=[{"id": 5, "user_id": "u1", "scenario_id": 1, "created_at": "t1", "module": "speaking"}],
        )
        supabase = _FakeSupabase(tables)
        with patch.object(evidence_module, "get_supabase", return_value=supabase):
            result = evidence_module.list_speaking_sessions(
                pipeline=None, user_id=None, scenario_id=None, limit=20, current_user=None,
            )
        self.assertEqual(len(result["realtime"]), 2)
        self.assertEqual({r["id"] for r in result["realtime"]}, {1, 2})
        self.assertEqual(len(result["legacy"]), 1)
        self.assertEqual(result["legacy"][0]["id"], 5)


if __name__ == "__main__":
    unittest.main()
