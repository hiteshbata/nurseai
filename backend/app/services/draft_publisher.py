"""Publishing engine for RC3.3: turns an approved draft into real production
content. Copies, never moves -- the draft row is left untouched (its status
flip to 'published' happens in draft_store.mark_published, called by the
router after publish() succeeds here). Speaking/Writing publish into
scenarios; Reading/Listening publish the passage/section only, standalone
(test_id left null) -- grouping published items into a full test/paper is
explicitly deferred to a future Test Builder (CTO decision). Vocabulary and
Grammar have no production target this sprint.

Reading/Listening standalone rows publish with is_active=False. With no
test_id, there's no "Make Live" step for them to go through (that only
exists at the test level), so is_active=True would make them immediately
student-visible via GET /reading/passages the moment publish() runs -- an
admin must explicitly activate the row afterward via the existing
passage/section-active endpoint. Speaking/Writing scenarios are unaffected
(published active=True, as before).

build_preview() and publish() share the same per-module payload builders
and the same create-vs-update decision (_existing_production_id) so the
Publish Preview dialog can never drift from what publish() actually does.

One draft is at most one production row (Model A). First publish INSERTs;
republishing an edited, re-approved draft UPDATEs that same row in place --
it never creates a second one. See publish()'s docstring for what a
republish does and doesn't touch.

Reading Part B and Part C are Model A's deliberate exceptions (Phase 4B,
4C-3): their generated_content is several independent passages, not 1, so
each publishes multiple reading_passages rows per draft (6 for Part B, 2 for
Part C) instead of 1 -- see _reading_part_b_payloads/_reading_part_c_payloads
and the shared _publish_multi_passage_reading. Each of those rows still has
its own one-row-per-slot guarantee (reading_passages_source_draft_uidx is
(source_draft_id, passage_seq), not source_draft_id alone --
20260816000000_reading_part_b_multi_passage.sql), so a republish still
UPDATEs the same rows rather than duplicating them. Part A is unaffected:
passage_seq defaults to 0, so it keeps exactly the old one-row-per-draft
behavior.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from app.core.supabase import get_supabase
from app.services import listening_audio

logger = logging.getLogger(__name__)

_PUBLISH_TABLE = {
    "speaking": "scenarios",
    "writing": "scenarios",
    "reading": "reading_passages",
    "listening": "listening_sections",
}


class NotPublishableError(Exception):
    """module has no production target this sprint (vocab, grammar)."""


class DuplicateTitleError(Exception):
    """Hard-uniqueness conflict (scenarios(module, lower(trim(title)))) --
    caller must rename the draft's title before publishing again."""


class AlreadyPublishedError(Exception):
    """Hard-uniqueness conflict on reading_passages/listening_sections
    (source_draft_id) -- this draft already has a published row; a second
    Publish (double-click, two admins racing, or a retry after publish()
    succeeded but mark_published() failed) cannot create another one."""


class InvalidPartError(Exception):
    """content['part'] isn't one of the values the target table's CHECK
    constraint allows -- raised here so publish fails loudly instead of
    silently coercing to a default part."""


class AudioNotReadyError(Exception):
    """A Listening Part A/B/C draft has one or more extracts whose audio is
    missing (NOT_GENERATED) or stale (OUTDATED -- transcript edited after
    audio was generated), per listening_audio.get_audio_status. Raised
    before any production row is written, so Publish never ships an extract
    a learner can't hear or whose audio doesn't match its transcript."""

    def __init__(self, part: str, missing_indexes: List[int], outdated_indexes: List[int]):
        self.part = part
        self.missing_indexes = missing_indexes
        self.outdated_indexes = outdated_indexes
        if missing_indexes and outdated_indexes:
            self.reason = "audio_missing_and_outdated"
        elif outdated_indexes:
            self.reason = "audio_outdated"
        else:
            self.reason = "audio_missing"
        bits = []
        if missing_indexes:
            bits.append(f"missing audio for extract(s) {missing_indexes}")
        if outdated_indexes:
            bits.append(f"outdated audio for extract(s) {outdated_indexes}")
        super().__init__(f"Listening Part {part} is not publish-ready: {'; '.join(bits)}.")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _title(draft: Dict[str, Any], content: Dict[str, Any]) -> str:
    return str(content.get("title") or draft.get("ai_title") or draft.get("draft_name") or "").strip()


