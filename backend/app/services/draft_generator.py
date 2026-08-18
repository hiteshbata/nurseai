"""AI Draft Generator (RC3.2): builds a prompt, calls the shared
content_draft_generation purpose, validates the response, and returns an
unpersisted draft. Never writes to production content tables and never
publishes -- app/services/draft_store.py is the only thing this sprint is
allowed to persist to.
"""
import logging
import re
from typing import Any, Dict, List, Optional

from app.core.supabase import get_supabase
from app.routers.reading import _split_part_a_sections
from app.services import ai_registry
from app.services import prompt_builder
from app.services.ai_scoring import _call_ai

logger = logging.getLogger(__name__)

PURPOSE = "content_draft_generation"

# Required top-level keys per module, checked after JSON parsing succeeds.
_REQUIRED_FIELDS: Dict[str, List[str]] = {
    "speaking": ["title", "setting", "nurse_card", "interlocutor_card"],
    "reading": ["title", "body", "questions"],
    "listening": ["title", "transcript", "questions"],
    "writing": ["title", "case_notes", "task"],
    "vocab": ["topic", "items"],
    "grammar": ["topic", "explanation"],
}

# Fields that must be a non-empty list, on top of the presence check above.
_REQUIRED_NONEMPTY_LISTS: Dict[str, List[str]] = {
    "reading": ["questions"],
    "listening": ["transcript", "questions"],
    "vocab": ["items"],
}

# module -> (production table, extra eq filters) for the best-effort
# duplicate-title check. Grammar/vocab have no production content table
# (see content_studio.py) so duplicate checking is skipped for them --
# this only affects the warning, never blocks generation or saving.
_DUPLICATE_CHECK_TABLE = {
    "speaking": ("scenarios", {"module": "speaking"}),
    "writing": ("scenarios", {"module": "writing"}),
    "reading": ("reading_passages", {}),
    "listening": ("listening_sections", {}),
}

_TITLE_FIELD = {
    "speaking": "title", "reading": "title", "listening": "title", "writing": "title",
    "vocab": "topic", "grammar": "topic",
}

# Reading (full passage + questions), Listening (full transcript + questions),
# and Grammar (explanation + practice questions) routinely exceed the default
# budget and got cut off mid-JSON -- confirmed via finish_reason=MAX_TOKENS on
# the raw AI response. Speaking/Writing/Vocab's schemas fit comfortably under
# the default and are left untouched.
_MAX_TOKENS_OVERRIDE = {"reading": 6000, "listening": 6000, "grammar": 6000}
_DEFAULT_MAX_TOKENS = 3000

# Part A production incident: finish_reason=MAX_TOKENS, response truncated
# mid-questions-array at the module-level 6000 ceiling above. Part A is
# structurally the largest Reading generation -- 4 texts + 20 questions --
# unlike Part B (6 short extracts) and Part C (2 texts), which fit 6000
# comfortably and are deliberately left there.
_READING_PART_MAX_TOKENS_OVERRIDE = {"A": 9000}


def _resolve_max_tokens(module: str, part: Optional[str]) -> int:
    if module == "reading" and part in _READING_PART_MAX_TOKENS_OVERRIDE:
        return _READING_PART_MAX_TOKENS_OVERRIDE[part]
    return _MAX_TOKENS_OVERRIDE.get(module, _DEFAULT_MAX_TOKENS)


class DraftGenerationError(Exception):
    """A friendly, user-facing generation failure (AI outage, malformed
    response, empty response). Caught by the router and returned as a
    per-item error instead of a 500."""


# Locked Part A contract (Phase 3B-3): 4 texts, 20 questions, Q1-5 matching
# MCQ over the four text labels, Q6-20 short_answer. Structural only -- no
# content-quality judgement (that's a later phase). Question numbering has
# no stored field of its own; array order IS the numbering (see
# `questions` in _READING_PART_A_SCHEMA / reading_passages+questions
# tables), so "Q1-5"/"Q6-20" below means list position, not a DB column.
_PART_A_MATCH_OPTIONS = ["Text A", "Text B", "Text C", "Text D"]
_PART_A_TEXT_LABELS = ("A", "B", "C", "D")
_PART_A_QUESTION_COUNT = 20
_PART_A_MATCH_COUNT = 5  # Q1-5

