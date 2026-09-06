"""Step 14: submissions.session_usage_id link.

Covers the migration (schema shape + RLS invariant), the speaking submission
path that populates the new column, and the Admin Speaking Evidence
Inspector's legacy-pipeline use of it -- see docs/... (Step 14 spec) for the
full design. Same style as test_admin_speaking_evidence.py /
test_speaking_session_quota.py / test_institution_migration_security.py:
route/service functions called directly against fake Supabase clients or
migration-text golden checks, no live DB, no FastAPI TestClient.
"""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402

import app.routers.speaking as speaking_module  # noqa: E402
from app.routers import admin_speaking_evidence as evidence_module  # noqa: E402
from app.routers.auth import UserInfo  # noqa: E402
from app.routers.speaking import ChatMessage, SpeakingSubmitRequest  # noqa: E402
from app.services.speaking_evidence import build_speaking_evidence  # noqa: E402

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "supabase" / "migrations" / "20260828010000_link_submissions_to_session_usage.sql"
)
SEMANTIC_STATE_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "supabase" / "migrations" / "20260828000000_session_semantic_state.sql"
)


def _run(coro):
    return asyncio.run(coro)


# ── Schema / migration (items 1-5, 14) ────────────────────────────────────

class MigrationSchemaTests(unittest.TestCase):
    def _sql(self) -> str:
        return MIGRATION_PATH.read_text(encoding="utf-8")

    def test_migration_file_exists(self):
        self.assertTrue(MIGRATION_PATH.exists(), f"expected migration at {MIGRATION_PATH}")

    def test_column_added_with_correct_type(self):
        sql = self._sql()
        self.assertIn("ADD COLUMN IF NOT EXISTS session_usage_id BIGINT", sql)

    def test_column_is_nullable_not_required(self):
        # No NOT NULL anywhere near the new column -- historical/non-speaking
        # rows must be able to leave it unset.
        sql = self._sql()
        self.assertNotIn("session_usage_id BIGINT NOT NULL", sql)

    def test_foreign_key_references_session_usage(self):
        sql = self._sql()
        self.assertIn("REFERENCES public.session_usage(id)", sql)

    def test_delete_behavior_is_cascade(self):
        sql = self._sql()
        self.assertIn("ON DELETE CASCADE", sql)

    def test_index_added_on_session_usage_id(self):
        sql = self._sql()
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_submissions_session_usage_id", sql)
        self.assertIn("ON public.submissions (session_usage_id)", sql)

    def test_migration_is_purely_additive(self):
        sql = self._sql().upper()
        for forbidden in ("DROP COLUMN", "ALTER COLUMN", "DELETE FROM", "TRUNCATE", "UPDATE PUBLIC.SUBMISSIONS"):
            self.assertNotIn(forbidden, sql)


class SemanticStateRemainsServiceRoleOnlyTests(unittest.TestCase):
    """Item 13: student cannot directly read session_semantic_state. This
    table's own migration (Step 13, untouched by Step 14) enables RLS with
    zero policies -- locking that in here so a future edit to either
    migration can't quietly open a student-readable path onto semantic
    state via the new submissions link."""

    def test_no_policy_grants_student_access(self):
        sql = SEMANTIC_STATE_MIGRATION_PATH.read_text(encoding="utf-8").upper()
        self.assertIn("ENABLE ROW LEVEL SECURITY", sql)
        self.assertNotIn("CREATE POLICY", sql)
        self.assertNotIn("TO AUTHENTICATED", sql)


# ── Speaking submission creation (items 6-7) ──────────────────────────────

class _FakeResult:
    def __init__(self, data=None):
        self.data = data if data is not None else []


class _FakeTable:
    def __init__(self, rows_by_table, captured_inserts):
        self._rows_by_table = rows_by_table
        self._captured = captured_inserts
        self._name = None
        self._op = None
        self._payload = None
        self._filters = []

    def table(self, name):
        self._name = name
        self._op = None
        self._filters = []
        return self

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def execute(self):
        if self._op == "insert":
            self._captured.setdefault(self._name, []).append(dict(self._payload))
            return _FakeResult([dict(self._payload, id=1)])
        rows = self._rows_by_table.get(self._name, [])
        matched = [r for r in rows if all(r.get(c) == v for c, v in self._filters)]
        return _FakeResult(matched)


def _make_request(session_id):
    return SpeakingSubmitRequest(
        scenario_id=1,
        history=[ChatMessage(role="nurse", content="Hello"), ChatMessage(role="patient", content="Hi")],
        duration_seconds=60,
        session_id=session_id,
    )


