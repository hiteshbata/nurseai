"""RC4.2 -- Deterministic publish-time validation for Reading, Listening and
Mock tests.

Validation-gated publishing: draft/edit -> validation -> Owner publish ->
immutable RC4.1 version (assessment_versioning.py). This module is the
"validation" step only -- it never writes anything, never mutates is_active,
never creates a version. Callers (reading.py/listening.py's set_test_active,
mock.py's admin_publish_mock_test_version) run it BEFORE calling into
assessment_versioning and 409 on failure without calling that at all.

Deterministic checks only -- no AI quality checks, per the approved RC4.2
architecture. The `_validate_reading_content`/`_validate_listening_content`
cores are pure (plain dicts in, no supabase) so they're unit-testable without
a fake DB; the `validate_*_test` wrappers do the live-table resolution, using
the same query shape assessment_versioning.py's `build_*_snapshot` already
uses for "what's actually live right now".
"""
import json
from typing import Any, Dict, List, Optional, Tuple

from app.services.assessment_versioning import latest_version_id

_REQUIRED_PARTS = ("A", "B", "C")
_VALID_TYPES = {"mcq", "short_answer"}


def _ok(warnings: Optional[List[dict]] = None) -> Dict[str, Any]:
    return {"valid": True, "errors": [], "warnings": warnings or []}


def _err(code: str, field: str, message: str, details: Optional[dict] = None) -> dict:
    return {"code": code, "field": field, "message": message, "details": details or {}}


def _result(errors: List[dict], warnings: List[dict]) -> Dict[str, Any]:
    return {"valid": not errors, "errors": errors, "warnings": warnings}


# ── shared question-level checks (reading passage / listening section) ────

def _check_questions(questions: List[dict], parent_field: str, parent_label: str) -> List[dict]:
    """Question-level checks shared by Reading passages and Listening
    sections: >=2 options, non-blank correct_answer at publish time,
    correct_answer must exactly match one option, valid type, no duplicate
    option strings within a question, no duplicate question text within the
    parent (passage/section)."""
    errors: List[dict] = []
    if not questions:
        errors.append(_err("no_questions", parent_field, f"{parent_label} has no questions"))
        return errors

    seen_content: Dict[str, int] = {}
    for q in questions:
        qid = q.get("question_id")
        content = (q.get("content") or "").strip()
        qtype = q.get("type") or "mcq"
        options = q.get("options") or []
        answer = (q.get("correct_answer") or "").strip()

        if qtype not in _VALID_TYPES:
            errors.append(_err(
                "invalid_type", f"question:{qid}",
                f"Question {qid} has an invalid type '{qtype}'",
                {"question_id": qid, "type": qtype},
            ))

        if content:
            seen_content[content] = seen_content.get(content, 0) + 1

        if qtype == "short_answer":
            if not answer:
                errors.append(_err(
                    "blank_answer", f"question:{qid}",
                    f"Question {qid} has no correct answer",
                    {"question_id": qid},
                ))
            continue

        if len(options) < 2:
            errors.append(_err(
                "too_few_options", f"question:{qid}",
                f"Question {qid} needs at least 2 options",
                {"question_id": qid, "option_count": len(options)},
            ))

        dupes = {o for o in options if options.count(o) > 1}
        if dupes:
            errors.append(_err(
                "duplicate_option", f"question:{qid}",
                f"Question {qid} has duplicate option text: {', '.join(sorted(dupes))}",
                {"question_id": qid, "duplicates": sorted(dupes)},
            ))

        if not answer:
            errors.append(_err(
                "blank_answer", f"question:{qid}",
                f"Question {qid} has no correct answer",
                {"question_id": qid},
            ))
        elif answer not in options:
            errors.append(_err(
                "dangling_answer", f"question:{qid}",
                f"Question {qid}'s correct answer does not match any option",
                {"question_id": qid, "correct_answer": answer, "options": options},
            ))

    for content, count in seen_content.items():
        if count > 1:
            errors.append(_err(
                "duplicate_question_text", parent_field,
                f"{parent_label} has {count} questions with the same text: \"{content[:80]}\"",
                {"content": content, "count": count},
            ))

    return errors


# ── READING ─────────────────────────────────────────────────────────────