# Phase 3B-10: Gemini occasionally leaves a stray space before a
# sentence-completion question's terminal punctuation ("...below ."). Only
# matches whitespace directly touching a terminal mark that's followed by
# whitespace/end-of-string, so decimals ("0.5 mg"), ranges, and mid-sentence
# abbreviations never have that whitespace to begin with -- untouched by
# construction, not by exclusion list.
_TERMINAL_PUNCT_WHITESPACE = re.compile(r"[ \t]+([.?!])(?=\s|$)")


def _strip_terminal_punct_whitespace(text: str) -> str:
    return _TERMINAL_PUNCT_WHITESPACE.sub(r"\1", text)


def _normalize_part_a_question_content(content: Dict[str, Any]) -> None:
    """Mutates content["questions"] in place, cleaning only each question's
    `content` string. Body (Texts A-D), options, and correct_answer are
    never touched -- this is a cosmetic fix to AI-generated question text,
    not a content transform."""
    questions = content.get("questions")
    if not isinstance(questions, list):
        return
    for q in questions:
        if isinstance(q, dict) and isinstance(q.get("content"), str):
            q["content"] = _strip_terminal_punct_whitespace(q["content"])


def _validate_reading_part_a(content: Dict[str, Any]) -> List[str]:
    """Pure structural check against the locked Part A contract. Takes the
    freshly-generated (unpersisted) draft dict -- same shape _validate()
    already has in hand, no supabase involved."""
    errors: List[str] = []

    sections = _split_part_a_sections(str(content.get("body") or ""))
    labels = [s["label"] for s in sections]
    for label in _PART_A_TEXT_LABELS:
        count = labels.count(label)
        if count == 0:
            errors.append(f"Body is missing Text {label}.")
        elif count > 1:
            errors.append(f"Body has {count} duplicate Text {label} headers.")

    questions = content.get("questions")
    if not isinstance(questions, list):
        errors.append("'questions' must be a list.")
        return errors

    if len(questions) != _PART_A_QUESTION_COUNT:
        errors.append(f"Must contain exactly {_PART_A_QUESTION_COUNT} questions; received {len(questions)}.")

    seen_content: Dict[str, int] = {}
    for i, q in enumerate(questions):
        n = i + 1
        qtype = q.get("type") if isinstance(q, dict) else None
        options = q.get("options") if isinstance(q, dict) else None
        answer = str((q.get("correct_answer") if isinstance(q, dict) else "") or "").strip()
        qcontent = str((q.get("content") if isinstance(q, dict) else "") or "").strip()
        if qcontent:
            seen_content[qcontent] = seen_content.get(qcontent, 0) + 1

        if n <= _PART_A_MATCH_COUNT:
            if qtype != "mcq":
                errors.append(f"Question {n} must be type 'mcq' (matching); got '{qtype}'.")
            if options != _PART_A_MATCH_OPTIONS:
                errors.append(f"Question {n} options must be exactly {_PART_A_MATCH_OPTIONS}; got {options}.")
            if answer not in _PART_A_MATCH_OPTIONS:
                errors.append(f"Question {n} correct_answer must be one of {_PART_A_MATCH_OPTIONS}; got '{answer}'.")
        else:
            if qtype != "short_answer":
                errors.append(f"Question {n} must be type 'short_answer'; got '{qtype}'.")
            if options != []:
                errors.append(f"Question {n} options must be an empty array; got {options}.")
            if not answer:
                errors.append(f"Question {n} must have a non-empty correct_answer.")

    for text, count in seen_content.items():
        if count > 1:
            errors.append(f"Duplicate question text appears {count} times: \"{text[:80]}\"")

    return errors



