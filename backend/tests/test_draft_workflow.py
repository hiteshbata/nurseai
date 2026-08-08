"""RC3.3 self-check: the draft review/publish status machine (draft_store)
and the publish payload mapping (draft_publisher). Uses a minimal in-memory
fake of the Supabase query builder -- enough to exercise the branch logic
without a real DB.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import draft_store, draft_publisher


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self._filters = []
        self._op = None
        self._payload = None

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def ilike(self, col, val):
        self._filters.append((col, val))
        return self

    def limit(self, *_a):
        return self

    def order(self, *_a, **_k):
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def execute(self):
        matched = [r for r in self._rows if all(r.get(c) == v for c, v in self._filters)]
        if self._op == "update":
            for r in matched:
                r.update(self._payload)
            return FakeResult(matched)
        if self._op == "insert":
            new_id = max([r.get("id", 0) for r in self._rows], default=0) + 1
            row = {"id": new_id, **self._payload}
            self._rows.append(row)
            return FakeResult([row])
        if self._op == "delete":
            for r in matched:
                self._rows.remove(r)
            return FakeResult(matched)
        return FakeResult(matched)


class FakeSupabase:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        self.tables.setdefault(name, [])
        return FakeQuery(self.tables[name])


def _draft(status="draft", **overrides):
    base = {
        "id": 1, "module": "speaking", "draft_name": "n", "ai_title": None,
        "metadata": {}, "prompt": {}, "generated_content": {"title": "t"},
        "validation_warnings": [], "status": status, "model_used": None,
        "ai_generated": True, "created_by": None,
    }
    base.update(overrides)
    return base


def _patched(monkeypatch, rows):
    fake = FakeSupabase()
    fake.tables["generated_content_drafts"] = rows
    monkeypatch.setattr(draft_store, "get_supabase", lambda: fake)
    return fake


# ── status machine ────────────────────────────────────────────────────

def test_submit_for_review_from_draft_succeeds(monkeypatch):
    rows = [_draft(status="draft")]
    _patched(monkeypatch, rows)
    updated = draft_store.submit_for_review(1)
    assert updated["status"] == "review"


def test_submit_for_review_from_review_rejected(monkeypatch):
    rows = [_draft(status="review")]
    _patched(monkeypatch, rows)
    try:
        draft_store.submit_for_review(1)
        assert False, "expected InvalidTransitionError"
    except draft_store.InvalidTransitionError:
        pass


def test_approve_sets_reviewed_and_approved_fields(monkeypatch):
    rows = [_draft(status="review")]
    _patched(monkeypatch, rows)
    updated = draft_store.approve(1, "admin-1")
    assert updated["status"] == "approved"
    assert updated["approved_by"] == "admin-1"
    assert updated["reviewed_by"] == "admin-1"


def test_reject_from_review_goes_to_draft(monkeypatch):
    rows = [_draft(status="review")]
    _patched(monkeypatch, rows)
    updated = draft_store.reject(1, "admin-1")
    assert updated["status"] == "draft"


def test_reject_from_approved_goes_to_review(monkeypatch):
    rows = [_draft(status="approved")]
    _patched(monkeypatch, rows)
    updated = draft_store.reject(1, "admin-1")
    assert updated["status"] == "review"


def test_reject_from_draft_rejected(monkeypatch):
    rows = [_draft(status="draft")]
    _patched(monkeypatch, rows)
    try:
        draft_store.reject(1, "admin-1")
        assert False, "expected InvalidTransitionError"
    except draft_store.InvalidTransitionError:
        pass


def test_archive_blocked_once_published(monkeypatch):
    rows = [_draft(status="published")]
    _patched(monkeypatch, rows)
    try:
        draft_store.archive(1)
        assert False, "expected InvalidTransitionError"
    except draft_store.InvalidTransitionError:
        pass


def test_mark_published_requires_approved(monkeypatch):
    rows = [_draft(status="draft")]
    _patched(monkeypatch, rows)
    try:
        draft_store.mark_published(1, "owner-1")
        assert False, "expected InvalidTransitionError"
    except draft_store.InvalidTransitionError:
        pass


# ── content update + revisions ───────────────────────────────────────

def test_update_content_writes_revision_only_when_content_changes(monkeypatch):
    rows = [_draft(status="draft")]
    fake = FakeSupabase()
    fake.tables["generated_content_drafts"] = rows
    monkeypatch.setattr(draft_store, "get_supabase", lambda: fake)

    draft_store.update_content(1, draft_name="renamed only", editor_id="a1")
    assert fake.tables.get("generated_content_draft_revisions", []) == []

    draft_store.update_content(1, generated_content={"title": "changed"}, editor_id="a1")
    revisions = fake.tables["generated_content_draft_revisions"]
    assert len(revisions) == 1
    assert revisions[0]["after"]["generated_content"] == {"title": "changed"}


# ── publish payload mapping ───────────────────────────────────────────

def test_writing_payload_maps_case_notes_task_and_key_points():
    draft = _draft(module="writing", generated_content={
        "title": "Discharge letter", "difficulty": "medium",
        "case_notes": "Patient details...", "task": "Write to the GP...",
        "key_points": ["point 1", "point 2"],
    })
    payload = draft_publisher._scenario_payload(draft)
    assert payload["setting"] == "Patient details..."
    assert payload["nurse_card"] == {"role": "Write to the GP..."}
    assert payload["key_points"] == ["point 1", "point 2"]
    assert payload["module"] == "writing"


def test_reading_payload_clamps_invalid_part_to_c():
    draft = _draft(module="reading", generated_content={
        "title": "A passage", "part": "A", "body": "text", "questions": [],
    })
    passage, questions = draft_publisher._reading_payload(draft)
    assert passage["part"] == "C"
    assert questions == []


def test_listening_payload_defaults_missing_part_to_b():
    draft = _draft(module="listening", generated_content={
        "title": "A section", "transcript": [], "questions": [{"content": "q"}],
    })
    section, questions = draft_publisher._listening_payload(draft)
    assert section["part"] == "B"
    assert len(questions) == 1


# ── standalone reading/listening publish starts inactive ──────────────
# A standalone row (test_id null) has no test-level "Make Live" step to
# go through, so it must not be born is_active=True -- that would make it
# instantly student-visible via GET /reading/passages the moment an admin
# clicks Publish. See draft_publisher.py's module docstring.

def test_reading_payload_starts_inactive():
    draft = _draft(module="reading", generated_content={
        "title": "A passage", "part": "B", "body": "text", "questions": [],
    })
    passage, _ = draft_publisher._reading_payload(draft)
    assert passage["is_active"] is False
    assert passage.get("test_id") is None


def test_listening_payload_starts_inactive():
    draft = _draft(module="listening", generated_content={
        "title": "A section", "transcript": [], "questions": [],
    })
    section, _ = draft_publisher._listening_payload(draft)
    assert section["is_active"] is False
    assert section.get("test_id") is None


def test_scenario_payload_unaffected_by_this_fix():
    # Speaking/Writing publish is out of scope for this fix -- guards that
    # _scenario_payload wasn't touched (no is_active key; DB default handles it).
    draft = _draft(module="speaking", generated_content={
        "title": "S1", "difficulty": "easy", "setting": "ward",
        "nurse_card": {}, "interlocutor_card": {},
    })
    payload = draft_publisher._scenario_payload(draft)
    assert "is_active" not in payload


def test_published_reading_content_starts_inactive_and_hidden_from_students(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(module="reading", generated_content={
        "title": "New passage", "part": "B", "body": "text",
        "questions": [{"type": "mcq", "content": "q1", "options": ["a", "b"], "correct_answer": "a"}],
    })
    result = draft_publisher.publish(draft, "admin-1")

    row = next(r for r in fake.tables["reading_passages"] if r["id"] == result["id"])
    assert row["is_active"] is False
    assert row.get("test_id") is None

    # Same filter GET /reading/passages uses (reading.py list_passages) --
    # the published row must not come back while inactive.
    visible_ids = [r["id"] for r in fake.table("reading_passages").select("id").eq("is_active", True).execute().data]
    assert result["id"] not in visible_ids


def test_published_listening_content_starts_inactive_and_hidden_from_students(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(module="listening", generated_content={
        "title": "New section", "transcript": [],
        "questions": [{"type": "mcq", "content": "q1", "options": ["a", "b"], "correct_answer": "a"}],
    })
    result = draft_publisher.publish(draft, "admin-1")

    row = next(r for r in fake.tables["listening_sections"] if r["id"] == result["id"])
    assert row["is_active"] is False
    assert row.get("test_id") is None

    visible_ids = [r["id"] for r in fake.table("listening_sections").select("id").eq("is_active", True).execute().data]
    assert result["id"] not in visible_ids


if __name__ == "__main__":
    import types
    mod = types.SimpleNamespace()

    class MP:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    mp = MP()
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        import inspect
        if "monkeypatch" in inspect.signature(t).parameters:
            t(mp)
        else:
            t()
        passed += 1
    print(f"{passed}/{len(tests)} draft workflow checks passed")