_SCENARIO_ROW = {"id": 1, "title": "T", "nurse_card": {}, "scoring_criteria": {}}
_PROFILE_ROW = {"plan": "free", "plan_expires_at": None, "sessions_used_this_month": 0}
_FEEDBACK = {"overall_band": 7.0, "scores": {"grammar": {"score": 7}}}


async def _fake_score_speaking(**_kwargs):
    return dict(_FEEDBACK)


async def _fake_noop(*_a, **_k):
    return {}


class SpeakingSubmissionStoresSessionLinkTests(unittest.TestCase):
    def setUp(self):
        self.captured = {}
        rows_by_table = {"scenarios": [_SCENARIO_ROW], "user_profiles": [_PROFILE_ROW]}
        self.service_client = _FakeTable(rows_by_table, self.captured)
        self.user_db = _FakeTable(rows_by_table, self.captured)

        async def _fake_insights(*_a, **_k):
            return {}

        for p in [
            patch.object(speaking_module, "get_supabase", lambda: self.service_client),
            patch.object(speaking_module, "score_speaking", _fake_score_speaking),
            patch.object(speaking_module, "record_skill_observations", _fake_noop),
            patch.object(speaking_module, "is_first_ever_session", lambda *_a, **_k: False),
            patch.object(speaking_module, "claim_session_for_scoring", lambda *_a, **_k: True),
            patch.object(speaking_module, "_build_speaking_insights", _fake_insights),
        ]:
            p.start()
            self.addCleanup(p.stop)

    def test_new_speaking_submission_stores_session_usage_id(self):
        with patch.object(speaking_module, "validate_session", lambda *_a, **_k: True):
            _run(speaking_module.score_speaking_session(
                request=_make_request(session_id=99),
                current_user=UserInfo(id="u1", email="u1@example.com"),
                user_db=self.user_db,
            ))

        inserted = self.captured["submissions"][0]
        self.assertEqual(inserted["session_usage_id"], 99)
        # Reused, not invented: the same id that was validated, not the
        # submission's own future id, a scenario id, or a random value.

    def test_invalid_session_id_is_rejected_before_any_insert(self):
        with patch.object(speaking_module, "validate_session", lambda *_a, **_k: False):
            with self.assertRaises(HTTPException) as ctx:
                _run(speaking_module.score_speaking_session(
                    request=_make_request(session_id=12345),
                    current_user=UserInfo(id="u1", email="u1@example.com"),
                    user_db=self.user_db,
                ))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertNotIn("submissions", self.captured)

    def test_missing_session_id_is_rejected_before_any_insert(self):
        with self.assertRaises(HTTPException) as ctx:
            _run(speaking_module.score_speaking_session(
                request=_make_request(session_id=None),
                current_user=UserInfo(id="u1", email="u1@example.com"),
                user_db=self.user_db,
            ))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertNotIn("submissions", self.captured)


# ── Admin Inspector: legacy link + realtime unaffected + safe fallback ────
# (items 8-12) -- extends test_admin_speaking_evidence.py's fixtures.

_INTERLOCUTOR_CARD = {
    "mood": "anxious",
    "emotional_triggers": ["surgery"],
    "questions_to_ask": ["operation"],
}
_HISTORY = [
    {"role": "patient", "content": "I'm really worried about the operation."},
    {"role": "nurse", "content": "I can understand why you're worried."},
]
_SCENARIO_ROW_ADMIN = {"id": 1, "title": "Pre-op anxiety", "setting": "Ward", "interlocutor_card": _INTERLOCUTOR_CARD}


class _FakeQuery:
    def __init__(self, rows):
        self._rows = list(rows)

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._rows = [r for r in self._rows if r.get(col) == val]
        return self

    def order(self, *_a, **_k):
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


def _tables(**overrides):
    base = {"scenarios": [_SCENARIO_ROW_ADMIN], "session_transcripts": [], "realtime_session_metrics": [], "submissions": []}
    base.update(overrides)
    return base


