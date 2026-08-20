"""RC3.3 self-check: the draft review/publish status machine (draft_store)
and the publish payload mapping (draft_publisher). Uses a minimal in-memory
fake of the Supabase query builder -- enough to exercise the branch logic
without a real DB.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import draft_store, draft_publisher, listening_audio


class FakeResult:
    def __init__(self, data):
        self.data = data
        self.count = len(data)


class _NotProxy:
    """Mirrors supabase-py's query.not_.in_(col, values) -- a NOT IN filter.
    Only .in_ is implemented; nothing else in this codebase uses .not_ yet."""
    def __init__(self, query):
        self._query = query

    def in_(self, col, values):
        self._query._not_in_filters.append((col, set(values)))
        return self._query


class FakeQuery:
    def __init__(self, rows, table_name=None, enforce_source_draft_unique=False, unique_cols=("source_draft_id",), supabase=None):
        self._rows = rows
        self._table_name = table_name
        self._enforce_source_draft_unique = enforce_source_draft_unique
        self._unique_cols = unique_cols
        self._supabase = supabase
        self._filters = []
        self._in_filters = []
        self._not_in_filters = []
        self._op = None
        self._payload = None

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def in_(self, col, values):
        self._in_filters.append((col, set(values)))
        return self

    def ilike(self, col, val):
        self._filters.append((col, val))
        return self

    def limit(self, *_a):
        return self

    def range(self, *_a):
        return self

    def order(self, *_a, **_k):
        return self

    @property
    def not_(self):
        return _NotProxy(self)

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
        matched = [
            r for r in self._rows
            if all(r.get(c) == v for c, v in self._filters)
            and all(r.get(c) in vals for c, vals in self._in_filters)
            and all(r.get(c) not in vals for c, vals in self._not_in_filters)
        ]
        if self._op == "update":
            for r in matched:
                r.update(self._payload)
            return FakeResult(matched)
        if self._op == "insert":
            # Fault injection for _replace_questions tests: fail_insert_on_call[table]
            # = the 1-indexed call number (across the whole test) that should raise,
            # simulating a transient DB error partway through a batch of inserts.
            if self._supabase is not None:
                counts = self._supabase._insert_counts
                counts[self._table_name] = counts.get(self._table_name, 0) + 1
                fail_at = self._supabase.fail_insert_on_call.get(self._table_name)
                if fail_at is not None and counts[self._table_name] == fail_at:
                    raise Exception(f"simulated insert failure on {self._table_name} (call #{fail_at})")
            # Mirrors reading_passages_source_draft_uidx / listening_sections_source_draft_uidx
            # (20260808050000_draft_review_workflow.sql, widened by
            # 20260816000000_reading_part_b_multi_passage.sql for reading_passages
            # and 20260819020000_listening_sections_part_studio.sql for
            # listening_sections) -- a partial unique index, null-safe (legacy
            # rows with no source_draft_id never conflict). Both tables' index
            # is now (source_draft_id, <seq column>) so a multi-row draft's N
            # passages/sections (seq 0..N-1) can share one source_draft_id.
            if self._enforce_source_draft_unique:
                sdid = self._payload.get("source_draft_id")
                if sdid is not None:
                    if len(self._unique_cols) == 2:
                        seq_col = self._unique_cols[1]
                        seq = self._payload.get(seq_col, 0)
                        conflict = any(
                            r.get("source_draft_id") == sdid and r.get(seq_col, 0) == seq
                            for r in self._rows
                        )
                    else:
                        conflict = any(r.get("source_draft_id") == sdid for r in self._rows)
                    if conflict:
                        raise Exception(
                            f'duplicate key value violates unique constraint "{self._table_name}_source_draft_uidx"'
                        )
            new_id = max([r.get("id", 0) for r in self._rows], default=0) + 1
            row = {"id": new_id, **self._payload}
            self._rows.append(row)
            return FakeResult([row])
        if self._op == "delete":
            # Fault injection: fail_next_delete is a one-shot set of table names --
            # the next delete() on that table raises once, then the trigger clears
            # itself (so a cleanup retry against the same table can still succeed).
            if self._supabase is not None and self._table_name in self._supabase.fail_next_delete:
                self._supabase.fail_next_delete.discard(self._table_name)
                raise Exception(f"simulated delete failure on {self._table_name}")
            for r in matched:
                self._rows.remove(r)
            return FakeResult(matched)
        return FakeResult(matched)


class FakeSupabase:
    # Only these two tables get the new partial unique index -- scenarios
    # stays protected by its existing title uniqueness instead (see the
    # migration comment), so it's deliberately not in this set.
    UNIQUE_SOURCE_DRAFT_TABLES = {
        "reading_passages": ("source_draft_id", "passage_seq"),
        # Widened by the Phase 3F migration (20260819020000_listening_sections_part_studio.sql)
        # the same way reading_passages was widened for Part B -- see that
        # migration's comment. Legacy flat-listening payloads never set
        # section_seq, so they default to 0 same as the real DB column default.
        "listening_sections": ("source_draft_id", "section_seq"),
    }

    def __init__(self):
        self.tables = {}
        self._insert_counts = {}
        self.fail_insert_on_call = {}
        self.fail_next_delete = set()

    def table(self, name):
        self.tables.setdefault(name, [])
        return FakeQuery(
            self.tables[name], table_name=name, supabase=self,
            enforce_source_draft_unique=name in self.UNIQUE_SOURCE_DRAFT_TABLES,
            unique_cols=self.UNIQUE_SOURCE_DRAFT_TABLES.get(name, ("source_draft_id",)),
        )


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


def test_mark_published_is_compare_and_set_not_check_then_act(monkeypatch):
    """Module 1 Section 12E Step 5/7: mark_published's update is filtered on
    .eq("status", "approved") -- not a separate read followed by an
    unconditional write -- so of two calls racing for the same draft, only
    the first can ever match and write; the second finds zero rows updated
    (status is already 'published' by then) and raises InvalidTransitionError
    instead of silently overwriting published_by/published_at a second time."""
    rows = [_draft(status="approved")]
    _patched(monkeypatch, rows)

    first = draft_store.mark_published(1, "owner-1")
    assert first["status"] == "published"
    assert first["published_by"] == "owner-1"

    try:
        draft_store.mark_published(1, "owner-2")
        assert False, "expected InvalidTransitionError"
    except draft_store.InvalidTransitionError:
        pass
    assert rows[0]["published_by"] == "owner-1"  # second call never wrote


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


def test_reading_payload_preserves_part_a():
    draft = _draft(module="reading", generated_content={
        "title": "A passage", "part": "A", "body": "text", "questions": [],
    })
    passage, questions = draft_publisher._reading_payload(draft)
    assert passage["part"] == "A"
    assert questions == []


def test_reading_payload_rejects_part_b_as_a_single_combined_passage():
    """Part B is 6 independent passages (_reading_part_b_payloads), never
    one -- _reading_payload must refuse it instead of silently combining
    the 6 into a single row."""
    draft = _draft(module="reading", generated_content={
        "part": "B", "passages": [],
    })
    try:
        draft_publisher._reading_payload(draft)
        assert False, "expected InvalidPartError"
    except draft_publisher.InvalidPartError:
        pass


def test_reading_payload_preserves_part_c():
    draft = _draft(module="reading", generated_content={
        "title": "A passage", "part": "A", "body": "text", "questions": [],
    })
    passage, _ = draft_publisher._reading_payload(draft)
    assert passage["part"] == "A"


def test_reading_payload_rejects_invalid_part_instead_of_silently_converting():
    draft = _draft(module="reading", generated_content={
        "title": "A passage", "part": "D", "body": "text", "questions": [],
    })
    try:
        draft_publisher._reading_payload(draft)
        assert False, "expected InvalidPartError"
    except draft_publisher.InvalidPartError:
        pass


def test_reading_payload_rejects_missing_part():
    draft = _draft(module="reading", generated_content={
        "title": "A passage", "body": "text", "questions": [],
    })
    try:
        draft_publisher._reading_payload(draft)
        assert False, "expected InvalidPartError"
    except draft_publisher.InvalidPartError:
        pass


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
        "title": "A passage", "part": "A", "body": "text", "questions": [],
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
        "title": "New passage", "part": "A", "body": "text",
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


# ── Blocker 1: one draft is at most one production row ──────────────────
# (reading_passages_source_draft_uidx / listening_sections_source_draft_uidx,
# 20260808050000_draft_review_workflow.sql, plus publish()'s own
# _existing_production_id lookup for every module). Guards double-click
# Publish, two admins racing, or a retry after publish() succeeded but the
# subsequent mark_published() call failed -- and, per the final design
# review, also legitimate republish-after-edit: that case UPDATEs the
# existing row rather than erroring or duplicating (see the "full
# republish lifecycle" tests further down).

def test_reading_publish_succeeds_first_time(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(module="reading", generated_content={
        "title": "First publish", "part": "A", "body": "text", "questions": [],
    })
    result = draft_publisher.publish(draft, "admin-1")
    assert result["table"] == "reading_passages"
    assert result["action"] == "created"
    assert len(fake.tables["reading_passages"]) == 1


def test_reading_republish_of_unchanged_draft_updates_not_duplicates(monkeypatch):
    """Two Publish calls for the same draft, no edit in between (double-click,
    or two admins racing) -- must not create a second row. In the ordinary
    (non-racing) case the router's own status=='approved' check is the first
    line of defense (status flips to 'published' after the first call, so a
    literal double-click never reaches publish() a second time at all); this
    exercises publish() itself directly, as the backstop for whatever gets
    past that check (a genuine race, or a retry after mark_published failed)."""
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=42, module="reading", generated_content={
        "title": "Race condition", "part": "A", "body": "text", "questions": [],
    })
    first = draft_publisher.publish(draft, "admin-1")
    second = draft_publisher.publish(draft, "admin-2")
    assert first["action"] == "created"
    assert second["action"] == "updated"
    assert first["id"] == second["id"]
    assert len(fake.tables["reading_passages"]) == 1


def test_listening_republish_of_unchanged_draft_updates_not_duplicates(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=43, module="listening", generated_content={
        "title": "Race condition", "transcript": [], "questions": [],
    })
    first = draft_publisher.publish(draft, "admin-1")
    second = draft_publisher.publish(draft, "admin-2")
    assert first["action"] == "created"
    assert second["action"] == "updated"
    assert first["id"] == second["id"]
    assert len(fake.tables["listening_sections"]) == 1


def test_legacy_rows_with_null_source_draft_id_unaffected(monkeypatch):
    fake = FakeSupabase()
    # Pre-existing rows from before this workflow existed -- no source_draft_id at all.
    fake.tables["reading_passages"] = [
        {"id": 1, "title": "Legacy passage 1", "is_active": True},
        {"id": 2, "title": "Legacy passage 2", "is_active": True},
    ]
    fake.tables["listening_sections"] = [
        {"id": 1, "title": "Legacy section", "is_active": True},
    ]
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)

    reading_draft = _draft(id=44, module="reading", generated_content={
        "title": "New passage", "part": "A", "body": "text", "questions": [],
    })
    listening_draft = _draft(id=45, module="listening", generated_content={
        "title": "New section", "transcript": [], "questions": [],
    })
    reading_result = draft_publisher.publish(reading_draft, "admin-1")
    listening_result = draft_publisher.publish(listening_draft, "admin-1")

    assert reading_result["table"] == "reading_passages"
    assert listening_result["table"] == "listening_sections"
    assert len(fake.tables["reading_passages"]) == 3
    assert len(fake.tables["listening_sections"]) == 2


# ── Blocker 2: content edit after approval forces re-review ────────────
# An approval signs off on specific content, not "whatever this becomes
# later". update_content() must drop approved/published back to 'review'
# (and clear the stale approved_by/approved_at) when generated_content
# itself changes -- not on a metadata-only or rename-only save.

def test_approved_draft_content_edit_forces_review(monkeypatch):
    rows = [_draft(status="approved", approved_by="admin-1", approved_at="2026-08-01T00:00:00Z",
                    generated_content={"title": "original"})]
    fake = _patched(monkeypatch, rows)
    updated = draft_store.update_content(1, generated_content={"title": "changed"}, editor_id="a1")
    assert updated["status"] == "review"
    assert updated["approved_by"] is None
    assert updated["approved_at"] is None
    assert fake.tables["generated_content_drafts"][0]["status"] == "review"


def test_approved_draft_metadata_only_edit_keeps_approved(monkeypatch):
    rows = [_draft(status="approved", approved_by="admin-1", approved_at="2026-08-01T00:00:00Z",
                    generated_content={"title": "original"}, metadata={})]
    _patched(monkeypatch, rows)
    updated = draft_store.update_content(1, metadata={"note": "internal only"}, editor_id="a1")
    assert updated["status"] == "approved"
    assert updated["approved_by"] == "admin-1"
    assert updated["approved_at"] == "2026-08-01T00:00:00Z"


def test_draft_status_content_edit_no_regression(monkeypatch):
    rows = [_draft(status="draft", generated_content={"title": "original"})]
    _patched(monkeypatch, rows)
    updated = draft_store.update_content(1, generated_content={"title": "changed"}, editor_id="a1")
    assert updated["status"] == "draft"


def test_review_status_content_edit_no_regression(monkeypatch):
    rows = [_draft(status="review", generated_content={"title": "original"})]
    _patched(monkeypatch, rows)
    updated = draft_store.update_content(1, generated_content={"title": "changed"}, editor_id="a1")
    assert updated["status"] == "review"


def test_published_draft_content_edit_forces_review_not_silent(monkeypatch):
    rows = [_draft(status="published", approved_by="admin-1", approved_at="2026-08-01T00:00:00Z",
                    published_by="owner-1", published_at="2026-08-02T00:00:00Z",
                    generated_content={"title": "original"})]
    fake = _patched(monkeypatch, rows)
    updated = draft_store.update_content(1, generated_content={"title": "changed"}, editor_id="a1")
    assert updated["status"] != "published"
    assert updated["status"] == "review"
    assert updated["approved_by"] is None
    assert fake.tables["generated_content_drafts"][0]["status"] != "published"


def test_publish_still_requires_approved_after_edit_reset(monkeypatch):
    """After the reset above, the draft is 'review' again -- mark_published
    (called by the publish router only after draft_publisher.publish()
    succeeds) must still refuse it, same as any other non-approved draft."""
    rows = [_draft(status="review")]
    _patched(monkeypatch, rows)
    try:
        draft_store.mark_published(1, "owner-1")
        assert False, "expected InvalidTransitionError"
    except draft_store.InvalidTransitionError:
        pass


# ── Full lifecycle: publish -> edit -> review -> approve -> republish ──
# End-to-end coverage of the fix from the final design review: publish()
# was insert-only, so this legitimate cycle either dead-ended (Reading/
# Listening, blocked by the new unique index with no update path) or could
# create a second live row (Speaking/Writing, if the edit changed the
# title). draft_store and draft_publisher each call get_supabase()
# independently, so these need both monkeypatched to the SAME fake to
# observe the whole cycle, not just one service's half of it.

def _shared_fake(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_store, "get_supabase", lambda: fake)
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    return fake


def test_reading_full_republish_lifecycle(monkeypatch):
    fake = _shared_fake(monkeypatch)
    fake.tables["generated_content_drafts"] = [_draft(
        id=1, status="approved", module="reading",
        generated_content={
            "title": "V1", "part": "A", "body": "first version",
            "questions": [{"type": "mcq", "content": "q1", "options": ["a", "b"], "correct_answer": "a"}],
        },
    )]

    draft = draft_store.get_draft(1)
    first = draft_publisher.publish(draft, "owner-1")
    draft_store.mark_published(1, "owner-1")
    assert first["action"] == "created"
    assert len(fake.tables["reading_passages"]) == 1
    passage_id = first["id"]

    # A separate, existing admin action -- publish() itself never sets is_active=True.
    fake.tables["reading_passages"][0]["is_active"] = True

    updated = draft_store.update_content(1, generated_content={
        "title": "V2", "part": "A", "body": "corrected version",
        "questions": [{"type": "mcq", "content": "q1-fixed", "options": ["a", "b"], "correct_answer": "b"}],
    }, editor_id="analyst-1")
    assert updated["status"] == "review"

    # Currently-live production content is untouched while the draft is under review.
    assert fake.tables["reading_passages"][0]["is_active"] is True
    assert fake.tables["reading_passages"][0]["body"] == "first version"

    draft_store.approve(1, "admin-1")
    draft = draft_store.get_draft(1)
    second = draft_publisher.publish(draft, "owner-1")
    draft_store.mark_published(1, "owner-1")

    assert second["action"] == "updated"
    assert second["id"] == passage_id
    assert len(fake.tables["reading_passages"]) == 1  # still exactly one row -- no duplicate

    row = next(r for r in fake.tables["reading_passages"] if r["id"] == passage_id)
    assert row["body"] == "corrected version"
    assert row["is_active"] is True  # republish didn't reset the earlier "make live"
    assert row["source_draft_id"] == 1

    q_texts = {q["content"] for q in fake.tables["questions"] if q.get("passage_id") == passage_id}
    assert q_texts == {"q1-fixed"}  # old question replaced, not appended alongside


def test_listening_full_republish_lifecycle(monkeypatch):
    fake = _shared_fake(monkeypatch)
    fake.tables["generated_content_drafts"] = [_draft(
        id=1, status="approved", module="listening",
        generated_content={
            "title": "V1", "transcript": [{"speaker": "Nurse", "text": "v1"}],
            "questions": [{"type": "mcq", "content": "q1", "options": ["a", "b"], "correct_answer": "a"}],
        },
    )]

    draft = draft_store.get_draft(1)
    first = draft_publisher.publish(draft, "owner-1")
    draft_store.mark_published(1, "owner-1")
    section_id = first["id"]
    fake.tables["listening_sections"][0]["is_active"] = True

    draft_store.update_content(1, generated_content={
        "title": "V2", "transcript": [{"speaker": "Nurse", "text": "v2"}],
        "questions": [{"type": "mcq", "content": "q1-fixed", "options": ["a", "b"], "correct_answer": "b"}],
    }, editor_id="analyst-1")
    assert fake.tables["listening_sections"][0]["is_active"] is True  # still untouched, still under review

    draft_store.approve(1, "admin-1")
    draft = draft_store.get_draft(1)
    second = draft_publisher.publish(draft, "owner-1")
    updated_draft = draft_store.mark_published(1, "owner-1")

    assert second["action"] == "updated"
    assert second["id"] == section_id
    assert len(fake.tables["listening_sections"]) == 1
    assert updated_draft["status"] == "published"

    row = next(r for r in fake.tables["listening_sections"] if r["id"] == section_id)
    assert row["title"] == "V2"
    assert row["is_active"] is True
    assert row["source_draft_id"] == 1
    q_texts = {q["content"] for q in fake.tables["questions"] if q.get("section_id") == section_id}
    assert q_texts == {"q1-fixed"}


def test_writing_full_republish_lifecycle_with_title_change(monkeypatch):
    """The exact case the final review flagged as a blocker: scenarios has
    no source_draft_id uniqueness (title uniqueness covers first-publish
    races instead), so a republish whose edit also changes the title used
    to sail past that guard and INSERT a second, duplicate, live scenario.
    publish() now looks the row up by source_draft_id before deciding
    insert vs. update, so the title changing is irrelevant to that decision."""
    fake = _shared_fake(monkeypatch)
    fake.tables["generated_content_drafts"] = [_draft(
        id=2, status="approved", module="writing",
        generated_content={
            "title": "Discharge Letter V1", "difficulty": "medium",
            "case_notes": "notes v1", "task": "task v1", "key_points": ["a"],
        },
    )]

    draft = draft_store.get_draft(2)
    first = draft_publisher.publish(draft, "owner-1")
    draft_store.mark_published(2, "owner-1")
    assert first["action"] == "created"
    assert len(fake.tables["scenarios"]) == 1

    draft_store.update_content(2, generated_content={
        "title": "Discharge Letter V2 (renamed)", "difficulty": "medium",
        "case_notes": "notes v2", "task": "task v2", "key_points": ["b"],
    }, editor_id="analyst-1")
    draft_store.approve(2, "admin-1")
    draft = draft_store.get_draft(2)
    second = draft_publisher.publish(draft, "owner-1")
    updated_draft = draft_store.mark_published(2, "owner-1")

    assert second["action"] == "updated"
    assert second["id"] == first["id"]
    assert len(fake.tables["scenarios"]) == 1  # still one scenario -- no duplicate live row
    assert updated_draft["status"] == "published"
    row = fake.tables["scenarios"][0]
    assert row["title"] == "Discharge Letter V2 (renamed)"
    assert row["setting"] == "notes v2"
    assert row["source_draft_id"] == 2


def test_speaking_full_republish_lifecycle_with_title_change(monkeypatch):
    fake = _shared_fake(monkeypatch)
    fake.tables["generated_content_drafts"] = [_draft(
        id=3, status="approved", module="speaking",
        generated_content={
            "title": "Anxious Patient V1", "difficulty": "easy", "setting": "ward v1",
            "nurse_card": {}, "interlocutor_card": {},
        },
    )]

    draft = draft_store.get_draft(3)
    first = draft_publisher.publish(draft, "owner-1")
    draft_store.mark_published(3, "owner-1")
    assert first["action"] == "created"
    assert len(fake.tables["scenarios"]) == 1

    draft_store.update_content(3, generated_content={
        "title": "Anxious Patient V2 (renamed)", "difficulty": "easy", "setting": "ward v2",
        "nurse_card": {}, "interlocutor_card": {},
    }, editor_id="analyst-1")
    draft_store.approve(3, "admin-1")
    draft = draft_store.get_draft(3)
    second = draft_publisher.publish(draft, "owner-1")
    updated_draft = draft_store.mark_published(3, "owner-1")

    assert second["action"] == "updated"
    assert second["id"] == first["id"]
    assert len(fake.tables["scenarios"]) == 1
    assert updated_draft["status"] == "published"
    row = fake.tables["scenarios"][0]
    assert row["title"] == "Anxious Patient V2 (renamed)"
    assert row["source_draft_id"] == 3


# ── _replace_questions() failure safety ─────────────────────────────────
# The final review found this wasn't atomic: a mid-loop insert failure, or
# a failure of the old-set delete after the new set landed, could leave a
# mixed or duplicated question set with no recovery. Each test seeds a
# passage that already has a published row (existing_id findable via
# source_draft_id) and an old question set, then republishes with fault
# injection controlling exactly where the failure happens.

def test_replace_questions_normal_swap_keeps_only_new(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    fake.tables["reading_passages"] = [{"id": 1, "title": "T", "source_draft_id": 9, "is_active": False}]
    fake.tables["questions"] = [
        {"id": 100, "passage_id": 1, "content": "old-1"},
        {"id": 101, "passage_id": 1, "content": "old-2"},
    ]
    draft = _draft(id=9, module="reading", generated_content={
        "title": "T", "part": "A", "body": "b",
        "questions": [{"type": "mcq", "content": "new-1", "options": ["a", "b"], "correct_answer": "a"}],
    })
    result = draft_publisher.publish(draft, "owner-1")
    assert result["action"] == "updated"
    remaining = [q["content"] for q in fake.tables["questions"] if q["passage_id"] == 1]
    assert remaining == ["new-1"]


def test_replace_questions_fails_on_first_insert_leaves_old_intact(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    fake.tables["reading_passages"] = [{"id": 1, "title": "T", "source_draft_id": 9, "is_active": False}]
    fake.tables["questions"] = [
        {"id": 100, "passage_id": 1, "content": "old-1"},
        {"id": 101, "passage_id": 1, "content": "old-2"},
    ]
    fake.fail_insert_on_call["questions"] = 1  # the very first new-question insert fails
    draft = _draft(id=9, module="reading", generated_content={
        "title": "T", "part": "A", "body": "b",
        "questions": [{"type": "mcq", "content": "new-1", "options": ["a"], "correct_answer": "a"}],
    })
    try:
        draft_publisher.publish(draft, "owner-1")
        assert False, "expected the simulated insert failure to propagate"
    except Exception as e:
        assert "simulated insert failure" in str(e)
    remaining = sorted(q["content"] for q in fake.tables["questions"] if q["passage_id"] == 1)
    assert remaining == ["old-1", "old-2"]  # untouched -- no new rows landed at all


def test_replace_questions_fails_halfway_cleans_up_partial_new_rows(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    fake.tables["reading_passages"] = [{"id": 1, "title": "T", "source_draft_id": 9, "is_active": False}]
    fake.tables["questions"] = [
        {"id": 100, "passage_id": 1, "content": "old-1"},
        {"id": 101, "passage_id": 1, "content": "old-2"},
    ]
    fake.fail_insert_on_call["questions"] = 3  # A, B succeed; C fails
    draft = _draft(id=9, module="reading", generated_content={
        "title": "T", "part": "A", "body": "b",
        "questions": [
            {"type": "mcq", "content": "new-A", "options": ["a"], "correct_answer": "a"},
            {"type": "mcq", "content": "new-B", "options": ["a"], "correct_answer": "a"},
            {"type": "mcq", "content": "new-C", "options": ["a"], "correct_answer": "a"},
        ],
    })
    try:
        draft_publisher.publish(draft, "owner-1")
        assert False, "expected the simulated insert failure to propagate"
    except Exception as e:
        assert "simulated insert failure" in str(e)
    remaining = sorted(q["content"] for q in fake.tables["questions"] if q["passage_id"] == 1)
    # Old set survives; A and B (the partial new inserts) were cleaned back out; C never landed.
    assert remaining == ["old-1", "old-2"]


def test_replace_questions_fails_deleting_old_cleans_up_new_rows(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    fake.tables["reading_passages"] = [{"id": 1, "title": "T", "source_draft_id": 9, "is_active": False}]
    fake.tables["questions"] = [
        {"id": 100, "passage_id": 1, "content": "old-1"},
        {"id": 101, "passage_id": 1, "content": "old-2"},
    ]
    fake.fail_next_delete.add("questions")  # old-set delete fails, after the new set is fully inserted
    draft = _draft(id=9, module="reading", generated_content={
        "title": "T", "part": "A", "body": "b",
        "questions": [{"type": "mcq", "content": "new-1", "options": ["a"], "correct_answer": "a"}],
    })
    try:
        draft_publisher.publish(draft, "owner-1")
        assert False, "expected the simulated delete failure to propagate"
    except Exception as e:
        assert "simulated delete failure" in str(e)
    remaining = sorted(q["content"] for q in fake.tables["questions"] if q["passage_id"] == 1)
    # new-1 was inserted, then torn back down by the cleanup delete; old set survives untouched.
    assert remaining == ["old-1", "old-2"]


def test_replace_questions_listening_fails_halfway_cleans_up_partial_new_rows(monkeypatch):
    """Same failure mode, listening_sections/section_id -- confirms the fix
    isn't reading-specific."""
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    fake.tables["listening_sections"] = [{"id": 1, "title": "T", "source_draft_id": 9, "is_active": False}]
    fake.tables["questions"] = [
        {"id": 100, "section_id": 1, "content": "old-1"},
        {"id": 101, "section_id": 1, "content": "old-2"},
    ]
    fake.fail_insert_on_call["questions"] = 2
    draft = _draft(id=9, module="listening", generated_content={
        "title": "T", "transcript": [],
        "questions": [
            {"type": "mcq", "content": "new-A", "options": ["a"], "correct_answer": "a"},
            {"type": "mcq", "content": "new-B", "options": ["a"], "correct_answer": "a"},
        ],
    })
    try:
        draft_publisher.publish(draft, "owner-1")
        assert False, "expected the simulated insert failure to propagate"
    except Exception as e:
        assert "simulated insert failure" in str(e)
    remaining = sorted(q["content"] for q in fake.tables["questions"] if q["section_id"] == 1)
    assert remaining == ["old-1", "old-2"]


