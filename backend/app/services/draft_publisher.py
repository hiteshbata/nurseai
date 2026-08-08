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
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from app.core.supabase import get_supabase

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


def _reading_payload(draft: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    content = draft["generated_content"]
    part = content.get("part")
    passage = {
        # reading_passages.part CHECK only allows B/C -- the AI schema
        # (prompt_builder.build_reading_prompt) offers A/B/C, so clamp here
        # rather than let an occasional 'A' 500 the insert.
        "title": _title(draft, content),
        "part": part if part in ("B", "C") else "C",
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


def _listening_payload(draft: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    content = draft["generated_content"]
    part = content.get("part")
    section = {
        "title": _title(draft, content),
        "part": part if part in ("A", "B", "C") else "B",
        "difficulty": content.get("difficulty", "intermediate"),
        "audio_url": None,
        "transcript": content.get("transcript"),
        "body": None,
        # Starts inactive -- see matching comment in _reading_payload.
        "is_active": False,
        "source_draft_id": draft["id"],
    }
    return section, content.get("questions", [])


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

    section, questions = _listening_payload(draft)
    warnings = _duplicate_warning(supabase, "listening_sections", section["title"], {}, exclude_id=existing_id)
    return {
        "records": [
            {"table": "listening_sections", "fields": section, "action": action, "id": existing_id},
            {"table": "questions", "count": len(questions)},
        ],
        "warnings": warnings,
    }


def _insert_questions(supabase, module: str, questions: List[Dict[str, Any]], link_col: str, link_id: int) -> List[Any]:
    inserted_ids = []
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
    """Republish: swap in the edited question set without ever leaving the
    row with zero questions if this fails partway. Insert the new set first;
    only delete the old set once the new one is fully in place. If the
    insert fails, the old questions are still untouched and intact -- a
    retry-safe partial-failure state, not a data-loss one."""
    new_ids = _insert_questions(supabase, module, questions, link_col, link_id)
    query = supabase.table("questions").delete().eq(link_col, link_id)
    if new_ids:
        query = query.not_.in_("id", new_ids)
    query.execute()
    return len(questions)


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
    """Sets is_active=false on the production row this draft published --
    no manual DB access required. The row (and its published_at) stays;
    only visibility to learners changes."""
    module = draft["module"]
    table = _PUBLISH_TABLE.get(module)
    if not table:
        raise NotPublishableError(f'"{module}" has no production target.')
    supabase = get_supabase()
    rows = supabase.table(table).select("id").eq("source_draft_id", draft["id"]).execute().data
    if not rows:
        raise LookupError("This draft has no published production record to unpublish.")
    row_id = rows[0]["id"]
    supabase.table(table).update({"is_active": False}).eq("id", row_id).execute()
    return {"table": table, "id": row_id, "is_active": False}