# Locked Part B contract (Phase 4A): 6 independent short extracts, each its
# own passage with exactly 1 mcq question over exactly 3 options. Structural
# only, same spirit as _validate_reading_part_a. Content shape is a
# "passages" container, not the flat title/body/questions every other module
# (and Part A) uses -- see prompt_builder.py's _READING_PART_B_SCHEMA comment
# for why: one Part B generation is six independent production rows, not one.
# Publishing those 6 rows from a single draft (draft_publisher.py currently
# assumes Model A -- one draft, at most one production row) is out of scope
# for this phase; this validator only gates what generate_draft() returns.
_PART_B_PASSAGE_COUNT = 6
_PART_B_OPTION_COUNT = 3


def _validate_reading_part_b(content: Dict[str, Any]) -> List[str]:
    """Pure structural check against the locked Part B contract. Takes the
    freshly-generated (unpersisted) draft dict -- same shape _validate()
    already has in hand, no supabase involved."""
    errors: List[str] = []

    if content.get("part") != "B":
        errors.append(f"'part' must be 'B'; got {content.get('part')!r}.")

    passages = content.get("passages")
    if not isinstance(passages, list):
        errors.append("'passages' must be a list.")
        return errors

    if len(passages) != _PART_B_PASSAGE_COUNT:
        errors.append(f"Must contain exactly {_PART_B_PASSAGE_COUNT} passages; received {len(passages)}.")

    seen_content: Dict[str, int] = {}
    for i, p in enumerate(passages):
        n = i + 1
        if not isinstance(p, dict):
            errors.append(f"Passage {n} must be an object.")
            continue

        if not str(p.get("title") or "").strip():
            errors.append(f"Passage {n} is missing a title.")
        if not str(p.get("body") or "").strip():
            errors.append(f"Passage {n} is missing a body.")

        questions = p.get("questions")
        if not isinstance(questions, list):
            errors.append(f"Passage {n} 'questions' must be a list.")
            continue
        if len(questions) != 1:
            errors.append(f"Passage {n} must have exactly 1 question; got {len(questions)}.")

        for j, q in enumerate(questions):
            label = f"Passage {n} question {j + 1}"
            if not isinstance(q, dict):
                errors.append(f"{label} must be an object.")
                continue

            qtype = q.get("type")
            if qtype != "mcq":
                errors.append(f"{label} must be type 'mcq'; got {qtype!r}.")

            options = q.get("options")
            if not isinstance(options, list) or len(options) != _PART_B_OPTION_COUNT:
                errors.append(f"{label} must have exactly {_PART_B_OPTION_COUNT} options; got {options!r}.")
            else:
                stripped = [str(o).strip() for o in options]
                if any(not o for o in stripped):
                    errors.append(f"{label} has an empty option.")
                if len(set(stripped)) != len(stripped):
                    errors.append(f"{label} has duplicate options.")

            answer = str(q.get("correct_answer") or "").strip()
            if not answer:
                errors.append(f"{label} must have a non-empty correct_answer.")
            elif isinstance(options, list) and answer not in options:
                errors.append(f"{label} correct_answer must exactly match one of its options; got '{answer}'.")

            qcontent = str(q.get("content") or "").strip()
            if qcontent:
                seen_content[qcontent] = seen_content.get(qcontent, 0) + 1

    for text, count in seen_content.items():
        if count > 1:
            errors.append(f"Duplicate question text appears {count} times: \"{text[:80]}\"")

    return errors


# Locked Part C contract (Phase 4C-3): 2 independent long-form texts, each
# its own passage with exactly 8 mcq questions over exactly 4 options.
# Structural only, same spirit as _validate_reading_part_a/_b. Content shape
# ("texts": [...]) mirrors Part B's "passages" container -- see
# prompt_builder.py's _READING_PART_C_SCHEMA comment for why: one Part C
# generation is two independent production rows, not one.
_PART_C_TEXT_COUNT = 2
_PART_C_QUESTIONS_PER_TEXT = 8
_PART_C_OPTION_COUNT = 4