# ── Part B: 6 independent passages from one draft (Phase 4B) ───────────
# reading_passages_source_draft_uidx is now (source_draft_id, passage_seq)
# (20260816000000_reading_part_b_multi_passage.sql) instead of source_draft_id
# alone, specifically so these 6 rows can share one source_draft_id without
# the Model-A guard above (Blocker 1) rejecting the 2nd..6th insert. Part A
# is untouched: its passage_seq is always the DB default (0), so it still
# gets exactly the one-row-per-draft guarantee the old index gave. Part C
# (Phase 4C-3) reuses this same multi-passage architecture -- see the Part C
# section further below.

def _part_b_passages(n=6):
    return [
        {
            "title": f"Extract {i + 1}",
            "body": f"Body text for extract {i + 1}.",
            "questions": [{
                "type": "mcq",
                "content": f"What does extract {i + 1} say?",
                "options": ["Option A", "Option B", "Option C"],
                "correct_answer": "Option B",
            }],
        }
        for i in range(n)
    ]


def _part_b_content(passages=None):
    return {"part": "B", "passages": _part_b_passages() if passages is None else passages}


def test_part_b_payloads_builds_six_passages_with_seq_and_content_preserved():
    draft = _draft(id=50, module="reading", generated_content=_part_b_content())
    payloads = draft_publisher._reading_part_b_payloads(draft)
    assert len(payloads) == 6
    for i, (passage, questions) in enumerate(payloads):
        assert passage["part"] == "B"
        assert passage["passage_seq"] == i
        assert passage["title"] == f"Extract {i + 1}"
        assert passage["body"] == f"Body text for extract {i + 1}."
        assert passage["source_draft_id"] == 50
        assert passage["is_active"] is False
        assert len(questions) == 1
        assert questions[0]["options"] == ["Option A", "Option B", "Option C"]
        assert questions[0]["correct_answer"] == "Option B"