class LegacySemanticStateLinkTests(unittest.TestCase):
    def test_linked_legacy_submission_loads_persisted_semantic_state(self):
        """Item 9: legacy inspector reaches session_semantic_state through
        submission.session_usage_id -- not through the submission's own id
        (7) and not through some other session (item 12's isolation)."""
        tables = _tables(submissions=[
            {"id": 7, "user_id": "u1", "scenario_id": 1, "module": "speaking",
             "answer": "Patient: I'm really worried about the operation.\nNurse: I can understand why you're worried.",
             "created_at": "t", "session_usage_id": 555},
        ])
        supabase = _FakeSupabase(tables)
        captured = {}
        sentinel_hints = object()

        async def fake_load(session_usage_id):
            captured["loaded_session_usage_id"] = session_usage_id
            return sentinel_hints

        async def fake_build(*_a, **kwargs):
            captured["prior"] = kwargs.get("prior")
            return build_speaking_evidence(_INTERLOCUTOR_CARD, _HISTORY)

        with patch.object(evidence_module, "get_supabase", return_value=supabase), \
             patch.object(evidence_module.session_semantic_state, "load_semantic_state", fake_load), \
             patch.object(evidence_module, "build_speaking_evidence_with_semantics", fake_build):
            _run(evidence_module.get_speaking_evidence(
                pipeline=evidence_module.Pipeline.legacy, session_id=7, current_user=None,
            ))

        # session_usage_id (555), not the submission id (7) -- the whole
        # point of Step 14 is reusing the validated session id, not inventing
        # or conflating it with the submission's own identity.
        self.assertEqual(captured["loaded_session_usage_id"], 555)
        self.assertIs(captured["prior"], sentinel_hints)

    def test_second_linked_submission_does_not_leak_first_sessions_state(self):
        """Item 12: submission A cannot retrieve session semantic state B."""
        tables = _tables(submissions=[
            {"id": 7, "user_id": "u1", "scenario_id": 1, "module": "speaking",
             "answer": "Patient: hi\nNurse: hello", "created_at": "t", "session_usage_id": 555},
            {"id": 8, "user_id": "u2", "scenario_id": 1, "module": "speaking",
             "answer": "Patient: hi\nNurse: hello", "created_at": "t", "session_usage_id": 556},
        ])
        supabase = _FakeSupabase(tables)
        captured = []

        async def fake_load(session_usage_id):
            captured.append(session_usage_id)
            return None

        with patch.object(evidence_module, "get_supabase", return_value=supabase), \
             patch.object(evidence_module.session_semantic_state, "load_semantic_state", fake_load):
            _run(evidence_module.get_speaking_evidence(
                pipeline=evidence_module.Pipeline.legacy, session_id=7, current_user=None,
            ))
            _run(evidence_module.get_speaking_evidence(
                pipeline=evidence_module.Pipeline.legacy, session_id=8, current_user=None,
            ))

        self.assertEqual(captured, [555, 556])

    def test_unlinked_legacy_submission_falls_back_without_guessing(self):
        """Item 11: historical submission with session_usage_id = NULL must
        not trigger a semantic-state lookup at all (no guessing), same as
        pre-Step-14 behavior."""
        tables = _tables(submissions=[
            {"id": 9, "user_id": "u1", "scenario_id": 1, "module": "speaking",
             "answer": "Patient: I'm really worried about the operation.\nNurse: I can understand why you're worried.",
             "created_at": "t"},  # no session_usage_id key
        ])
        supabase = _FakeSupabase(tables)
        called = {"n": 0}

        async def fake_load(session_usage_id):
            called["n"] += 1
            return None

        with patch.object(evidence_module, "get_supabase", return_value=supabase), \
             patch.object(evidence_module.session_semantic_state, "load_semantic_state", fake_load):
            result = _run(evidence_module.get_speaking_evidence(
                pipeline=evidence_module.Pipeline.legacy, session_id=9, current_user=None,
            ))

        self.assertEqual(called["n"], 0)
        expected = build_speaking_evidence(_INTERLOCUTOR_CARD, _HISTORY).model_dump()
        self.assertEqual(result["evidence"], expected)

    def test_realtime_pipeline_still_loads_by_session_id_directly(self):
        """Item 10: realtime inspector's Step 13 behavior is unchanged --
        session_id IS session_usage_id for that pipeline, no submissions
        lookup involved."""
        tables = _tables(session_transcripts=[
            {"session_usage_id": 42, "user_id": "u1", "scenario_id": 1,
             "transcript": [{"role": "nurse", "text": "hi"}], "created_at": "t"},
        ])
        supabase = _FakeSupabase(tables)
        captured = {}

        async def fake_load(session_usage_id):
            captured["loaded_session_usage_id"] = session_usage_id
            return None

        with patch.object(evidence_module, "get_supabase", return_value=supabase), \
             patch.object(evidence_module.session_semantic_state, "load_semantic_state", fake_load):
            _run(evidence_module.get_speaking_evidence(
                pipeline=evidence_module.Pipeline.realtime, session_id=42, current_user=None,
            ))

        self.assertEqual(captured["loaded_session_usage_id"], 42)


if __name__ == "__main__":
    unittest.main()