def _validate_reading_part_c(content: Dict[str, Any]) -> List[str]:
    """Pure structural check against the locked Part C contract. Takes the
    freshly-generated (unpersisted) draft dict -- same shape _validate()
    already has in hand, no supabase involved."""
    errors: List[str] = []

    if content.get("part") != "C":
        errors.append(f"'part' must be 'C'; got {content.get('part')!r}.")

    texts = content.get("texts")
    if not isinstance(texts, list):
        errors.append("'texts' must be a list.")
        return errors

    if len(texts) != _PART_C_TEXT_COUNT:
        errors.append(f"Must contain exactly {_PART_C_TEXT_COUNT} texts; received {len(texts)}.")

    seen_content: Dict[str, int] = {}
    for i, t in enumerate(texts):
        n = i + 1
        if not isinstance(t, dict):
            errors.append(f"Text {n} must be an object.")
            continue

        if not str(t.get("title") or "").strip():
            errors.append(f"Text {n} is missing a title.")
        if not str(t.get("body") or "").strip():
            errors.append(f"Text {n} is missing a body.")

        questions = t.get("questions")
        if not isinstance(questions, list):
            errors.append(f"Text {n} 'questions' must be a list.")
            continue
        if len(questions) != _PART_C_QUESTIONS_PER_TEXT:
            errors.append(f"Text {n} must have exactly {_PART_C_QUESTIONS_PER_TEXT} questions; got {len(questions)}.")

        for j, q in enumerate(questions):
            label = f"Text {n} question {j + 1}"
            if not isinstance(q, dict):
                errors.append(f"{label} must be an object.")
                continue

            qtype = q.get("type")
            if qtype != "mcq":
                errors.append(f"{label} must be type 'mcq'; got {qtype!r}.")

            options = q.get("options")
            if not isinstance(options, list) or len(options) != _PART_C_OPTION_COUNT:
                errors.append(f"{label} must have exactly {_PART_C_OPTION_COUNT} options; got {options!r}.")
            else:
                stripped = [str(o).strip() for o in options]
                if any(not o for o in stripped):
                    errors.append(f"{label} has an empty option.")
                if len(set(stripped)) != len(stripped):
                    errors.append(f"{label} has duplicate options.")

            answer = str(q.get("correct_answer") or "").strip()
            if not answer:
                errors.append(f"{label} must have a non-empty correct_answer.")
            elif isinstance(options, list) and answer not in options:
                errors.append(f"{label} correct_answer must exactly match one of its options; got '{answer}'.")

            qcontent = str(q.get("content") or "").strip()
            if qcontent:
                seen_content[qcontent] = seen_content.get(qcontent, 0) + 1

    for text, count in seen_content.items():
        if count > 1:
            errors.append(f"Duplicate question text appears {count} times: \"{text[:80]}\"")

    return errors


def _validate(module: str, content: Dict[str, Any]) -> List[str]:
    if module == "reading" and content.get("part") == "C":
        # Part C's shape ("texts": [...]) doesn't have top-level
        # body/questions, so it must bypass the generic required-field check
        # below entirely, same reason Part B does.
        part_c_errors = _validate_reading_part_c(content)
        if part_c_errors:
            raise DraftGenerationError(
                "Generated Part C content violates the locked contract: " + " ".join(part_c_errors)
            )
        return []

    if module == "reading" and content.get("part") == "B":
        # Part B's shape ("passages": [...]) doesn't have top-level
        # body/questions, so it must bypass the generic required-field check
        # below entirely rather than fail it before this branch even runs.
        part_b_errors = _validate_reading_part_b(content)
        if part_b_errors:
            raise DraftGenerationError(
                "Generated Part B content violates the locked contract: " + " ".join(part_b_errors)
            )
        return []

    required = _REQUIRED_FIELDS.get(module, [])
    missing = [f for f in required if not content.get(f)]
    if missing:
        raise DraftGenerationError(f"AI response is missing required field(s): {', '.join(missing)}")

    for field in _REQUIRED_NONEMPTY_LISTS.get(module, []):
        value = content.get(field)
        if not isinstance(value, list) or not value:
            raise DraftGenerationError(f"AI response has an empty '{field}' list")

    if module == "reading" and content.get("part") == "A":
        part_a_errors = _validate_reading_part_a(content)
        if part_a_errors:
            raise DraftGenerationError(
                "Generated Part A content violates the locked contract: " + " ".join(part_a_errors)
            )

    return []