def test_part_b_payloads_rejects_wrong_passage_count():
    """Proves a malformed draft (wrong passage count) can't reach the
    publisher successfully -- it fails loudly at the payload-building step,
    same as _reading_payload's InvalidPartError for Part A/C."""
    draft = _draft(module="reading", generated_content=_part_b_content(_part_b_passages(5)))
    try:
        draft_publisher._reading_part_b_payloads(draft)
        assert False, "expected InvalidPartError"
    except draft_publisher.InvalidPartError:
        pass


def test_part_b_publish_creates_exactly_six_passages_all_part_b(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=60, module="reading", generated_content=_part_b_content())

    result = draft_publisher.publish(draft, "owner-1")

    rows = fake.tables["reading_passages"]
    assert len(rows) == 6
    assert {r["part"] for r in rows} == {"B"}
    assert sorted(r["passage_seq"] for r in rows) == [0, 1, 2, 3, 4, 5]
    assert result["table"] == "reading_passages"
    assert result["action"] == "created"
    assert len(result["passages"]) == 6


def test_part_b_publish_each_passage_has_exactly_one_question_with_three_options(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=61, module="reading", generated_content=_part_b_content())
    draft_publisher.publish(draft, "owner-1")

    for passage in fake.tables["reading_passages"]:
        qs = [q for q in fake.tables["questions"] if q.get("passage_id") == passage["id"]]
        assert len(qs) == 1
        assert len(json.loads(qs[0]["options"])) == 3