def _scenario_payload(draft: Dict[str, Any]) -> Dict[str, Any]:
    module = draft["module"]
    content = draft["generated_content"]
    payload: Dict[str, Any] = {
        "module": module,
        "title": _title(draft, content),
        "difficulty": content.get("difficulty", "intermediate"),
        "specialty": content.get("specialty") or (draft.get("metadata") or {}).get("specialty"),
        "scoring_criteria": {},
        "source_draft_id": draft["id"],
    }
    if module == "speaking":
        payload["setting"] = content.get("setting", "")
        payload["nurse_card"] = content.get("nurse_card", {})
        payload["interlocutor_card"] = content.get("interlocutor_card", {})
    else:  # writing -- case_notes lives in `setting`, task lives in nurse_card.role
        # (matches how writing.py already reads existing scenarios, see
        # `case_notes=scenario.get("setting", "")` in routers/writing.py)
        payload["setting"] = content.get("case_notes", "")
        payload["nurse_card"] = {"role": content.get("task", "")}
        payload["interlocutor_card"] = {}
        payload["key_points"] = content.get("key_points", [])
    return payload


_READING_PARTS = ("A", "B", "C")  # matches reading_passages_part_check (20260724000200_reading_part_a.sql)
_PART_B_PASSAGE_COUNT = 6  # locked contract, matches the Part B structural validator
_PART_C_TEXT_COUNT = 2  # locked contract, matches the Part C structural validator


def _reading_payload(draft: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Part A: one passage, one row. Part B and Part C are NOT handled here
    -- they're several independent passages, not one payload -- see
    _reading_part_b_payloads / _reading_part_c_payloads. Routing a Part B/C
    draft through here would silently combine its passages into a single
    row, which is exactly the shape publish() must never produce."""
    content = draft["generated_content"]
    part = content.get("part")
    if part not in _READING_PARTS:
        raise InvalidPartError(f"Reading draft has invalid part {part!r}; must be one of {_READING_PARTS}.")
    if part == "B":
        raise InvalidPartError("Part B publishes as 6 separate passages, not one combined passage.")
    if part == "C":
        raise InvalidPartError("Part C publishes as 2 separate passages, not one combined passage.")
    passage = {
        "title": _title(draft, content),
        "part": part,
        "difficulty": content.get("difficulty", "intermediate"),
        "body": content.get("body", ""),
        # Starts inactive: with test_id left null (Test Builder deferred),
        # is_active=True would make this immediately student-visible via
        # GET /reading/passages with no Make Live step. An admin must
        # explicitly flip it active via the existing passage-active endpoint.
        "is_active": False,
        "source_draft_id": draft["id"],
    }
    return passage, content.get("questions", [])


def _set_audio_url(section: Dict[str, Any], source: Dict[str, Any]) -> None:
    """Only sets audio_url when `source` explicitly carries a non-empty
    replacement. Draft generated_content never carries audio -- that's
    attached to the production row afterward via listening.py's own
    upload/TTS endpoints -- so omitting the key here (rather than setting it
    to None) means an update() leaves the production row's existing
    audio_url untouched. A missing audio_url must never be read as "delete
    audio" (RC Phase 6A)."""
    url = source.get("audio_url")
    if isinstance(url, str) and url.strip():
        section["audio_url"] = url.strip()


def _listening_payload(draft: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Legacy flat listening generation (no locked Part A/B/C contract): one
    section, one row -- untouched by Phase 3C. Part A/B/C drafts are NOT
    handled here -- see _listening_part_a/b/c_payloads below."""
    content = draft["generated_content"]
    part = content.get("part")
    section = {
        "title": _title(draft, content),
        "part": part if part in ("A", "B", "C") else "B",
        "difficulty": content.get("difficulty", "intermediate"),
        "transcript": content.get("transcript"),
        "body": None,
        # Starts inactive -- see matching comment in _reading_payload.
        "is_active": False,
        "source_draft_id": draft["id"],
    }
    _set_audio_url(section, content)
    return section, content.get("questions", [])


# Locked Listening Part A/B/C contract (Phase 3C): each part publishes N
# independent listening_sections rows from one draft (2 for A, 6 for B, 2 for
# C), same multi-row architecture Reading Part B/C established --
# section_seq (0..N-1, generation order) is what lets them share one
# source_draft_id despite listening_sections_source_draft_uidx being widened
# to (source_draft_id, section_seq) -- see the Phase 3F migration file.
_LISTENING_PART_A_EXTRACT_COUNT = 2  # locked contract, matches the Part A structural validator
_LISTENING_PART_B_EXTRACT_COUNT = 6  # locked contract, matches the Part B structural validator
_LISTENING_PART_C_EXTRACT_COUNT = 2  # locked contract, matches the Part C structural validator


def _listening_part_a_payloads(draft: Dict[str, Any]) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Part A's 2 independent extracts, each its own listening_sections row
    (part='A', 12 short_answer questions, body=note-completion template,
    prep_seconds=30, audio_mode='dialogue' -- global, copied onto every row)."""
    content = draft["generated_content"]
    extracts = content.get("extracts")
    if not isinstance(extracts, list) or len(extracts) != _LISTENING_PART_A_EXTRACT_COUNT:
        got = len(extracts) if isinstance(extracts, list) else type(extracts).__name__
        raise InvalidPartError(f"Listening Part A draft must have exactly {_LISTENING_PART_A_EXTRACT_COUNT} extracts; got {got}.")
    out: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]] = []
    for seq, ex in enumerate(extracts):
        section = {
            "title": str(ex.get("title") or "").strip(),
            "part": "A",
            "difficulty": content.get("difficulty", "intermediate"),
            "transcript": ex.get("transcript"),
            "body": ex.get("body"),
            "prep_seconds": content.get("prep_seconds", 30),
            "audio_mode": content.get("audio_mode", "dialogue"),
            "section_seq": seq,
            # Starts inactive -- see matching comment in _reading_payload.
            "is_active": False,
            "source_draft_id": draft["id"],
        }
        _set_audio_url(section, ex)
        out.append((section, ex.get("questions", [])))
    return out


