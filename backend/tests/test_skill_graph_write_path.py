"""Covers the QA schema fix: user_skill_stats is uniquely keyed on
(user_id, product, skill_tag), not (user_id, skill_tag). _record_sync must
upsert against that composite key and tag every row "product": "OET", or
every write 400s against QA's real constraint. Fake store below enforces
the composite unique key itself (dict keyed on the 3-tuple) so tests C/D/E
prove insert-vs-update routing without hitting a real database -- Task 5
covers the real-QA verification separately."""
import asyncio

import app.services.skill_graph as skill_graph
from app.services.skill_graph import PRODUCT, _record_sync, record_skill_observations


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, store):
        self.store = store
        self._user_id = None
        self._product = None
        self._in_tags = None
        self._upsert_rows = None

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        if col == "user_id":
            self._user_id = val
        elif col == "product":
            self._product = val
        return self

    def in_(self, col, vals):
        if col == "skill_tag":
            self._in_tags = set(vals)
        return self

    def upsert(self, rows, on_conflict=""):
        self.store.last_upsert_payload = rows
        self.store.last_on_conflict = on_conflict
        self._upsert_rows = rows
        return self

    def execute(self):
        if self._upsert_rows is not None:
            for row in self._upsert_rows:
                key = (row["user_id"], row["product"], row["skill_tag"])
                self.store.rows[key] = dict(row)
            return _FakeResult([dict(r) for r in self._upsert_rows])
        out = []
        for (uid, product, tag), row in self.store.rows.items():
            if self._user_id is not None and uid != self._user_id:
                continue
            if self._product is not None and product != self._product:
                continue
            if self._in_tags is not None and tag not in self._in_tags:
                continue
            out.append(row)
        return _FakeResult(out)


class _FakeStore:
    """In-memory stand-in for the user_skill_stats table, keyed exactly like
    QA's UNIQUE(user_id, product, skill_tag) constraint."""

    def __init__(self):
        self.rows = {}
        self.last_upsert_payload = None
        self.last_on_conflict = None

    def table(self, _name):
        return _FakeQuery(self)


def _patch_supabase(monkeypatch, store):
    monkeypatch.setattr(skill_graph, "get_supabase", lambda: store)


# ── A/B: payload shape ──────────────────────────────────────────────────

def test_upsert_payload_tags_every_row_with_product_oet(monkeypatch):
    store = _FakeStore()
    _patch_supabase(monkeypatch, store)
    _record_sync("user-1", {"reading:B": 4.5})
    assert all(row["product"] == PRODUCT for row in store.last_upsert_payload)


def test_upsert_conflict_target_is_composite_key(monkeypatch):
    store = _FakeStore()
    _patch_supabase(monkeypatch, store)
    _record_sync("user-1", {"reading:B": 4.5})
    assert store.last_on_conflict == "user_id,product,skill_tag"


# ── C/D: insert vs update routing ───────────────────────────────────────

def test_first_record_inserts_one_row(monkeypatch):
    store = _FakeStore()
    _patch_supabase(monkeypatch, store)
    _record_sync("user-1", {"reading:B": 4.5})
    assert len(store.rows) == 1
    row = store.rows[("user-1", "OET", "reading:B")]
    assert row["attempts"] == 1
    assert row["ema_score"] == 4.5


def test_second_record_same_user_product_skill_updates_not_duplicates(monkeypatch):
    store = _FakeStore()
    _patch_supabase(monkeypatch, store)
    _record_sync("user-1", {"reading:B": 4.5})
    _record_sync("user-1", {"reading:B": 6.0})
    assert len(store.rows) == 1
    row = store.rows[("user-1", "OET", "reading:B")]
    assert row["attempts"] == 2
    # alpha=0.3: 0.3*6.0 + 0.7*4.5 = 4.95
    assert row["ema_score"] == 4.95


# ── E: product isolation (pure fixture -- code only ever writes OET today) ─

def test_same_skill_tag_different_product_is_a_distinct_row(monkeypatch):
    store = _FakeStore()
    _patch_supabase(monkeypatch, store)
    # Simulate a pre-existing row for a hypothetical second product sharing
    # the same user_id/skill_tag, proving the composite key keeps it distinct
    # from what _record_sync writes for OET.
    store.rows[("user-1", "IELTS", "reading:B")] = {
        "user_id": "user-1", "product": "IELTS", "skill_tag": "reading:B",
        "attempts": 3, "ema_score": 5.0,
    }
    _record_sync("user-1", {"reading:B": 4.5})
    assert len(store.rows) == 2
    assert store.rows[("user-1", "IELTS", "reading:B")]["attempts"] == 3
    assert store.rows[("user-1", "OET", "reading:B")]["attempts"] == 1


# ── F: best-effort failure isolation preserved ──────────────────────────

def test_record_skill_observations_swallows_failure(monkeypatch):
    class _BrokenStore:
        def table(self, _name):
            raise RuntimeError("simulated QA schema mismatch")

    _patch_supabase(monkeypatch, _BrokenStore())
    asyncio.run(record_skill_observations("user-1", {"reading:B": 4.5}))  # must not raise


def test_record_skill_observations_noop_on_empty_scores(monkeypatch):
    store = _FakeStore()
    _patch_supabase(monkeypatch, store)
    asyncio.run(record_skill_observations("user-1", {}))
    assert store.rows == {}


# ── G: get_weakness unaffected by the extra "product" column ───────────

def test_get_weakness_ignores_product_column_on_rows(monkeypatch):
    from app.services.skill_graph import get_weakness, WEAKNESS_MIN_ATTEMPTS

    class _WeaknessQuery:
        def __init__(self, rows):
            self._rows = rows

        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def like(self, *a, **k):
            return self

        def execute(self):
            return _FakeResult(self._rows)

    class _WeaknessSupabase:
        def __init__(self, rows):
            self._rows = rows

        def table(self, _name):
            return _WeaknessQuery(self._rows)

    rows = [{"skill_tag": "reading:A", "attempts": WEAKNESS_MIN_ATTEMPTS, "ema_score": 3.0, "product": "OET"}]
    out = asyncio.run(get_weakness(_WeaknessSupabase(rows), "user-1", "reading:"))
    assert len(out) == 1
    assert out[0]["skill"] == "A"