def test_part_b_publish_correct_answer_survives_unchanged(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    passages = _part_b_passages()
    passages[3]["questions"][0]["correct_answer"] = "Option C"
    draft = _draft(id=62, module="reading", generated_content=_part_b_content(passages))
    draft_publisher.publish(draft, "owner-1")

    by_seq = {r["passage_seq"]: r["id"] for r in fake.tables["reading_passages"]}
    q = next(q for q in fake.tables["questions"] if q["passage_id"] == by_seq[3])
    assert q["correct_answer"] == "Option C"


def test_part_b_publish_titles_and_bodies_survive_unchanged(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=63, module="reading", generated_content=_part_b_content())
    draft_publisher.publish(draft, "owner-1")

    rows_by_seq = {r["passage_seq"]: r for r in fake.tables["reading_passages"]}
    for i in range(6):
        assert rows_by_seq[i]["title"] == f"Extract {i + 1}"
        assert rows_by_seq[i]["body"] == f"Body text for extract {i + 1}."


def test_part_b_publish_questions_linked_to_their_own_passage_only(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=64, module="reading", generated_content=_part_b_content())
    draft_publisher.publish(draft, "owner-1")

    rows_by_seq = {r["passage_seq"]: r for r in fake.tables["reading_passages"]}
    for i in range(6):
        qs = [q for q in fake.tables["questions"] if q.get("passage_id") == rows_by_seq[i]["id"]]
        assert len(qs) == 1
        assert qs[0]["content"] == f"What does extract {i + 1} say?"


def test_part_b_publish_all_six_share_same_source_draft_id(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=65, module="reading", generated_content=_part_b_content())
    draft_publisher.publish(draft, "owner-1")

    assert all(r["source_draft_id"] == 65 for r in fake.tables["reading_passages"])


def test_part_a_publish_still_creates_exactly_one_row(monkeypatch):
    """Part A is untouched by the Part B changes -- still one row, one draft."""
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=66, module="reading", generated_content={
        "title": "Part A passage", "part": "A", "body": "text", "questions": [],
    })
    result = draft_publisher.publish(draft, "owner-1")
    assert len(fake.tables["reading_passages"]) == 1
    assert result["action"] == "created"


def test_reading_payload_rejects_part_c_as_a_single_combined_passage():
    """Phase 4C-3 -- Part C is now 2 independent passages (like Part B), not
    one combined passage; _reading_payload must reject it just like Part B."""
    draft = _draft(id=67, module="reading", generated_content={
        "title": "Part C passage", "part": "C", "body": "text", "questions": [],
    })
    try:
        draft_publisher._reading_payload(draft)
        assert False, "expected InvalidPartError"
    except draft_publisher.InvalidPartError:
        pass


def test_part_b_publish_preview_returns_all_six_passages(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=68, module="reading", generated_content=_part_b_content())

    preview = draft_publisher.build_preview(draft)

    passage_records = [r for r in preview["records"] if r["table"] == "reading_passages"]
    assert len(passage_records) == 6
    assert all(r["fields"]["part"] == "B" for r in passage_records)
    assert all(r["action"] == "create" for r in passage_records)
    assert sorted(r["fields"]["passage_seq"] for r in passage_records) == [0, 1, 2, 3, 4, 5]
    assert len(fake.tables["reading_passages"]) == 0  # preview writes nothing


def test_part_b_republish_of_unchanged_draft_updates_not_duplicates(monkeypatch):
    """Same idempotency guarantee as the single-passage Blocker-1 tests above,
    extended to all 6 rows -- a double-click/retry publish must UPDATE the
    same 6 rows, never create a 2nd set of 6."""
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=69, module="reading", generated_content=_part_b_content())

    first = draft_publisher.publish(draft, "admin-1")
    second = draft_publisher.publish(draft, "admin-2")

    assert first["action"] == "created"
    assert second["action"] == "updated"
    assert len(fake.tables["reading_passages"]) == 6  # still 6, not 12
    first_ids = sorted(p["id"] for p in first["passages"])
    second_ids = sorted(p["id"] for p in second["passages"])
    assert first_ids == second_ids


def test_part_b_republish_after_edit_updates_all_six_rows_in_place(monkeypatch):
    fake = _shared_fake(monkeypatch)
    fake.tables["generated_content_drafts"] = [_draft(
        id=70, status="approved", module="reading", generated_content=_part_b_content(),
    )]

    draft = draft_store.get_draft(70)
    first = draft_publisher.publish(draft, "owner-1")
    draft_store.mark_published(70, "owner-1")
    assert len(fake.tables["reading_passages"]) == 6

    edited_passages = _part_b_passages()
    edited_passages[0]["title"] = "Extract 1 (revised)"
    edited_passages[0]["questions"][0]["correct_answer"] = "Option A"
    draft_store.update_content(70, generated_content=_part_b_content(edited_passages), editor_id="analyst-1")
    draft_store.approve(70, "admin-1")

    draft = draft_store.get_draft(70)
    second = draft_publisher.publish(draft, "owner-1")

    assert second["action"] == "updated"
    assert len(fake.tables["reading_passages"]) == 6  # still 6, no duplicates
    row0 = next(r for r in fake.tables["reading_passages"] if r["passage_seq"] == 0)
    assert row0["title"] == "Extract 1 (revised)"
    q0 = next(q for q in fake.tables["questions"] if q["passage_id"] == row0["id"])
    assert q0["correct_answer"] == "Option A"


def test_part_b_publish_failure_partway_leaves_no_partial_passages(monkeypatch):
    """Atomicity per the Phase 4B brief: if any one passage/question in a
    first publish fails, none of that publish's passages survive -- not a
    partial set of 2 or 3 out of 6."""
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    fake.fail_insert_on_call["questions"] = 3  # passages 0,1 succeed; passage 2's question fails
    draft = _draft(id=71, module="reading", generated_content=_part_b_content())

    try:
        draft_publisher.publish(draft, "owner-1")
        assert False, "expected the simulated insert failure to propagate"
    except Exception as e:
        assert "simulated insert failure" in str(e)

    assert len(fake.tables["reading_passages"]) == 0


# ── Part C: 2 independent long-form texts from one draft (Phase 4C-3) ──
# Reuses the exact same multi-passage architecture Part B established --
# reading_passages_source_draft_uidx is (source_draft_id, passage_seq), so
# Part C's 2 rows share one source_draft_id the same way Part B's 6 do.

def _part_c_texts(n=2):
    return [
        {
            "title": f"Feature {i + 1}",
            "body": f"Long-form journalistic body text for feature {i + 1}.",
            "questions": [{
                "type": "mcq",
                "content": f"Feature {i + 1} question {q + 1}?",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "correct_answer": "Option B",
            } for q in range(8)],
        }
        for i in range(n)
    ]


def _part_c_content(texts=None):
    return {"part": "C", "texts": _part_c_texts() if texts is None else texts}


def test_part_c_payloads_builds_two_passages_with_seq_and_content_preserved():
    draft = _draft(id=80, module="reading", generated_content=_part_c_content())
    payloads = draft_publisher._reading_part_c_payloads(draft)
    assert len(payloads) == 2
    for i, (passage, questions) in enumerate(payloads):
        assert passage["part"] == "C"
        assert passage["passage_seq"] == i
        assert passage["title"] == f"Feature {i + 1}"
        assert passage["body"] == f"Long-form journalistic body text for feature {i + 1}."
        assert passage["source_draft_id"] == 80
        assert passage["is_active"] is False
        assert len(questions) == 8
        assert questions[0]["options"] == ["Option A", "Option B", "Option C", "Option D"]
        assert questions[0]["correct_answer"] == "Option B"


def test_part_c_payloads_rejects_wrong_text_count():
    draft = _draft(module="reading", generated_content=_part_c_content(_part_c_texts(1)))
    try:
        draft_publisher._reading_part_c_payloads(draft)
        assert False, "expected InvalidPartError"
    except draft_publisher.InvalidPartError:
        pass