def _check_duplicate_title(module: str, title: str) -> Optional[str]:
    mapping = _DUPLICATE_CHECK_TABLE.get(module)
    if not mapping or not title:
        return None
    table, filters = mapping
    supabase = get_supabase()
    query = supabase.table(table).select("id").ilike("title", title.strip())
    for col, val in filters.items():
        query = query.eq(col, val)
    existing = query.limit(1).execute().data
    if existing:
        return f'A {module} item titled "{title}" already exists in production content -- consider a different topic or angle.'
    return None


async def generate_draft(
    module: str,
    difficulty: str,
    specialty: str,
    topic: str,
    objectives: Optional[str] = None,
    instructions: Optional[str] = None,
    admin_user_id: str = "",
    part: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate one draft. Returns a dict ready for the Preview UI / Save
    Draft call. Raises DraftGenerationError on any AI or validation failure
    -- callers should catch it and surface result.error rather than a 500,
    so one bad draft in a batch doesn't fail the whole request."""
    system_prompt, user_prompt = prompt_builder.build_prompt(module, difficulty, specialty, topic, objectives, instructions, part=part)

    try:
        cfg = await ai_registry.get_model_config(PURPOSE)
        model_used = f"{cfg.provider}/{cfg.model_name}"
    except ai_registry.PurposeNotConfigured:
        model_used = None

    result = await _call_ai(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        purpose=PURPOSE,
        max_tokens=_resolve_max_tokens(module, part),
        json_mode=True,
        temperature=0.4,
        user_id=admin_user_id,
        timeout=90.0,
    )
    if result.get("provider_failure"):
        raise DraftGenerationError("The AI service is temporarily unavailable. Please try again.")
    if "raw_feedback" in result:
        # DIAGNOSTIC (local only): the bounded parse-failure record (provider,
        # model, finish_reason, length, error position/context, response
        # hash) is already logged by ai_scoring._try_parse_json as
        # [SCORING_PARSE_FAILURE] -- this just marks where in the request
        # flow it surfaced. Deliberately no response content here: no
        # raw_head, no full raw_feedback -- that content-bearing diagnostic
        # exists in exactly one place (the bounded record above it), not
        # duplicated across log lines.
        logger.warning("[draft_generator] JSON parse failed | module=%s", module)
        raise DraftGenerationError("The AI response could not be read as valid content. Please try again.")

    content = {k: v for k, v in result.items() if k != "finish_reason"}
    if not content:
        raise DraftGenerationError("The AI returned an empty response.")

    if module == "reading" and content.get("part") == "A":
        _normalize_part_a_question_content(content)

    warnings = _validate(module, content)

    title = str(content.get(_TITLE_FIELD.get(module, "title"), "")).strip()
    dup_warning = _check_duplicate_title(module, title)
    if dup_warning:
        warnings.append(dup_warning)

    return {
        "generated_content": content,
        "metadata": {
            "difficulty": difficulty,
            "specialty": specialty,
            "topic": topic,
            "objectives": objectives,
            "instructions": instructions,
        },
        "prompt": {"system_prompt": system_prompt, "user_prompt": user_prompt},
        "validation_warnings": warnings,
        "ai_title": title or None,
        "model_used": model_used,
    }
