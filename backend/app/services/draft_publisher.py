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

build_preview() and publish() share the same per-module payload builders so
the Publish Preview dialog can never drift from what publish() actually
inserts.
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


def _duplicate_warning(supabase, table: str, title: str, extra_eq: Dict[str, Any]) -> List[str]:
    if not title:
        return []
    query = supabase.table(table).select("id").ilike("title", title)
    for col, val in extra_eq.items():
        query = query.eq(col, val)
    existing = query.limit(1).execute().data
    if not existing:
        return []
    return [f'A "{table}" row titled "{title}" already exists (id {existing[0]["id"]}) -- consider renaming before publishing.']


def build_preview(draft: Dict[str, Any]) -> Dict[str, Any]:
    """Dry run: returns exactly what publish() would create, without writing
    anything. Used by the Publish Preview dialog."""
    module = draft["module"]
    if module not in _PUBLISH_TABLE:
        raise NotPublishableError(f'"{module}" publishing is not available.')
    supabase = get_supabase()

    if module in ("speaking", "writing"):
        payload = _scenario_payload(draft)
        warnings = _duplicate_warning(supabase, "scenarios", payload["title"], {"module": module})
        return {"records": [{"table": "scenarios", "fields": payload}], "warnings": warnings}

    if module == "reading":
        passage, questions = _reading_payload(draft)
        warnings = _duplicate_warning(supabase, "reading_passages", passage["title"], {})
        return {
            "records": [
                {"table": "reading_passages", "fields": passage},
                {"table": "questions", "count": len(questions)},
            ],
            "warnings": warnings,
        }

    section, questions = _listening_payload(draft)
    warnings = _duplicate_warning(supabase, "listening_sections", section["title"], {})
    return {
        "records": [
            {"table": "listening_sections", "fields": section},
            {"table": "questions", "count": len(questions)},
        ],
        "warnings": warnings,
    }


def _insert_questions(supabase, module: str, questions: List[Dict[str, Any]], link_col: str, link_id: int) -> None:
    for q in questions:
        supabase.table("questions").insert({
            "module": module,
            "type": q.get("type", "mcq"),
            "content": q.get("content", ""),
            "options": json.dumps(q["options"]) if q.get("options") else None,
            "correct_answer": q.get("correct_answer") or None,
            link_col: link_id,
        }).execute()


def publish(draft: Dict[str, Any], published_by: str) -> Dict[str, Any]:
    module = draft["module"]
    if module not in _PUBLISH_TABLE:
        raise NotPublishableError(f'"{module}" publishing is not available.')
    supabase = get_supabase()
    now = _now_iso()

    if module in ("speaking", "writing"):
        payload = _scenario_payload(draft)
        payload["published_at"] = now
        try:
            row = supabase.table("scenarios").insert(payload).execute().data[0]
        except Exception as e:
            if "duplicate key" in str(e).lower():
                raise DuplicateTitleError(f'A {module} scenario titled "{payload["title"]}" already exists.')
            raise
        return {"table": "scenarios", "id": row["id"], "title": row["title"]}

    if module == "reading":
        passage, questions = _reading_payload(draft)
        passage["published_at"] = now
        row = supabase.table("reading_passages").insert(passage).execute().data[0]
        try:
            _insert_questions(supabase, "reading", questions, "passage_id", row["id"])
        except Exception:
            # Best-effort rollback -- ON DELETE CASCADE takes any already-inserted
            # questions with it (see 20260723000300_reading_passages.sql).
            supabase.table("reading_passages").delete().eq("id", row["id"]).execute()
            raise
        return {"table": "reading_passages", "id": row["id"], "title": row["title"], "questions_created": len(questions)}

    section, questions = _listening_payload(draft)
    section["published_at"] = now
    row = supabase.table("listening_sections").insert(section).execute().data[0]
    try:
        _insert_questions(supabase, "listening", questions, "section_id", row["id"])
    except Exception:
        supabase.table("listening_sections").delete().eq("id", row["id"]).execute()
        raise
    return {"table": "listening_sections", "id": row["id"], "title": row["title"], "questions_created": len(questions)}


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