def test_part_c_publish_creates_exactly_two_passages_all_part_c(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=81, module="reading", generated_content=_part_c_content())

    result = draft_publisher.publish(draft, "owner-1")

    rows = fake.tables["reading_passages"]
    assert len(rows) == 2
    assert {r["part"] for r in rows} == {"C"}
    assert sorted(r["passage_seq"] for r in rows) == [0, 1]
    assert result["table"] == "reading_passages"
    assert result["action"] == "created"
    assert len(result["passages"]) == 2


def test_part_c_publish_each_passage_has_exactly_eight_questions_with_four_options(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=82, module="reading", generated_content=_part_c_content())
    draft_publisher.publish(draft, "owner-1")

    for passage in fake.tables["reading_passages"]:
        qs = [q for q in fake.tables["questions"] if q.get("passage_id") == passage["id"]]
        assert len(qs) == 8
        for q in qs:
            assert len(json.loads(q["options"])) == 4


def test_part_c_publish_correct_answers_survive_unchanged(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    texts = _part_c_texts()
    texts[1]["questions"][3]["correct_answer"] = "Option D"
    draft = _draft(id=83, module="reading", generated_content=_part_c_content(texts))
    draft_publisher.publish(draft, "owner-1")

    by_seq = {r["passage_seq"]: r["id"] for r in fake.tables["reading_passages"]}
    q = next(q for q in fake.tables["questions"] if q["passage_id"] == by_seq[1] and q["content"] == "Feature 2 question 4?")
    assert q["correct_answer"] == "Option D"


def test_part_c_publish_all_two_share_same_source_draft_id(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=84, module="reading", generated_content=_part_c_content())
    draft_publisher.publish(draft, "owner-1")

    assert all(r["source_draft_id"] == 84 for r in fake.tables["reading_passages"])


def test_part_c_publish_preview_returns_both_passages(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=85, module="reading", generated_content=_part_c_content())

    preview = draft_publisher.build_preview(draft)

    passage_records = [r for r in preview["records"] if r["table"] == "reading_passages"]
    assert len(passage_records) == 2
    assert all(r["fields"]["part"] == "C" for r in passage_records)
    assert all(r["action"] == "create" for r in passage_records)
    assert sorted(r["fields"]["passage_seq"] for r in passage_records) == [0, 1]
    assert len(fake.tables["reading_passages"]) == 0  # preview writes nothing


def test_part_c_republish_of_unchanged_draft_updates_not_duplicates(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=86, module="reading", generated_content=_part_c_content())

    first = draft_publisher.publish(draft, "admin-1")
    second = draft_publisher.publish(draft, "admin-2")

    assert first["action"] == "created"
    assert second["action"] == "updated"
    assert len(fake.tables["reading_passages"]) == 2  # still 2, not 4
    first_ids = sorted(p["id"] for p in first["passages"])
    second_ids = sorted(p["id"] for p in second["passages"])
    assert first_ids == second_ids


def test_part_c_republish_after_edit_updates_both_rows_in_place(monkeypatch):
    fake = _shared_fake(monkeypatch)
    fake.tables["generated_content_drafts"] = [_draft(
        id=87, status="approved", module="reading", generated_content=_part_c_content(),
    )]

    draft = draft_store.get_draft(87)
    draft_publisher.publish(draft, "owner-1")
    draft_store.mark_published(87, "owner-1")
    assert len(fake.tables["reading_passages"]) == 2

    edited_texts = _part_c_texts()
    edited_texts[0]["title"] = "Feature 1 (revised)"
    edited_texts[0]["questions"][0]["correct_answer"] = "Option A"
    draft_store.update_content(87, generated_content=_part_c_content(edited_texts), editor_id="analyst-1")
    draft_store.approve(87, "admin-1")

    draft = draft_store.get_draft(87)
    second = draft_publisher.publish(draft, "owner-1")

    assert second["action"] == "updated"
    assert len(fake.tables["reading_passages"]) == 2  # still 2, no duplicates
    row0 = next(r for r in fake.tables["reading_passages"] if r["passage_seq"] == 0)
    assert row0["title"] == "Feature 1 (revised)"
    q0 = next(q for q in fake.tables["questions"] if q["passage_id"] == row0["id"] and q["content"] == "Feature 1 question 1?")
    assert q0["correct_answer"] == "Option A"


def test_part_c_publish_failure_partway_leaves_no_partial_passages(monkeypatch):
    """If the second passage's questions fail to insert, the first passage
    (already inserted this call) must be rolled back too -- a failed Publish
    never leaves 1 of 2 Part C passages behind."""
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    fake.fail_insert_on_call["questions"] = 9  # passage 0's 8 questions succeed; passage 1's 1st question fails
    draft = _draft(id=88, module="reading", generated_content=_part_c_content())

    try:
        draft_publisher.publish(draft, "owner-1")
        assert False, "expected the simulated insert failure to propagate"
    except Exception as e:
        assert "simulated insert failure" in str(e)

    assert len(fake.tables["reading_passages"]) == 0


def test_part_c_unpublish_deactivates_both_passages(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=89, module="reading", generated_content=_part_c_content())
    draft_publisher.publish(draft, "owner-1")

    result = draft_publisher.unpublish(draft)

    assert result["table"] == "reading_passages"
    assert len(result["ids"]) == 2
    assert all(r["is_active"] is False for r in fake.tables["reading_passages"])


def test_part_a_publish_unaffected_by_part_c(monkeypatch):
    """Part A is untouched by the Part C changes -- still one row, one draft."""
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=90, module="reading", generated_content={
        "title": "Part A passage", "part": "A", "body": "text", "questions": [],
    })
    result = draft_publisher.publish(draft, "owner-1")
    assert len(fake.tables["reading_passages"]) == 1
    assert result["action"] == "created"


def test_part_b_publish_unaffected_by_part_c(monkeypatch):
    """Part B is untouched by the Part C changes -- still 6 rows, one draft."""
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=91, module="reading", generated_content=_part_b_content())
    result = draft_publisher.publish(draft, "owner-1")
    assert len(fake.tables["reading_passages"]) == 6
    assert result["action"] == "created"


# ── Listening Content Studio Phase 3C: multi-section publish ───────────
# Locked contract (Phase 3, mirrors Reading Part B/C's multi-passage
# architecture over listening_sections instead of reading_passages):
# Part A -> 2 sections, Part B -> 6, Part C -> 2. section_seq (0..N-1) is
# what lets them share one source_draft_id under the widened
# listening_sections_source_draft_uidx (Phase 3F migration).
#
# Phase 7E: publish now hard-blocks any of these parts if an extract's audio
# is missing/stale (draft_publisher._check_listening_audio_gate), so every
# extract fixture below carries ready audio (url + matching transcript hash)
# by default -- otherwise every publish()/build_preview() call in this
# section would raise AudioNotReadyError before reaching what it's actually
# testing. See test_content_studio_audio.py's PublishAudioGateTests for the
# gate's own dedicated coverage (missing/partial/outdated/all-ready).

def _ready_audio(transcript, tag):
    return {"audio_url": f"https://cdn/{tag}.mp3", "audio_transcript_hash": listening_audio.transcript_hash(transcript)}


def _listening_part_a_extracts(n=2):
    out = []
    for i in range(n):
        transcript = [{"speaker": "Nurse", "text": f"extract {i + 1} turn"}]
        out.append({
            "title": f"Extract {i + 1}",
            "transcript": transcript,
            "body": f"Extract {i + 1} notes\n1. blank ______",
            "questions": [{
                "type": "short_answer", "content": f"Extract {i + 1} blank ({b})",
                "options": [], "correct_answer": f"answer {i + 1}-{b}",
            } for b in range(1, 13)],
            **_ready_audio(transcript, f"part-a-{i}"),
        })
    return out


def _listening_part_a_content(extracts=None):
    return {"part": "A", "prep_seconds": 30, "audio_mode": "dialogue", "extracts": _listening_part_a_extracts() if extracts is None else extracts}


def _listening_part_b_extracts(n=6):
    out = []
    for i in range(n):
        transcript = [{"speaker": "Nurse", "text": f"extract {i + 1} turn"}]
        out.append({
            "title": f"Extract {i + 1}",
            "transcript": transcript,
            "questions": [{
                "type": "mcq", "content": f"What does extract {i + 1} say?",
                "options": ["Option A", "Option B", "Option C"], "correct_answer": "Option B",
            }],
            **_ready_audio(transcript, f"part-b-{i}"),
        })
    return out


def _listening_part_b_content(extracts=None):
    return {"part": "B", "prep_seconds": 15, "audio_mode": "dialogue", "extracts": _listening_part_b_extracts() if extracts is None else extracts}


def _listening_part_c_extracts(n=2):
    out = []
    for i in range(n):
        transcript = [{"speaker": "Interviewer", "text": f"extract {i + 1} turn"}]
        out.append({
            "title": f"Extract {i + 1}",
            "audio_mode": "dialogue" if i % 2 == 0 else "monologue",
            "transcript": transcript,
            "questions": [{
                "type": "mcq", "content": f"Extract {i + 1} question {q}",
                "options": ["Option A", "Option B", "Option C"], "correct_answer": "Option B",
            } for q in range(1, 7)],
            **_ready_audio(transcript, f"part-c-{i}"),
        })
    return out


def _listening_part_c_content(extracts=None):
    return {"part": "C", "prep_seconds": 90, "extracts": _listening_part_c_extracts() if extracts is None else extracts}


def test_listening_part_a_payloads_builds_two_sections_with_seq_and_fields_preserved():
    draft = _draft(id=200, module="listening", generated_content=_listening_part_a_content())
    payloads = draft_publisher._listening_part_a_payloads(draft)
    assert len(payloads) == 2
    for i, (section, questions) in enumerate(payloads):
        assert section["part"] == "A"
        assert section["section_seq"] == i
        assert section["prep_seconds"] == 30
        assert section["audio_mode"] == "dialogue"
        assert section["body"] == f"Extract {i + 1} notes\n1. blank ______"
        assert section["transcript"] == [{"speaker": "Nurse", "text": f"extract {i + 1} turn"}]
        assert len(questions) == 12