def _listening_part_b_payloads(draft: Dict[str, Any]) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Part B's 6 independent extracts, each its own listening_sections row
    (part='B', 1 mcq/3-option question, prep_seconds=15, audio_mode='dialogue'
    -- global, copied onto every row). No body -- that's Part A only."""
    content = draft["generated_content"]
    extracts = content.get("extracts")
    if not isinstance(extracts, list) or len(extracts) != _LISTENING_PART_B_EXTRACT_COUNT:
        got = len(extracts) if isinstance(extracts, list) else type(extracts).__name__
        raise InvalidPartError(f"Listening Part B draft must have exactly {_LISTENING_PART_B_EXTRACT_COUNT} extracts; got {got}.")
    out: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]] = []
    for seq, ex in enumerate(extracts):
        section = {
            "title": str(ex.get("title") or "").strip(),
            "part": "B",
            "difficulty": content.get("difficulty", "intermediate"),
            "transcript": ex.get("transcript"),
            "body": None,
            "prep_seconds": content.get("prep_seconds", 15),
            "audio_mode": content.get("audio_mode", "dialogue"),
            "section_seq": seq,
            # Starts inactive -- see matching comment in _reading_payload.
            "is_active": False,
            "source_draft_id": draft["id"],
        }
        _set_audio_url(section, ex)
        out.append((section, ex.get("questions", [])))
    return out