def _validate_reading_content(
    passages: List[dict], questions_by_passage: Dict[int, List[dict]],
) -> Tuple[List[dict], List[dict]]:
    errors: List[dict] = []
    warnings: List[dict] = []

    parts_present = {p.get("part") for p in passages}
    for part in _REQUIRED_PARTS:
        if part not in parts_present:
            errors.append(_err("missing_part", f"part:{part}", f"Part {part} is required but has no passage"))

    for p in passages:
        part = p.get("part")
        if part not in _REQUIRED_PARTS:
            errors.append(_err(
                "invalid_part", f"passage:{p.get('passage_id')}",
                f"Passage {p.get('passage_id')} has an invalid part '{part}'",
                {"passage_id": p.get("passage_id"), "part": part},
            ))
        errors.extend(_check_questions(
            questions_by_passage.get(p.get("passage_id"), []),
            f"passage:{p.get('passage_id')}",
            f"Passage \"{p.get('title', '')}\"" ,
        ))

    for part in _REQUIRED_PARTS:
        if part in parts_present and not any(p.get("part") == part for p in passages):
            warnings.append(_err("part_empty", f"part:{part}", f"Part {part} has no active passage"))

    return errors, warnings


def validate_reading_test(supabase, test_id: int) -> Dict[str, Any]:
    """Live-table resolution of what a publish RIGHT NOW would freeze --
    mirrors assessment_versioning.build_reading_snapshot's query shape
    exactly, so validation always checks the same content publish is about
    to snapshot."""
    passages = supabase.table("reading_passages").select(
        "id, title, part"
    ).eq("test_id", test_id).eq("is_active", True).execute().data
    pids = [p["id"] for p in passages]
    questions = supabase.table("questions").select(
        "id, passage_id, type, content, options, correct_answer"
    ).in_("passage_id", pids).execute().data if pids else []

    questions_by_passage: Dict[int, List[dict]] = {}
    for q in questions:
        questions_by_passage.setdefault(q["passage_id"], []).append({
            "question_id": q["id"],
            "type": "short_answer" if q.get("type") == "short_answer" else "mcq",
            "content": q.get("content"),
            "options": json.loads(q["options"]) if q.get("options") else [],
            "correct_answer": q.get("correct_answer"),
        })

    passage_dicts = [{"passage_id": p["id"], "title": p.get("title", ""), "part": p.get("part")} for p in passages]
    errors, warnings = _validate_reading_content(passage_dicts, questions_by_passage)
    return _result(errors, warnings)


# ── LISTENING ──────────────────────────────────────────────────────────

def _validate_listening_content(
    sections: List[dict], questions_by_section: Dict[int, List[dict]],
) -> Tuple[List[dict], List[dict]]:
    errors: List[dict] = []
    warnings: List[dict] = []

    parts_present = {s.get("part") for s in sections}
    for part in _REQUIRED_PARTS:
        if part not in parts_present:
            errors.append(_err("missing_part", f"part:{part}", f"Part {part} is required but has no section"))

    for s in sections:
        part = s.get("part")
        sid = s.get("section_id")
        if part not in _REQUIRED_PARTS:
            errors.append(_err(
                "invalid_part", f"section:{sid}",
                f"Section {sid} has an invalid part '{part}'",
                {"section_id": sid, "part": part},
            ))
        if not (s.get("audio_url") or "").strip():
            errors.append(_err(
                "missing_audio", f"section:{sid}",
                f"Section \"{s.get('title', '')}\" has no audio",
                {"section_id": sid},
            ))
        errors.extend(_check_questions(
            questions_by_section.get(sid, []),
            f"section:{sid}",
            f"Section \"{s.get('title', '')}\"",
        ))

    for part in _REQUIRED_PARTS:
        if part in parts_present and not any(s.get("part") == part for s in sections):
            warnings.append(_err("part_empty", f"part:{part}", f"Part {part} has no active section"))

    return errors, warnings


def validate_listening_test(supabase, test_id: int) -> Dict[str, Any]:
    sections = supabase.table("listening_sections").select(
        "id, title, part, audio_url"
    ).eq("test_id", test_id).eq("is_active", True).execute().data
    sids = [s["id"] for s in sections]
    questions = supabase.table("questions").select(
        "id, section_id, type, content, options, correct_answer"
    ).in_("section_id", sids).execute().data if sids else []

    questions_by_section: Dict[int, List[dict]] = {}
    for q in questions:
        questions_by_section.setdefault(q["section_id"], []).append({
            "question_id": q["id"],
            "type": "short_answer" if q.get("type") == "short_answer" else "mcq",
            "content": q.get("content"),
            "options": json.loads(q["options"]) if q.get("options") else [],
            "correct_answer": q.get("correct_answer"),
        })

    section_dicts = [
        {"section_id": s["id"], "title": s.get("title", ""), "part": s.get("part"), "audio_url": s.get("audio_url")}
        for s in sections
    ]
    errors, warnings = _validate_listening_content(section_dicts, questions_by_section)
    return _result(errors, warnings)