def test_listening_part_b_payloads_builds_six_sections_with_seq_and_fields_preserved():
    draft = _draft(id=201, module="listening", generated_content=_listening_part_b_content())
    payloads = draft_publisher._listening_part_b_payloads(draft)
    assert len(payloads) == 6
    for i, (section, questions) in enumerate(payloads):
        assert section["part"] == "B"
        assert section["section_seq"] == i
        assert section["prep_seconds"] == 15
        assert section["audio_mode"] == "dialogue"
        assert section["body"] is None
        assert len(questions) == 1


def test_listening_part_c_payloads_preserve_per_extract_audio_mode():
    draft = _draft(id=202, module="listening", generated_content=_listening_part_c_content())
    payloads = draft_publisher._listening_part_c_payloads(draft)
    assert len(payloads) == 2
    assert payloads[0][0]["audio_mode"] == "dialogue"
    assert payloads[1][0]["audio_mode"] == "monologue"
    assert all(len(q) == 6 for _, q in payloads)


def test_listening_part_b_payloads_rejects_wrong_extract_count():
    draft = _draft(module="listening", generated_content=_listening_part_b_content(_listening_part_b_extracts(5)))
    try:
        draft_publisher._listening_part_b_payloads(draft)
        assert False, "expected InvalidPartError"
    except draft_publisher.InvalidPartError:
        pass


def test_listening_part_b_publish_creates_exactly_six_sections_all_part_b(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=203, module="listening", generated_content=_listening_part_b_content())
    result = draft_publisher.publish(draft, "owner-1")
    rows = fake.tables["listening_sections"]
    assert len(rows) == 6
    assert all(r["part"] == "B" for r in rows)
    assert sorted(r["section_seq"] for r in rows) == [0, 1, 2, 3, 4, 5]
    assert result["action"] == "created"
    assert result["questions_created"] == 6


def test_listening_part_b_publish_questions_linked_to_their_own_section_only(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=204, module="listening", generated_content=_listening_part_b_content())
    draft_publisher.publish(draft, "owner-1")
    rows_by_seq = {r["section_seq"]: r for r in fake.tables["listening_sections"]}
    for seq, section in rows_by_seq.items():
        qs = [q for q in fake.tables["questions"] if q["section_id"] == section["id"]]
        assert len(qs) == 1
        assert qs[0]["content"] == f"What does extract {seq + 1} say?"


def test_listening_part_b_publish_all_six_share_same_source_draft_id(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=205, module="listening", generated_content=_listening_part_b_content())
    draft_publisher.publish(draft, "owner-1")
    assert all(r["source_draft_id"] == 205 for r in fake.tables["listening_sections"])


def test_listening_part_b_publish_preview_returns_all_six_sections(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=206, module="listening", generated_content=_listening_part_b_content())
    preview = draft_publisher.build_preview(draft)
    section_records = [r for r in preview["records"] if r["table"] == "listening_sections"]
    assert len(section_records) == 6
    assert all(r["action"] == "create" for r in section_records)
    assert sorted(r["fields"]["section_seq"] for r in section_records) == [0, 1, 2, 3, 4, 5]


def test_listening_part_b_republish_of_unchanged_draft_updates_not_duplicates(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=207, module="listening", generated_content=_listening_part_b_content())
    first = draft_publisher.publish(draft, "owner-1")
    second = draft_publisher.publish(draft, "owner-2")
    assert first["action"] == "created"
    assert second["action"] == "updated"
    assert len(fake.tables["listening_sections"]) == 6


def test_listening_part_b_republish_after_edit_updates_all_six_rows_in_place(monkeypatch):
    fake = _shared_fake(monkeypatch)
    fake.tables["generated_content_drafts"] = [_draft(
        id=208, status="approved", module="listening", generated_content=_listening_part_b_content(),
    )]

    draft = draft_store.get_draft(208)
    draft_publisher.publish(draft, "owner-1")
    draft_store.mark_published(208, "owner-1")

    edited_extracts = _listening_part_b_extracts()
    edited_extracts[0]["title"] = "Edited title"
    draft_store.update_content(208, generated_content=_listening_part_b_content(edited_extracts), editor_id="analyst-1")
    draft_store.approve(208, "admin-1")
    draft = draft_store.get_draft(208)
    second = draft_publisher.publish(draft, "owner-1")

    assert second["action"] == "updated"
    assert len(fake.tables["listening_sections"]) == 6
    row0 = next(r for r in fake.tables["listening_sections"] if r["section_seq"] == 0)
    assert row0["title"] == "Edited title"


def test_listening_part_b_publish_failure_partway_leaves_no_partial_sections(monkeypatch):
    """Atomicity, same as Reading Part B's equivalent test: if any one
    section/question in a first publish fails, none of that publish's
    sections survive -- not a partial set of 2 or 3 out of 6."""
    fake = FakeSupabase()
    fake.fail_insert_on_call["questions"] = 3  # sections 0,1 succeed; section 2's question fails
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=209, module="listening", generated_content=_listening_part_b_content())
    try:
        draft_publisher.publish(draft, "owner-1")
        assert False, "expected the simulated insert failure to propagate"
    except Exception as e:
        assert "simulated insert failure" in str(e)
    assert fake.tables["listening_sections"] == []


def test_listening_part_a_unpublish_deactivates_both_sections(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=210, module="listening", generated_content=_listening_part_a_content())
    draft_publisher.publish(draft, "owner-1")
    for r in fake.tables["listening_sections"]:
        r["is_active"] = True

    result = draft_publisher.unpublish(draft)
    assert len(result["ids"]) == 2
    assert all(r["is_active"] is False for r in fake.tables["listening_sections"])


def test_listening_part_a_publish_unaffected_by_part_b(monkeypatch):
    """Part A (2 sections) and Part B (6 sections) publish independently --
    same non-interference guarantee Reading Part A/B/C already have."""
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft_a = _draft(id=211, module="listening", generated_content=_listening_part_a_content())
    draft_b = _draft(id=212, module="listening", generated_content=_listening_part_b_content())
    draft_publisher.publish(draft_a, "owner-1")
    draft_publisher.publish(draft_b, "owner-1")
    assert len(fake.tables["listening_sections"]) == 8
    assert sorted(r["section_seq"] for r in fake.tables["listening_sections"] if r["source_draft_id"] == 211) == [0, 1]
    assert sorted(r["section_seq"] for r in fake.tables["listening_sections"] if r["source_draft_id"] == 212) == [0, 1, 2, 3, 4, 5]


def test_legacy_flat_listening_still_publishes_one_row_unaffected_by_part_studio(monkeypatch):
    """Existing direct/flat Listening generation (no locked part contract) is
    untouched -- still exactly one row, section_seq defaults to 0."""
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=213, module="listening", generated_content={
        "title": "Legacy section", "transcript": [{"speaker": "Nurse", "text": "hi"}], "questions": [],
    })
    result = draft_publisher.publish(draft, "owner-1")
    assert result["action"] == "created"
    assert len(fake.tables["listening_sections"]) == 1
    assert fake.tables["listening_sections"][0].get("section_seq", 0) == 0


# ── Phase 6A: audio_url must survive a republish without new audio ─────
# Audio is attached to the production row directly (listening.py's
# upload/TTS endpoints), never through generated_content -- so a republish's
# payload previously hardcoded audio_url=None and nulled out whatever an
# admin had already attached. See draft_publisher._set_audio_url.

def test_legacy_listening_republish_without_audio_preserves_existing_audio_url(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=300, module="listening", generated_content={
        "title": "Legacy section", "transcript": [{"speaker": "Nurse", "text": "hi"}], "questions": [],
    })
    draft_publisher.publish(draft, "owner-1")
    fake.tables["listening_sections"][0]["audio_url"] = "https://bucket/a.mp3"

    result = draft_publisher.publish(draft, "owner-1")

    assert result["action"] == "updated"
    assert fake.tables["listening_sections"][0]["audio_url"] == "https://bucket/a.mp3"


def test_legacy_listening_republish_with_explicit_audio_url_replaces_it(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=301, module="listening", generated_content={
        "title": "Legacy section", "transcript": [{"speaker": "Nurse", "text": "hi"}], "questions": [],
    })
    draft_publisher.publish(draft, "owner-1")
    fake.tables["listening_sections"][0]["audio_url"] = "https://bucket/old.mp3"

    draft["generated_content"] = {**draft["generated_content"], "audio_url": "https://bucket/new.mp3"}
    result = draft_publisher.publish(draft, "owner-1")

    assert result["action"] == "updated"
    assert fake.tables["listening_sections"][0]["audio_url"] == "https://bucket/new.mp3"


def test_legacy_listening_first_publish_leaves_audio_url_null(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=302, module="listening", generated_content={
        "title": "New section", "transcript": [], "questions": [],
    })
    draft_publisher.publish(draft, "owner-1")
    assert fake.tables["listening_sections"][0].get("audio_url") is None


def test_listening_part_a_republish_keeps_each_sections_audio_synced_to_its_own_extract(monkeypatch):
    """Phase 7E: the audio gate requires every extract to carry ready audio
    before publish succeeds at all, so a section's audio_url is now always
    sourced from (and stays synced to) its own extract on every publish --
    superseding the pre-7E contract where a production row's independently-
    attached audio_url survived a republish untouched (that contract still
    holds for legacy flat listening -- see
    test_legacy_listening_republish_without_audio_preserves_existing_audio_url)."""
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=303, module="listening", generated_content=_listening_part_a_content())
    draft_publisher.publish(draft, "owner-1")

    result = draft_publisher.publish(draft, "owner-1")

    assert result["sections"][0]["action"] == "updated"
    rows_by_seq = {r["section_seq"]: r for r in fake.tables["listening_sections"]}
    assert rows_by_seq[0]["audio_url"] == "https://cdn/part-a-0.mp3"
    assert rows_by_seq[1]["audio_url"] == "https://cdn/part-a-1.mp3"