def _listening_part_c_payloads(draft: Dict[str, Any]) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Part C's 2 independent extracts, each its own listening_sections row
    (part='C', 6 mcq/3-option questions, prep_seconds=90). audio_mode is
    chosen PER EXTRACT (dialogue/monologue), unlike Part A/B's global value --
    read from each extract, not from content['audio_mode']."""
    content = draft["generated_content"]
    extracts = content.get("extracts")
    if not isinstance(extracts, list) or len(extracts) != _LISTENING_PART_C_EXTRACT_COUNT:
        got = len(extracts) if isinstance(extracts, list) else type(extracts).__name__
        raise InvalidPartError(f"Listening Part C draft must have exactly {_LISTENING_PART_C_EXTRACT_COUNT} extracts; got {got}.")
    out: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]] = []
    for seq, ex in enumerate(extracts):
        section = {
            "title": str(ex.get("title") or "").strip(),
            "part": "C",
            "difficulty": content.get("difficulty", "intermediate"),
            "transcript": ex.get("transcript"),
            "body": None,
            "prep_seconds": content.get("prep_seconds", 90),
            "audio_mode": ex.get("audio_mode", "dialogue"),
            "section_seq": seq,
            # Starts inactive -- see matching comment in _reading_payload.
            "is_active": False,
            "source_draft_id": draft["id"],
        }
        _set_audio_url(section, ex)
        out.append((section, ex.get("questions", [])))
    return out


_LISTENING_PART_PAYLOAD_BUILDERS = {
    "A": _listening_part_a_payloads,
    "B": _listening_part_b_payloads,
    "C": _listening_part_c_payloads,
}


def _check_listening_audio_gate(part: str, extracts: List[Dict[str, Any]]) -> None:
    """Every extract in a locked-contract Listening draft must have current
    audio before publish -- called only from the extracts[] branches of
    build_preview/publish, after the payload builder above has already
    confirmed the extract count matches the part's locked contract. Legacy
    flat listening (_listening_payload, no extracts[] key) never reaches
    this function."""
    missing = [i for i, ex in enumerate(extracts) if listening_audio.get_audio_status(ex) == "NOT_GENERATED"]
    outdated = [i for i, ex in enumerate(extracts) if listening_audio.get_audio_status(ex) == "OUTDATED"]
    if missing or outdated:
        raise AudioNotReadyError(part, missing, outdated)


def _reading_part_b_payloads(draft: Dict[str, Any]) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Part B's 6 independent extracts, each its own reading_passages row
    (part='B', one 3-option MCQ). passage_seq (0-5, generation order) is
    what lets all 6 share source_draft_id despite reading_passages_source_draft_uidx
    now being a (source_draft_id, passage_seq) composite -- see
    20260816000000_reading_part_b_multi_passage.sql."""
    content = draft["generated_content"]
    passages = content.get("passages")
    if not isinstance(passages, list) or len(passages) != _PART_B_PASSAGE_COUNT:
        got = len(passages) if isinstance(passages, list) else type(passages).__name__
        raise InvalidPartError(f"Part B draft must have exactly {_PART_B_PASSAGE_COUNT} passages; got {got}.")
    out: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]] = []
    for seq, p in enumerate(passages):
        passage = {
            "title": str(p.get("title") or "").strip(),
            "part": "B",
            "difficulty": content.get("difficulty", "intermediate"),
            "body": p.get("body", ""),
            "passage_seq": seq,
            # Starts inactive -- see matching comment in _reading_payload.
            "is_active": False,
            "source_draft_id": draft["id"],
        }
        out.append((passage, p.get("questions", [])))
    return out