# ── MOCK ───────────────────────────────────────────────────────────────

def _is_blank(value: Any) -> bool:
    """nurse_card/interlocutor_card/scoring_criteria are JSONB (dict, default
    '{}') -- not strings -- so "blank" means None, an empty/whitespace
    string, or an empty dict/list, not falsy-in-general (0/False are never
    stored here, but treating only these three shapes as blank keeps this
    from misfiring on some future scalar field)."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (dict, list)):
        return len(value) == 0
    return False


def _validate_scenario(row: Optional[dict], role: str, required_fields: List[str]) -> List[dict]:
    """role: 'writing_scenario' or 'speaking_scenario_1'/'speaking_scenario_2' --
    used as the error field prefix so the frontend can point at the right slot."""
    if not row:
        return [_err("slot_empty", role, f"{role.replace('_', ' ').title()} is missing")]
    errors: List[dict] = []
    if not row.get("is_active"):
        errors.append(_err("scenario_inactive", role, f"{role.replace('_', ' ').title()} is not active", {"scenario_id": row.get("id")}))
    for field in required_fields:
        if _is_blank(row.get(field)):
            errors.append(_err(
                "scenario_missing_field", role,
                f"{role.replace('_', ' ').title()} is missing {field.replace('_', ' ')}",
                {"scenario_id": row.get("id"), "field": field},
            ))
    return errors


def validate_mock_test(supabase, mock_test_id: int) -> Dict[str, Any]:
    """Composes Reading/Listening's own validators against the pack's picks
    (never a second implementation of those rules), plus Mock-specific
    checks: all 5 slots filled, referenced Reading/Listening each already
    have a published immutable version, Writing/Speaking scenarios active
    with non-empty required fields, the two Speaking scenarios distinct."""
    errors: List[dict] = []
    warnings: List[dict] = []

    pack = supabase.table("mock_tests").select("*").eq("id", mock_test_id).execute().data
    if not pack:
        return _result([_err("not_found", "mock_test", "Mock Test pack not found")], [])
    p = pack[0]

    reading_id = p.get("reading_test_id")
    listening_id = p.get("listening_test_id")
    writing_id = p.get("writing_scenario_id")
    speaking_id_1 = p.get("speaking_scenario_id_1")
    speaking_id_2 = p.get("speaking_scenario_id_2")

    for slot, val in [
        ("reading_test", reading_id), ("listening_test", listening_id), ("writing_scenario", writing_id),
        ("speaking_scenario_1", speaking_id_1), ("speaking_scenario_2", speaking_id_2),
    ]:
        if val is None:
            errors.append(_err("slot_empty", slot, f"{slot.replace('_', ' ').title()} slot is empty"))

    if reading_id is not None:
        reading_result = validate_reading_test(supabase, reading_id)
        for e in reading_result["errors"]:
            errors.append({**e, "field": f"reading_test.{e['field']}"})
        if not reading_result["valid"]:
            errors.append(_err("reading_test_invalid", "reading_test", "Referenced Reading test fails its own validation"))
        if latest_version_id(supabase, "reading_test_versions", "reading_test_id", reading_id) is None:
            errors.append(_err("reading_unpublished", "reading_test", "Referenced Reading test has no published version yet"))

    if listening_id is not None:
        listening_result = validate_listening_test(supabase, listening_id)
        for e in listening_result["errors"]:
            errors.append({**e, "field": f"listening_test.{e['field']}"})
        if not listening_result["valid"]:
            errors.append(_err("listening_test_invalid", "listening_test", "Referenced Listening test fails its own validation"))
        if latest_version_id(supabase, "listening_test_versions", "listening_test_id", listening_id) is None:
            errors.append(_err("listening_unpublished", "listening_test", "Referenced Listening test has no published version yet"))

    scenario_ids = [i for i in (writing_id, speaking_id_1, speaking_id_2) if i is not None]
    scenarios_by_id: Dict[int, dict] = {}
    if scenario_ids:
        rows = supabase.table("scenarios").select(
            "id, is_active, nurse_card, interlocutor_card, scoring_criteria"
        ).in_("id", scenario_ids).execute().data
        scenarios_by_id = {r["id"]: r for r in rows}

    if writing_id is not None:
        errors.extend(_validate_scenario(scenarios_by_id.get(writing_id), "writing_scenario", ["nurse_card", "scoring_criteria"]))

    if speaking_id_1 is not None:
        errors.extend(_validate_scenario(scenarios_by_id.get(speaking_id_1), "speaking_scenario_1", ["nurse_card", "interlocutor_card", "scoring_criteria"]))
    if speaking_id_2 is not None:
        errors.extend(_validate_scenario(scenarios_by_id.get(speaking_id_2), "speaking_scenario_2", ["nurse_card", "interlocutor_card", "scoring_criteria"]))

    if speaking_id_1 is not None and speaking_id_2 is not None and speaking_id_1 == speaking_id_2:
        errors.append(_err(
            "duplicate_speaking_scenario", "speaking_scenario_2",
            "The two Speaking scenarios must be different", {"scenario_id": speaking_id_1},
        ))

    return _result(errors, warnings)


if __name__ == "__main__":
    # ponytail: smallest runnable self-check for the pure cores -- not a
    # substitute for backend/tests/test_assessment_validation.py, just a
    # fast sanity gate on the branch logic itself.
    ok_passages = [{"passage_id": 1, "title": "P1", "part": "A"}, {"passage_id": 2, "title": "P2", "part": "B"}, {"passage_id": 3, "title": "P3", "part": "C"}]
    ok_questions = {
        1: [{"question_id": 10, "type": "short_answer", "content": "q1", "options": [], "correct_answer": "x"}],
        2: [{"question_id": 20, "type": "mcq", "content": "q2", "options": ["a", "b"], "correct_answer": "a"}],
        3: [{"question_id": 30, "type": "mcq", "content": "q3", "options": ["a", "b"], "correct_answer": "a"}],
    }
    errors, warnings = _validate_reading_content(ok_passages, ok_questions)
    assert errors == [], errors

    missing_part_errors, _ = _validate_reading_content(ok_passages[:2], {1: ok_questions[1], 2: ok_questions[2]})
    assert any(e["code"] == "missing_part" for e in missing_part_errors)

    blank_answer_errors, _ = _validate_reading_content(ok_passages, {**ok_questions, 2: [{"question_id": 20, "type": "mcq", "content": "q2", "options": ["a", "b"], "correct_answer": ""}]})
    assert any(e["code"] == "blank_answer" for e in blank_answer_errors)

    dangling_errors, _ = _validate_reading_content(ok_passages, {**ok_questions, 2: [{"question_id": 20, "type": "mcq", "content": "q2", "options": ["a", "b"], "correct_answer": "c"}]})
    assert any(e["code"] == "dangling_answer" for e in dangling_errors)

    dup_option_errors, _ = _validate_reading_content(ok_passages, {**ok_questions, 2: [{"question_id": 20, "type": "mcq", "content": "q2", "options": ["a", "a"], "correct_answer": "a"}]})
    assert any(e["code"] == "duplicate_option" for e in dup_option_errors)

    dup_text_errors, _ = _validate_reading_content(ok_passages, {**ok_questions, 2: [
        {"question_id": 20, "type": "mcq", "content": "same", "options": ["a", "b"], "correct_answer": "a"},
        {"question_id": 21, "type": "mcq", "content": "same", "options": ["a", "b"], "correct_answer": "a"},
    ]})
    assert any(e["code"] == "duplicate_question_text" for e in dup_text_errors)

    ok_sections = [
        {"section_id": 1, "title": "S1", "part": "A", "audio_url": "https://x/1.mp3"},
        {"section_id": 2, "title": "S2", "part": "B", "audio_url": "https://x/2.mp3"},
        {"section_id": 3, "title": "S3", "part": "C", "audio_url": "https://x/3.mp3"},
    ]
    ok_l_questions = {
        1: [{"question_id": 10, "type": "short_answer", "content": "q1", "options": [], "correct_answer": "x"}],
        2: [{"question_id": 20, "type": "mcq", "content": "q2", "options": ["a", "b"], "correct_answer": "a"}],
        3: [{"question_id": 30, "type": "mcq", "content": "q3", "options": ["a", "b"], "correct_answer": "a"}],
    }
    l_errors, _ = _validate_listening_content(ok_sections, ok_l_questions)
    assert l_errors == [], l_errors

    no_audio_errors, _ = _validate_listening_content(
        [{**ok_sections[0], "audio_url": None}] + ok_sections[1:], ok_l_questions,
    )
    assert any(e["code"] == "missing_audio" for e in no_audio_errors)

    print("assessment_validation.py self-check: all assertions passed")