def test_listening_part_b_republish_keeps_each_sections_audio_synced_to_its_own_extract(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=304, module="listening", generated_content=_listening_part_b_content())
    draft_publisher.publish(draft, "owner-1")

    result = draft_publisher.publish(draft, "owner-1")

    assert result["sections"][0]["action"] == "updated"
    rows_by_seq = {r["section_seq"]: r for r in fake.tables["listening_sections"]}
    for seq in range(6):
        assert rows_by_seq[seq]["audio_url"] == f"https://cdn/part-b-{seq}.mp3"


def test_listening_part_c_republish_keeps_each_sections_audio_synced_to_its_own_extract(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=305, module="listening", generated_content=_listening_part_c_content())
    draft_publisher.publish(draft, "owner-1")

    result = draft_publisher.publish(draft, "owner-1")

    assert result["sections"][0]["action"] == "updated"
    rows_by_seq = {r["section_seq"]: r for r in fake.tables["listening_sections"]}
    assert rows_by_seq[0]["audio_url"] == "https://cdn/part-c-0.mp3"
    assert rows_by_seq[1]["audio_url"] == "https://cdn/part-c-1.mp3"


def test_listening_part_b_republish_one_extract_regenerated_others_unaffected(monkeypatch):
    """Each section's audio is decided independently: regenerating (or
    editing) one extract's audio must not touch the others' -- same
    isolation guarantee as generate_draft_audio's own sibling-preservation
    tests (test_content_studio_audio.py), now proven through a full
    publish/republish cycle instead of just the draft-side update."""
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=306, module="listening", generated_content=_listening_part_b_content())
    draft_publisher.publish(draft, "owner-1")

    edited_extracts = _listening_part_b_extracts()
    edited_extracts[2]["audio_url"] = "https://cdn/part-b-2-regenerated.mp3"
    draft["generated_content"] = _listening_part_b_content(edited_extracts)
    draft_publisher.publish(draft, "owner-1")

    rows_by_seq = {r["section_seq"]: r for r in fake.tables["listening_sections"]}
    assert rows_by_seq[2]["audio_url"] == "https://cdn/part-b-2-regenerated.mp3"
    for seq in (0, 1, 3, 4, 5):
        assert rows_by_seq[seq]["audio_url"] == f"https://cdn/part-b-{seq}.mp3"


def test_listening_part_b_first_publish_stamps_each_sections_own_audio_url(monkeypatch):
    """Phase 7E: first publish of an audio-ready Part B draft carries each
    extract's own audio straight onto its row (not null -- publishing
    without audio at all is now blocked by the gate, see
    test_content_studio_audio.py's PublishAudioGateTests)."""
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=307, module="listening", generated_content=_listening_part_b_content())
    draft_publisher.publish(draft, "owner-1")
    rows_by_seq = {r["section_seq"]: r for r in fake.tables["listening_sections"]}
    for seq in range(6):
        assert rows_by_seq[seq]["audio_url"] == f"https://cdn/part-b-{seq}.mp3"
    assert len(fake.tables["listening_sections"]) == 6  # no duplicate rows from the republish-audio path