def _reading_part_c_payloads(draft: Dict[str, Any]) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Part C's 2 independent long-form texts, each its own reading_passages
    row (part='C', 8 4-option MCQs). Same passage_seq (0-1, generation order)
    mechanism as Part B -- see _reading_part_b_payloads."""
    content = draft["generated_content"]
    texts = content.get("texts")
    if not isinstance(texts, list) or len(texts) != _PART_C_TEXT_COUNT:
        got = len(texts) if isinstance(texts, list) else type(texts).__name__
        raise InvalidPartError(f"Part C draft must have exactly {_PART_C_TEXT_COUNT} texts; got {got}.")
    out: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]] = []
    for seq, t in enumerate(texts):
        passage = {
            "title": str(t.get("title") or "").strip(),
            "part": "C",
            "difficulty": content.get("difficulty", "intermediate"),
            "body": t.get("body", ""),
            "passage_seq": seq,
            # Starts inactive -- see matching comment in _reading_payload.
            "is_active": False,
            "source_draft_id": draft["id"],
        }
        out.append((passage, t.get("questions", [])))
    return out


def _existing_multi_passage_production_ids(supabase, draft_id: int) -> Dict[int, Any]:
    """seq -> production row id, for whichever of this draft's Part B/C
    passages already exist (republish) -- vs. _existing_production_id's
    single id, since Part B/C publish several rows, not 1."""
    rows = supabase.table("reading_passages").select("id, passage_seq").eq("source_draft_id", draft_id).execute().data
    return {r["passage_seq"]: r["id"] for r in rows if r.get("passage_seq") is not None}


def _existing_multi_section_production_ids(supabase, draft_id: int) -> Dict[int, Any]:
    """seq -> production row id, for whichever of this draft's Listening
    Part A/B/C sections already exist (republish) -- listening_sections
    analog of _existing_multi_passage_production_ids."""
    rows = supabase.table("listening_sections").select("id, section_seq").eq("source_draft_id", draft_id).execute().data
    return {r["section_seq"]: r["id"] for r in rows if r.get("section_seq") is not None}


def _existing_production_id(supabase, table: str, draft_id: int) -> Any:
    """The one production row this draft already published, if any (Model A:
    one draft -> at most one production row, enforced for reading/listening
    by reading_passages_source_draft_uidx / listening_sections_source_draft_uidx,
    for scenarios by the fact publish() only ever writes one row per draft).
    None means this is a first publish; a row -> republish must UPDATE it,
    never INSERT a second one."""
    rows = supabase.table(table).select("id").eq("source_draft_id", draft_id).execute().data
    return rows[0]["id"] if rows else None


def _duplicate_warning(supabase, table: str, title: str, extra_eq: Dict[str, Any], exclude_id: Any = None) -> List[str]:
    if not title:
        return []
    query = supabase.table(table).select("id").ilike("title", title)
    for col, val in extra_eq.items():
        query = query.eq(col, val)
    existing = [r for r in query.limit(5).execute().data if r["id"] != exclude_id]
    if not existing:
        return []
    return [f'A "{table}" row titled "{title}" already exists (id {existing[0]["id"]}) -- consider renaming before publishing.']


def build_preview(draft: Dict[str, Any]) -> Dict[str, Any]:
    """Dry run: returns exactly what publish() would do, without writing
    anything. Used by the Publish Preview dialog -- must stay in lockstep
    with publish()'s own create-vs-update decision (see _existing_production_id)
    so a republish preview doesn't warn about "duplicating" the very row it
    would update, and doesn't call an update a create."""
    module = draft["module"]
    if module not in _PUBLISH_TABLE:
        raise NotPublishableError(f'"{module}" publishing is not available.')
    supabase = get_supabase()
    table = _PUBLISH_TABLE[module]
    existing_id = _existing_production_id(supabase, table, draft["id"])
    action = "update" if existing_id else "create"

    if module in ("speaking", "writing"):
        payload = _scenario_payload(draft)
        warnings = _duplicate_warning(supabase, "scenarios", payload["title"], {"module": module}, exclude_id=existing_id)
        return {"records": [{"table": "scenarios", "fields": payload, "action": action, "id": existing_id}], "warnings": warnings}

    if module == "reading" and draft["generated_content"].get("part") in ("B", "C"):
        payloads = _reading_part_b_payloads(draft) if draft["generated_content"]["part"] == "B" else _reading_part_c_payloads(draft)
        existing = _existing_multi_passage_production_ids(supabase, draft["id"])
        records: List[Dict[str, Any]] = []
        warnings: List[str] = []
        for seq, (passage, questions) in enumerate(payloads):
            existing_id = existing.get(seq)
            warnings += _duplicate_warning(supabase, "reading_passages", passage["title"], {}, exclude_id=existing_id)
            records.append({"table": "reading_passages", "fields": passage, "action": "update" if existing_id else "create", "id": existing_id})
            records.append({"table": "questions", "count": len(questions)})
        return {"records": records, "warnings": warnings}

    if module == "reading":
        passage, questions = _reading_payload(draft)
        warnings = _duplicate_warning(supabase, "reading_passages", passage["title"], {}, exclude_id=existing_id)
        return {
            "records": [
                {"table": "reading_passages", "fields": passage, "action": action, "id": existing_id},
                {"table": "questions", "count": len(questions)},
            ],
            "warnings": warnings,
        }

    if module == "listening" and draft["generated_content"].get("part") in _LISTENING_PART_PAYLOAD_BUILDERS:
        part = draft["generated_content"]["part"]
        payloads = _LISTENING_PART_PAYLOAD_BUILDERS[part](draft)
        _check_listening_audio_gate(part, draft["generated_content"]["extracts"])
        existing = _existing_multi_section_production_ids(supabase, draft["id"])
        records: List[Dict[str, Any]] = []
        warnings: List[str] = []
        for seq, (section, questions) in enumerate(payloads):
            existing_id = existing.get(seq)
            warnings += _duplicate_warning(supabase, "listening_sections", section["title"], {}, exclude_id=existing_id)
            records.append({"table": "listening_sections", "fields": section, "action": "update" if existing_id else "create", "id": existing_id})
            records.append({"table": "questions", "count": len(questions)})
        return {"records": records, "warnings": warnings}

    section, questions = _listening_payload(draft)
    warnings = _duplicate_warning(supabase, "listening_sections", section["title"], {}, exclude_id=existing_id)
    return {
        "records": [
            {"table": "listening_sections", "fields": section, "action": action, "id": existing_id},
            {"table": "questions", "count": len(questions)},
        ],
        "warnings": warnings,
    }


