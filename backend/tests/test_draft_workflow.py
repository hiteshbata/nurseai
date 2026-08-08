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


class _NotProxy:
    """Mirrors supabase-py's query.not_.in_(col, values) -- a NOT IN filter.
    Only .in_ is implemented; nothing else in this codebase uses .not_ yet."""
    def __init__(self, query):
        self._query = query

    def in_(self, col, values):
        self._query._not_in_filters.append((col, set(values)))
        return self._query


class FakeQuery:
    def __init__(self, rows, table_name=None, enforce_source_draft_unique=False, supabase=None):
        self._rows = rows
        self._table_name = table_name
        self._enforce_source_draft_unique = enforce_source_draft_unique
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
            # (20260808050000_draft_review_workflow.sql) -- a partial unique index on
            # source_draft_id, null-safe (legacy rows with no source_draft_id never conflict).
            if self._enforce_source_draft_unique:
                sdid = self._payload.get("source_draft_id")
                if sdid is not None and any(r.get("source_draft_id") == sdid for r in self._rows):
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
    UNIQUE_SOURCE_DRAFT_TABLES = {"reading_passages", "listening_sections"}

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
        "title": "First publish", "part": "B", "body": "text", "questions": [],
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
        "title": "Race condition", "part": "B", "body": "text", "questions": [],
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
        "title": "New passage", "part": "B", "body": "text", "questions": [],
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
            "title": "V1", "part": "B", "body": "first version",
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
        "title": "V2", "part": "B", "body": "corrected version",
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
        "title": "T", "part": "B", "body": "b",
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
        "title": "T", "part": "B", "body": "b",
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
        "title": "T", "part": "B", "body": "b",
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
        "title": "T", "part": "B", "body": "b",
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