def test_reading_republish_unaffected_by_listening_audio_url_fix(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(id=308, module="reading", generated_content={
        "title": "A passage", "part": "A", "body": "text", "questions": [],
    })
    first = draft_publisher.publish(draft, "owner-1")
    second = draft_publisher.publish(draft, "owner-1")
    assert first["action"] == "created"
    assert second["action"] == "updated"
    assert len(fake.tables["reading_passages"]) == 1


# ── Blog draft fields (Module 1 Section 7A) ─────────────────────────────
# slug/excerpt/cover_image_ref live as first-class columns (not buried in
# generated_content jsonb) so the review workflow's revision snapshots can
# see them change. draft_store never enforces slug uniqueness itself -- the
# DB partial unique index (generated_content_drafts_blog_slug_uidx,
# 20260819010000_blog_draft_fields.sql) is the authoritative guard; these
# tests only prove create_draft()/update_content() plumb the fields through
# and that draft_publisher still refuses to publish 'blog' (no dispatch
# branch added for it -- see draft_publisher.publish's NotPublishableError).

def test_create_draft_blog_with_all_fields_persists(monkeypatch):
    fake = _patched(monkeypatch, [])
    created = draft_store.create_draft(
        module="blog", draft_name="My Post", ai_title=None, metadata={}, prompt={},
        generated_content={"title": "Hello", "body": "World"}, validation_warnings=[],
        model_used=None, created_by="admin-1",
        slug="oet-speaking-guide", excerpt="A short teaser.", cover_image_ref="image-abc123-800x600-jpg",
    )
    assert created["module"] == "blog"
    assert created["slug"] == "oet-speaking-guide"
    assert created["excerpt"] == "A short teaser."
    assert created["cover_image_ref"] == "image-abc123-800x600-jpg"
    assert created["generated_content"] == {"title": "Hello", "body": "World"}
    assert fake.tables["generated_content_drafts"][0]["slug"] == "oet-speaking-guide"


def test_create_draft_blog_with_fields_omitted_stays_null(monkeypatch):
    fake = _patched(monkeypatch, [])
    created = draft_store.create_draft(
        module="blog", draft_name="No extras yet", ai_title=None, metadata={}, prompt={},
        generated_content={"title": "Hello"}, validation_warnings=[],
        model_used=None, created_by="admin-1",
    )
    assert created["slug"] is None
    assert created["excerpt"] is None
    assert created["cover_image_ref"] is None


def test_create_draft_non_blog_unaffected_by_new_optional_fields(monkeypatch):
    """Existing modules must keep working -- and keep returning NULL for the
    new columns -- without passing slug/excerpt/cover_image_ref at all."""
    fake = _patched(monkeypatch, [])
    created = draft_store.create_draft(
        module="speaking", draft_name="A scenario", ai_title=None, metadata={}, prompt={},
        generated_content={"title": "S1"}, validation_warnings=[],
        model_used=None, created_by="admin-1",
    )
    assert created["module"] == "speaking"
    assert created["slug"] is None
    assert created["excerpt"] is None
    assert created["cover_image_ref"] is None


def test_blog_publish_still_blocked_not_publishable(monkeypatch):
    """Blog drafts can now exist, but draft_publisher has no dispatch branch
    for 'blog' -- Section 7A must not make it publishable."""
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    draft = _draft(module="blog", status="approved", generated_content={"title": "t", "body": "b"},
                    slug="oet-speaking-guide")
    try:
        draft_publisher.publish(draft, "owner-1")
        assert False, "expected NotPublishableError"
    except draft_publisher.NotPublishableError:
        pass


# ── revision snapshots: slug / excerpt / cover_image_ref ────────────────

def test_slug_change_creates_revision_snapshot(monkeypatch):
    rows = [_draft(module="blog", status="draft", slug=None, excerpt=None, cover_image_ref=None)]
    fake = _patched(monkeypatch, rows)
    updated = draft_store.update_content(1, slug="oet-speaking-guide", editor_id="a1")
    assert updated["slug"] == "oet-speaking-guide"
    revisions = fake.tables["generated_content_draft_revisions"]
    assert len(revisions) == 1
    assert revisions[0]["before"]["slug"] is None
    assert revisions[0]["after"]["slug"] == "oet-speaking-guide"


def test_excerpt_change_creates_revision_snapshot(monkeypatch):
    rows = [_draft(module="blog", status="draft", slug=None, excerpt=None, cover_image_ref=None)]
    fake = _patched(monkeypatch, rows)
    updated = draft_store.update_content(1, excerpt="A short teaser.", editor_id="a1")
    assert updated["excerpt"] == "A short teaser."
    revisions = fake.tables["generated_content_draft_revisions"]
    assert len(revisions) == 1
    assert revisions[0]["before"]["excerpt"] is None
    assert revisions[0]["after"]["excerpt"] == "A short teaser."


def test_cover_image_ref_change_creates_revision_snapshot(monkeypatch):
    rows = [_draft(module="blog", status="draft", slug=None, excerpt=None, cover_image_ref=None)]
    fake = _patched(monkeypatch, rows)
    updated = draft_store.update_content(1, cover_image_ref="image-abc123-800x600-jpg", editor_id="a1")
    assert updated["cover_image_ref"] == "image-abc123-800x600-jpg"
    revisions = fake.tables["generated_content_draft_revisions"]
    assert len(revisions) == 1
    assert revisions[0]["before"]["cover_image_ref"] is None
    assert revisions[0]["after"]["cover_image_ref"] == "image-abc123-800x600-jpg"


# ── cover_image_ref clear sentinel (Module 1 Section 11 Step 15) ────────

def test_cover_image_ref_empty_string_clears_to_null(monkeypatch):
    rows = [_draft(module="blog", status="draft", cover_image_ref="image-abc123-800x600-jpg")]
    _patched(monkeypatch, rows)
    updated = draft_store.update_content(1, cover_image_ref="", editor_id="a1")
    assert updated["cover_image_ref"] is None


def test_cover_image_ref_clear_creates_revision_snapshot(monkeypatch):
    rows = [_draft(module="blog", status="draft", cover_image_ref="image-abc123-800x600-jpg")]
    fake = _patched(monkeypatch, rows)
    draft_store.update_content(1, cover_image_ref="", editor_id="a1")
    revisions = fake.tables["generated_content_draft_revisions"]
    assert len(revisions) == 1
    assert revisions[0]["before"]["cover_image_ref"] == "image-abc123-800x600-jpg"
    assert revisions[0]["after"]["cover_image_ref"] is None


def test_cover_image_ref_clear_on_already_null_is_noop(monkeypatch):
    """"" normalizes to None -- clearing an already-empty cover_image_ref must
    not write a field, a revision, or bump updated_at (matches the existing
    "only when content actually changed" rule the other Blog fields follow)."""
    rows = [_draft(module="blog", status="draft", cover_image_ref=None)]
    fake = _patched(monkeypatch, rows)
    updated = draft_store.update_content(1, cover_image_ref="", editor_id="a1")
    assert updated["cover_image_ref"] is None
    assert fake.tables.get("generated_content_draft_revisions", []) == []


def test_generated_content_change_still_creates_revision_after_blog_fields_added(monkeypatch):
    rows = [_draft(module="blog", status="draft", generated_content={"title": "v1"})]
    fake = _patched(monkeypatch, rows)
    draft_store.update_content(1, generated_content={"title": "v2"}, editor_id="a1")
    revisions = fake.tables["generated_content_draft_revisions"]
    assert len(revisions) == 1
    assert revisions[0]["after"]["generated_content"] == {"title": "v2"}


def test_metadata_change_still_creates_revision_after_blog_fields_added(monkeypatch):
    rows = [_draft(module="blog", status="draft", metadata={"a": 1})]
    fake = _patched(monkeypatch, rows)
    draft_store.update_content(1, metadata={"a": 2}, editor_id="a1")
    revisions = fake.tables["generated_content_draft_revisions"]
    assert len(revisions) == 1
    assert revisions[0]["after"]["metadata"] == {"a": 2}


def test_multiple_blog_fields_changed_together_produce_one_coherent_revision(monkeypatch):
    rows = [_draft(module="blog", status="draft", slug="old-slug", excerpt="old excerpt",
                    cover_image_ref=None, generated_content={"title": "v1"})]
    fake = _patched(monkeypatch, rows)
    updated = draft_store.update_content(
        1, generated_content={"title": "v2"}, slug="new-slug", excerpt="new excerpt",
        cover_image_ref="image-abc123-800x600-jpg", editor_id="a1",
    )
    revisions = fake.tables["generated_content_draft_revisions"]
    assert len(revisions) == 1  # one coherent snapshot, not one per field
    before, after = revisions[0]["before"], revisions[0]["after"]
    assert before["slug"] == "old-slug" and after["slug"] == "new-slug"
    assert before["excerpt"] == "old excerpt" and after["excerpt"] == "new excerpt"
    assert before["cover_image_ref"] is None and after["cover_image_ref"] == "image-abc123-800x600-jpg"
    assert before["generated_content"] == {"title": "v1"} and after["generated_content"] == {"title": "v2"}
    assert updated["slug"] == "new-slug"
    assert updated["excerpt"] == "new excerpt"
    assert updated["cover_image_ref"] == "image-abc123-800x600-jpg"


def test_existing_revision_without_new_keys_remains_readable(monkeypatch):
    """A revision written before this section shipped has only
    generated_content/metadata in before/after -- list_revisions must still
    return it as-is, not raise or backfill missing keys."""
    fake = FakeSupabase()
    fake.tables["generated_content_draft_revisions"] = [{
        "id": 1, "draft_id": 5,
        "before": {"generated_content": {"title": "old"}, "metadata": {}},
        "after": {"generated_content": {"title": "new"}, "metadata": {}},
        "editor": "a1", "created_at": "2026-08-01T00:00:00Z",
    }]
    monkeypatch.setattr(draft_store, "get_supabase", lambda: fake)
    revisions = draft_store.list_revisions(5)
    assert len(revisions) == 1
    assert "slug" not in revisions[0]["after"]
    assert revisions[0]["after"]["generated_content"] == {"title": "new"}


def test_non_blog_module_revision_behavior_unchanged(monkeypatch):
    """Speaking/writing/etc. drafts never set slug/excerpt/cover_image_ref --
    a content-only edit still produces exactly the same revision shape."""
    rows = [_draft(module="writing", status="draft", generated_content={"title": "v1"})]
    fake = _patched(monkeypatch, rows)
    draft_store.update_content(1, generated_content={"title": "v2"}, editor_id="a1")
    revisions = fake.tables["generated_content_draft_revisions"]
    assert len(revisions) == 1
    assert revisions[0]["before"]["slug"] is None
    assert revisions[0]["after"]["slug"] is None


# ── slug uniqueness (DB partial unique index) ────────────────────────────
# generated_content_drafts_blog_slug_uidx is verified directly against
# Postgres (QA project) as part of this task's DB verification step --
# these two tests only prove create_draft() doesn't swallow the DB's error,
# and that it doesn't invent an application-level uniqueness check of its
# own (a second blog draft with a distinct slug, or two with slug=None,
# must both succeed with no special-casing).

class _SlugUniqueFakeQuery(FakeQuery):
    def execute(self):
        if self._op == "insert" and self._table_name == "generated_content_drafts":
            slug = self._payload.get("slug")
            module = self._payload.get("module")
            if module == "blog" and slug is not None:
                conflict = any(
                    r.get("module") == "blog" and r.get("slug") == slug for r in self._rows
                )
                if conflict:
                    raise Exception(
                        'duplicate key value violates unique constraint "generated_content_drafts_blog_slug_uidx"'
                    )
        return super().execute()


class _SlugUniqueFakeSupabase(FakeSupabase):
    def table(self, name):
        self.tables.setdefault(name, [])
        return _SlugUniqueFakeQuery(self.tables[name], table_name=name, supabase=self)


def test_duplicate_blog_slug_rejected_by_db_constraint_simulation(monkeypatch):
    """Module 1 Section 15G: create_draft() translates the raw DB unique-
    violation into DuplicateSlugError -- no duplicate row is created (only
    the first insert lands in the fake table), and the raw Postgres
    constraint text does not reach the caller."""
    fake = _SlugUniqueFakeSupabase()
    monkeypatch.setattr(draft_store, "get_supabase", lambda: fake)
    draft_store.create_draft(
        module="blog", draft_name="A", ai_title=None, metadata={}, prompt={},
        generated_content={"title": "A"}, validation_warnings=[], model_used=None,
        created_by="admin-1", slug="oet-speaking-guide",
    )
    try:
        draft_store.create_draft(
            module="blog", draft_name="B", ai_title=None, metadata={}, prompt={},
            generated_content={"title": "B"}, validation_warnings=[], model_used=None,
            created_by="admin-1", slug="oet-speaking-guide",
        )
        assert False, "expected DuplicateSlugError to be raised"
    except draft_store.DuplicateSlugError as e:
        message = str(e)
        assert "oet-speaking-guide" in message
        assert "already in use" in message
        # no raw DB/constraint/SQL detail leaks into the application-level message
        assert "constraint" not in message.lower()
        assert "postgres" not in message.lower()
        assert "generated_content_drafts_blog_slug_uidx" not in message
    assert len(fake.tables["generated_content_drafts"]) == 1


def test_duplicate_blog_slug_does_not_create_duplicate_row(monkeypatch):
    fake = _SlugUniqueFakeSupabase()
    monkeypatch.setattr(draft_store, "get_supabase", lambda: fake)
    draft_store.create_draft(
        module="blog", draft_name="A", ai_title=None, metadata={}, prompt={},
        generated_content={"title": "A"}, validation_warnings=[], model_used=None,
        created_by="admin-1", slug="dup-slug",
    )
    try:
        draft_store.create_draft(
            module="blog", draft_name="B", ai_title=None, metadata={}, prompt={},
            generated_content={"title": "B"}, validation_warnings=[], model_used=None,
            created_by="admin-1", slug="dup-slug",
        )
    except draft_store.DuplicateSlugError:
        pass
    rows = fake.tables["generated_content_drafts"]
    assert len(rows) == 1
    assert rows[0]["draft_name"] == "A"


def test_distinct_blog_slug_still_succeeds(monkeypatch):
    fake = _SlugUniqueFakeSupabase()
    monkeypatch.setattr(draft_store, "get_supabase", lambda: fake)
    draft_store.create_draft(
        module="blog", draft_name="A", ai_title=None, metadata={}, prompt={},
        generated_content={"title": "A"}, validation_warnings=[], model_used=None,
        created_by="admin-1", slug="slug-one",
    )
    b = draft_store.create_draft(
        module="blog", draft_name="B", ai_title=None, metadata={}, prompt={},
        generated_content={"title": "B"}, validation_warnings=[], model_used=None,
        created_by="admin-1", slug="slug-two",
    )
    assert b["slug"] == "slug-two"
    assert len(fake.tables["generated_content_drafts"]) == 2


def test_same_slug_on_non_blog_module_unaffected(monkeypatch):
    """The unique index is partial (Blog-only) -- a non-Blog module reusing
    the same slug string must not be treated as a conflict."""
    fake = _SlugUniqueFakeSupabase()
    monkeypatch.setattr(draft_store, "get_supabase", lambda: fake)
    draft_store.create_draft(
        module="blog", draft_name="A", ai_title=None, metadata={}, prompt={},
        generated_content={"title": "A"}, validation_warnings=[], model_used=None,
        created_by="admin-1", slug="shared-slug-text",
    )
    other = draft_store.create_draft(
        module="reading", draft_name="B", ai_title=None, metadata={}, prompt={},
        generated_content={"title": "B"}, validation_warnings=[], model_used=None,
        created_by="admin-1", slug="shared-slug-text",
    )
    assert other["slug"] == "shared-slug-text"
    assert len(fake.tables["generated_content_drafts"]) == 2


def test_multiple_blog_drafts_with_null_slug_both_allowed(monkeypatch):
    fake = _SlugUniqueFakeSupabase()
    monkeypatch.setattr(draft_store, "get_supabase", lambda: fake)
    a = draft_store.create_draft(
        module="blog", draft_name="A", ai_title=None, metadata={}, prompt={},
        generated_content={"title": "A"}, validation_warnings=[], model_used=None,
        created_by="admin-1",
    )
    b = draft_store.create_draft(
        module="blog", draft_name="B", ai_title=None, metadata={}, prompt={},
        generated_content={"title": "B"}, validation_warnings=[], model_used=None,
        created_by="admin-1",
    )
    assert a["slug"] is None and b["slug"] is None
    assert len(fake.tables["generated_content_drafts"]) == 2


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