def _insert_questions(
    supabase, module: str, questions: List[Dict[str, Any]], link_col: str, link_id: int,
    collected: List[Any] = None,
) -> List[Any]:
    """Inserts one row per question. `collected`, if given, is appended to as
    each insert succeeds -- so a caller that needs to know what actually
    landed before a later item fails (see _replace_questions) still has that
    list even though this function raises instead of returning on failure."""
    inserted_ids = collected if collected is not None else []
    for q in questions:
        row = supabase.table("questions").insert({
            "module": module,
            "type": q.get("type", "mcq"),
            "content": q.get("content", ""),
            "options": json.dumps(q["options"]) if q.get("options") else None,
            "correct_answer": q.get("correct_answer") or None,
            link_col: link_id,
        }).execute().data[0]
        inserted_ids.append(row["id"])
    return inserted_ids


def _replace_questions(supabase, module: str, questions: List[Dict[str, Any]], link_col: str, link_id: int) -> int:
    """Republish: swap in the edited question set without ever leaving a
    mixed or duplicated set behind. The old set is never touched until the
    complete new set is confirmed inserted. If anything fails -- a partial
    insert, or the old-set delete itself -- whatever new rows did get
    created are torn back down (by id, scoped to this link_id, never a bare
    delete-by-id that could touch an unrelated question) and the old set is
    left as the sole survivor. The original exception is always what
    propagates; if the cleanup delete itself also fails, that's logged, not
    raised in place of it -- a cleanup failure must never hide why the
    replacement actually failed."""
    new_ids: List[Any] = []
    try:
        _insert_questions(supabase, module, questions, link_col, link_id, collected=new_ids)
        query = supabase.table("questions").delete().eq(link_col, link_id)
        if new_ids:
            query = query.not_.in_("id", new_ids)
        query.execute()
    except Exception:
        if new_ids:
            try:
                supabase.table("questions").delete().eq(link_col, link_id).in_("id", new_ids).execute()
            except Exception:
                logger.exception(
                    "Republish of %s=%s failed and cleanup of %d partially-inserted question "
                    "row(s) also failed -- ids %s may be orphaned and need manual removal. "
                    "The old question set was never touched and is still intact.",
                    link_col, link_id, len(new_ids), new_ids,
                )
        raise
    return len(questions)


def _publish_multi_passage_reading(supabase, draft: Dict[str, Any], now: str, payloads: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]) -> Dict[str, Any]:
    """Shared by Part B (6 passages) and Part C (2 passages) -- either
    publishes several passages, not 1 -- see _reading_part_b_payloads /
    _reading_part_c_payloads. Each gets the same insert-or-update-by-seq
    treatment publish()'s single-passage branch gives its one row (create on
    first publish, update in place on republish -- never a second row for a
    seq that already has one). There's no cross-row DB transaction available
    here (supabase-py is one REST call per insert/update, same constraint
    the single-passage rollback below already lives with), so atomicity is
    application-level: every passage *this call* newly inserts is tracked,
    and if any later passage/question in the same call fails, all of them
    are torn back down (ON DELETE CASCADE takes their questions with them)
    before the exception propagates -- a failed Publish never leaves a
    partial set. A republish only UPDATEs rows that already existed before
    this call started, so there's nothing to unwind for it."""
    existing = _existing_multi_passage_production_ids(supabase, draft["id"])
    results: List[Dict[str, Any]] = []
    created_ids: List[Any] = []
    try:
        for seq, (passage, questions) in enumerate(payloads):
            existing_id = existing.get(seq)
            if existing_id:
                passage.pop("is_active", None)
                row = supabase.table("reading_passages").update(passage).eq("id", existing_id).execute().data[0]
                questions_created = _replace_questions(supabase, "reading", questions, "passage_id", existing_id)
                results.append({"id": row["id"], "title": row["title"], "questions_created": questions_created, "action": "updated"})
                continue
            passage["published_at"] = now
            try:
                row = supabase.table("reading_passages").insert(passage).execute().data[0]
            except Exception as e:
                if "duplicate key" in str(e).lower():
                    raise AlreadyPublishedError(f"Draft {draft['id']} has already been published to reading_passages.")
                raise
            created_ids.append(row["id"])
            _insert_questions(supabase, "reading", questions, "passage_id", row["id"])
            results.append({"id": row["id"], "title": row["title"], "questions_created": len(questions), "action": "created"})
    except Exception:
        for pid in created_ids:
            try:
                supabase.table("reading_passages").delete().eq("id", pid).execute()
            except Exception:
                logger.exception(
                    "Multi-passage reading publish for draft=%s failed and rollback of "
                    "newly-created passage id=%s also failed -- it (and any cascaded "
                    "questions) may be orphaned and need manual removal.", draft["id"], pid,
                )
        raise
    action = "created" if not existing else ("updated" if len(existing) >= len(payloads) else "mixed")
    return {"table": "reading_passages", "passages": results, "questions_created": sum(r["questions_created"] for r in results), "action": action}


def _publish_multi_section_listening(supabase, draft: Dict[str, Any], now: str, payloads: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]) -> Dict[str, Any]:
    """Shared by Listening Part A (2 sections), Part B (6), and Part C (2) --
    listening_sections analog of _publish_multi_passage_reading, same
    insert-or-update-by-seq + all-or-nothing rollback behavior. See that
    function's docstring for the full reasoning; not repeated here."""
    existing = _existing_multi_section_production_ids(supabase, draft["id"])
    results: List[Dict[str, Any]] = []
    created_ids: List[Any] = []
    try:
        for seq, (section, questions) in enumerate(payloads):
            existing_id = existing.get(seq)
            if existing_id:
                section.pop("is_active", None)
                row = supabase.table("listening_sections").update(section).eq("id", existing_id).execute().data[0]
                questions_created = _replace_questions(supabase, "listening", questions, "section_id", existing_id)
                results.append({"id": row["id"], "title": row["title"], "questions_created": questions_created, "action": "updated"})
                continue
            section["published_at"] = now
            try:
                row = supabase.table("listening_sections").insert(section).execute().data[0]
            except Exception as e:
                if "duplicate key" in str(e).lower():
                    raise AlreadyPublishedError(f"Draft {draft['id']} has already been published to listening_sections.")
                raise
            created_ids.append(row["id"])
            _insert_questions(supabase, "listening", questions, "section_id", row["id"])
            results.append({"id": row["id"], "title": row["title"], "questions_created": len(questions), "action": "created"})
    except Exception:
        for sid in created_ids:
            try:
                supabase.table("listening_sections").delete().eq("id", sid).execute()
            except Exception:
                logger.exception(
                    "Multi-section listening publish for draft=%s failed and rollback of "
                    "newly-created section id=%s also failed -- it (and any cascaded "
                    "questions) may be orphaned and need manual removal.", draft["id"], sid,
                )
        raise
    action = "created" if not existing else ("updated" if len(existing) >= len(payloads) else "mixed")
    return {"table": "listening_sections", "sections": results, "questions_created": sum(r["questions_created"] for r in results), "action": action}


def publish(draft: Dict[str, Any], published_by: str) -> Dict[str, Any]:
    """First publish INSERTs a new production row. Republish (this draft
    already has one, found via source_draft_id -- see _existing_production_id)
    UPDATEs that same row instead: one draft is at most one production row
    (Model A), never a second row per edit. is_active and published_at are
    deliberately left out of the update payload -- a republish must not
    reset an admin's prior "make live" action, and published_at stays the
    original first-publish time (matching the migration's own stated intent
    for that column) rather than being bumped on every correction."""
    module = draft["module"]
    if module not in _PUBLISH_TABLE:
        raise NotPublishableError(f'"{module}" publishing is not available.')
    supabase = get_supabase()
    now = _now_iso()
    table = _PUBLISH_TABLE[module]
    existing_id = _existing_production_id(supabase, table, draft["id"])

    if module in ("speaking", "writing"):
        payload = _scenario_payload(draft)
        try:
            if existing_id:
                row = supabase.table("scenarios").update(payload).eq("id", existing_id).execute().data[0]
                action = "updated"
            else:
                payload["published_at"] = now
                row = supabase.table("scenarios").insert(payload).execute().data[0]
                action = "created"
        except Exception as e:
            if "duplicate key" in str(e).lower():
                raise DuplicateTitleError(f'A {module} scenario titled "{payload["title"]}" already exists.')
            raise
        return {"table": "scenarios", "id": row["id"], "title": row["title"], "action": action}

    if module == "reading" and draft["generated_content"].get("part") == "B":
        return _publish_multi_passage_reading(supabase, draft, now, _reading_part_b_payloads(draft))

    if module == "reading" and draft["generated_content"].get("part") == "C":
        return _publish_multi_passage_reading(supabase, draft, now, _reading_part_c_payloads(draft))

    if module == "reading":
        passage, questions = _reading_payload(draft)
        if existing_id:
            passage.pop("is_active", None)
            row = supabase.table("reading_passages").update(passage).eq("id", existing_id).execute().data[0]
            questions_created = _replace_questions(supabase, "reading", questions, "passage_id", existing_id)
            return {"table": "reading_passages", "id": row["id"], "title": row["title"], "questions_created": questions_created, "action": "updated"}
        passage["published_at"] = now
        try:
            row = supabase.table("reading_passages").insert(passage).execute().data[0]
        except Exception as e:
            if "duplicate key" in str(e).lower():
                raise AlreadyPublishedError(f"Draft {draft['id']} has already been published to reading_passages.")
            raise
        try:
            _insert_questions(supabase, "reading", questions, "passage_id", row["id"])
        except Exception:
            # Best-effort rollback -- ON DELETE CASCADE takes any already-inserted
            # questions with it (see 20260723000300_reading_passages.sql).
            supabase.table("reading_passages").delete().eq("id", row["id"]).execute()
            raise
        return {"table": "reading_passages", "id": row["id"], "title": row["title"], "questions_created": len(questions), "action": "created"}

    if module == "listening" and draft["generated_content"].get("part") in _LISTENING_PART_PAYLOAD_BUILDERS:
        part = draft["generated_content"]["part"]
        payloads = _LISTENING_PART_PAYLOAD_BUILDERS[part](draft)
        _check_listening_audio_gate(part, draft["generated_content"]["extracts"])
        return _publish_multi_section_listening(supabase, draft, now, payloads)

    section, questions = _listening_payload(draft)
    if existing_id:
        section.pop("is_active", None)
        row = supabase.table("listening_sections").update(section).eq("id", existing_id).execute().data[0]
        questions_created = _replace_questions(supabase, "listening", questions, "section_id", existing_id)
        return {"table": "listening_sections", "id": row["id"], "title": row["title"], "questions_created": questions_created, "action": "updated"}
    section["published_at"] = now
    try:
        row = supabase.table("listening_sections").insert(section).execute().data[0]
    except Exception as e:
        if "duplicate key" in str(e).lower():
            raise AlreadyPublishedError(f"Draft {draft['id']} has already been published to listening_sections.")
        raise
    try:
        _insert_questions(supabase, "listening", questions, "section_id", row["id"])
    except Exception:
        supabase.table("listening_sections").delete().eq("id", row["id"]).execute()
        raise
    return {"table": "listening_sections", "id": row["id"], "title": row["title"], "questions_created": len(questions), "action": "created"}


def unpublish(draft: Dict[str, Any]) -> Dict[str, Any]:
    """Sets is_active=false on every production row this draft published --
    no manual DB access required. The row(s) (and their published_at) stay;
    only visibility to learners changes. Every module but Part B reading
    publishes at most one row per draft; a Part B draft publishes 6
    (_reading_part_b_payloads), and all 6 must go dark together."""
    module = draft["module"]
    table = _PUBLISH_TABLE.get(module)
    if not table:
        raise NotPublishableError(f'"{module}" has no production target.')
    supabase = get_supabase()
    rows = supabase.table(table).select("id").eq("source_draft_id", draft["id"]).execute().data
    if not rows:
        raise LookupError("This draft has no published production record to unpublish.")
    ids = [r["id"] for r in rows]
    for row_id in ids:
        supabase.table(table).update({"is_active": False}).eq("id", row_id).execute()
    return {"table": table, "ids": ids, "is_active": False}
