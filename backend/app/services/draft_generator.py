"""AI Draft Generator (RC3.2): builds a prompt, calls the shared
content_draft_generation purpose, validates the response, and returns an
unpersisted draft. Never writes to production content tables and never
publishes -- app/services/draft_store.py is the only thing this sprint is
allowed to persist to.
"""
import difflib
import logging
import re
from datetime import date
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
    "blog": ["title", "body", "excerpt"],
}

# Fields that must be a non-empty list, on top of the presence check above.
_REQUIRED_NONEMPTY_LISTS: Dict[str, List[str]] = {
    "reading": ["questions"],
    "listening": ["transcript", "questions"],
    "vocab": ["items"],
}

# W2 structured Writing contract (kept in sync with prompt_builder.WRITING_LETTER_TYPES).
# Only the four types evidenced by the reference OET Nursing Writing samples.
_WRITING_LETTER_TYPES = ("referral", "discharge", "transfer", "ongoing_care")

# Fixed per the OET Nursing Writing sub-test format across all six reference
# samples -- never varies per case, so it's applied here rather than asked of
# the AI (one less thing that can come back malformed).
_WRITING_REQUIREMENTS_DEFAULT: Dict[str, Any] = {
    "reading_minutes": 5,
    "writing_minutes": 40,
    "target_word_count": "180-200",
    "letter_format": True,
    "no_note_form": True,
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
# the raw AI response. Speaking/Vocab's schemas fit comfortably under the
# default and are left untouched.
#
# W3.2: Writing (W2 structured contract) moved into this tier too -- the
# schema now duplicates case notes twice (case_notes_structured AND the
# rendered case_notes text block) plus key_points/writing_requirements,
# and generation was observed truncating mid-JSON (finish_reason=MAX_TOKENS)
# under the old 3000 default. Same 6000 ceiling as its schema-size peers,
# not a bespoke budget.
# Blog targets an 800-1200 word Markdown body plus title/excerpt -- same
# ceiling as its long-form schema peers above, not a bespoke budget.
_MAX_TOKENS_OVERRIDE = {"reading": 6000, "listening": 6000, "grammar": 6000, "writing": 6000, "blog": 6000}
_DEFAULT_MAX_TOKENS = 3000

# Part A production incident: finish_reason=MAX_TOKENS, response truncated
# mid-questions-array at the module-level 6000 ceiling above. Part A is
# structurally the largest Reading generation -- 4 texts + 20 questions --
# unlike Part B (6 short extracts) and Part C (2 texts), which fit 6000
# comfortably and are deliberately left there.
_READING_PART_MAX_TOKENS_OVERRIDE = {"A": 9000}

# Listening Part A/B/C (Phase 3B) all pack 2-6 extracts, each with its own
# transcript AND a note-completion body (A) or questions (all), well past
# Reading's incident threshold above -- same defensive bump for all three
# rather than waiting for the same truncation to reproduce per-part.
_LISTENING_PART_MAX_TOKENS_OVERRIDE = {"A": 9000, "B": 9000, "C": 9000}


def _resolve_max_tokens(module: str, part: Optional[str]) -> int:
    if module == "reading" and part in _READING_PART_MAX_TOKENS_OVERRIDE:
        return _READING_PART_MAX_TOKENS_OVERRIDE[part]
    if module == "listening" and part in _LISTENING_PART_MAX_TOKENS_OVERRIDE:
        return _LISTENING_PART_MAX_TOKENS_OVERRIDE[part]
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


# Locked Listening contract (Phase 3B): extracts[] with a canonical
# [{speaker, text}] transcript per extract, mirroring the Reading Part B/C
# multi-slot shape (_validate_reading_part_b/_c above) over audio instead of
# text. One generation is N independent production rows (listening_sections),
# not one -- see draft_publisher.py's Part A/B/C payload builders.
_LISTENING_PART_A_EXTRACT_COUNT = 2
_LISTENING_PART_A_QUESTIONS_PER_EXTRACT = 12
_LISTENING_PART_A_PREP_SECONDS = 30

_LISTENING_PART_B_EXTRACT_COUNT = 6
_LISTENING_PART_B_OPTION_COUNT = 3
_LISTENING_PART_B_PREP_SECONDS = 15

_LISTENING_PART_C_EXTRACT_COUNT = 2
_LISTENING_PART_C_QUESTIONS_PER_EXTRACT = 6
_LISTENING_PART_C_OPTION_COUNT = 3
_LISTENING_PART_C_PREP_SECONDS = 90
_LISTENING_AUDIO_MODES = ("dialogue", "monologue")


def _non_empty_transcript(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def _validate_listening_part_a(content: Dict[str, Any]) -> List[str]:
    """Pure structural check against the locked Listening Part A contract:
    2 extracts, 12 short_answer questions each (24 total), a note-completion
    body per extract, prep_seconds=30, audio_mode="dialogue"."""
    errors: List[str] = []

    if content.get("part") != "A":
        errors.append(f"'part' must be 'A'; got {content.get('part')!r}.")
    if content.get("prep_seconds") != _LISTENING_PART_A_PREP_SECONDS:
        errors.append(f"'prep_seconds' must be {_LISTENING_PART_A_PREP_SECONDS}; got {content.get('prep_seconds')!r}.")
    if content.get("audio_mode") != "dialogue":
        errors.append(f"'audio_mode' must be 'dialogue'; got {content.get('audio_mode')!r}.")

    extracts = content.get("extracts")
    if not isinstance(extracts, list):
        errors.append("'extracts' must be a list.")
        return errors
    if len(extracts) != _LISTENING_PART_A_EXTRACT_COUNT:
        errors.append(f"Must contain exactly {_LISTENING_PART_A_EXTRACT_COUNT} extracts; received {len(extracts)}.")

    seen_content: Dict[str, int] = {}
    for i, ex in enumerate(extracts):
        n = i + 1
        if not isinstance(ex, dict):
            errors.append(f"Extract {n} must be an object.")
            continue

        if not str(ex.get("title") or "").strip():
            errors.append(f"Extract {n} is missing a title.")
        if not _non_empty_transcript(ex.get("transcript")):
            errors.append(f"Extract {n} must have a non-empty transcript.")
        if not str(ex.get("body") or "").strip():
            errors.append(f"Extract {n} is missing a body (note-completion template).")

        questions = ex.get("questions")
        if not isinstance(questions, list):
            errors.append(f"Extract {n} 'questions' must be a list.")
            continue
        if len(questions) != _LISTENING_PART_A_QUESTIONS_PER_EXTRACT:
            errors.append(f"Extract {n} must have exactly {_LISTENING_PART_A_QUESTIONS_PER_EXTRACT} questions; got {len(questions)}.")

        for j, q in enumerate(questions):
            label = f"Extract {n} question {j + 1}"
            if not isinstance(q, dict):
                errors.append(f"{label} must be an object.")
                continue

            if q.get("type") != "short_answer":
                errors.append(f"{label} must be type 'short_answer'; got {q.get('type')!r}.")
            if q.get("options") not in (None, []):
                errors.append(f"{label} options must be an empty array; got {q.get('options')!r}.")

            answer = str(q.get("correct_answer") or "").strip()
            if not answer:
                errors.append(f"{label} must have a non-empty correct_answer.")

            accepted = q.get("accepted_answers")
            if accepted is not None and (
                not isinstance(accepted, list) or not all(isinstance(a, str) and a.strip() for a in accepted)
            ):
                errors.append(f"{label} 'accepted_answers' must be a list of non-empty strings.")

            qcontent = str(q.get("content") or "").strip()
            if qcontent:
                seen_content[qcontent] = seen_content.get(qcontent, 0) + 1

    for text, count in seen_content.items():
        if count > 1:
            errors.append(f"Duplicate question text appears {count} times: \"{text[:80]}\"")

    return errors


def _validate_listening_mcq_extracts(
    content: Dict[str, Any], *, expected_part: str, extract_count: int,
    questions_per_extract: int, option_count: int, expected_prep_seconds: int,
    global_audio_mode: Optional[str],
) -> List[str]:
    """Shared mcq-extract structural check for Listening Part B (global
    audio_mode) and Part C (per-extract audio_mode) -- both are N extracts,
    each with a fixed count of mcq questions over a fixed option count."""
    errors: List[str] = []

    if content.get("part") != expected_part:
        errors.append(f"'part' must be '{expected_part}'; got {content.get('part')!r}.")
    if content.get("prep_seconds") != expected_prep_seconds:
        errors.append(f"'prep_seconds' must be {expected_prep_seconds}; got {content.get('prep_seconds')!r}.")
    if global_audio_mode is not None and content.get("audio_mode") != global_audio_mode:
        errors.append(f"'audio_mode' must be '{global_audio_mode}'; got {content.get('audio_mode')!r}.")

    extracts = content.get("extracts")
    if not isinstance(extracts, list):
        errors.append("'extracts' must be a list.")
        return errors
    if len(extracts) != extract_count:
        errors.append(f"Must contain exactly {extract_count} extracts; received {len(extracts)}.")

    seen_content: Dict[str, int] = {}
    for i, ex in enumerate(extracts):
        n = i + 1
        if not isinstance(ex, dict):
            errors.append(f"Extract {n} must be an object.")
            continue

        if not str(ex.get("title") or "").strip():
            errors.append(f"Extract {n} is missing a title.")
        if not _non_empty_transcript(ex.get("transcript")):
            errors.append(f"Extract {n} must have a non-empty transcript.")
        if global_audio_mode is None and ex.get("audio_mode") not in _LISTENING_AUDIO_MODES:
            errors.append(f"Extract {n} 'audio_mode' must be one of {list(_LISTENING_AUDIO_MODES)}; got {ex.get('audio_mode')!r}.")

        questions = ex.get("questions")
        if not isinstance(questions, list):
            errors.append(f"Extract {n} 'questions' must be a list.")
            continue
        if len(questions) != questions_per_extract:
            errors.append(f"Extract {n} must have exactly {questions_per_extract} questions; got {len(questions)}.")

        for j, q in enumerate(questions):
            label = f"Extract {n} question {j + 1}"
            if not isinstance(q, dict):
                errors.append(f"{label} must be an object.")
                continue

            if q.get("type") != "mcq":
                errors.append(f"{label} must be type 'mcq'; got {q.get('type')!r}.")

            options = q.get("options")
            if not isinstance(options, list) or len(options) != option_count:
                errors.append(f"{label} must have exactly {option_count} options; got {options!r}.")
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


def _validate_listening_part_b(content: Dict[str, Any]) -> List[str]:
    """6 extracts, 1 mcq/3-option question each, prep_seconds=15,
    audio_mode="dialogue" (global)."""
    return _validate_listening_mcq_extracts(
        content, expected_part="B", extract_count=_LISTENING_PART_B_EXTRACT_COUNT,
        questions_per_extract=1, option_count=_LISTENING_PART_B_OPTION_COUNT,
        expected_prep_seconds=_LISTENING_PART_B_PREP_SECONDS, global_audio_mode="dialogue",
    )


def _validate_listening_part_c(content: Dict[str, Any]) -> List[str]:
    """2 extracts, 6 mcq/3-option questions each, prep_seconds=90,
    audio_mode chosen per extract (dialogue or monologue) -- no global value."""
    return _validate_listening_mcq_extracts(
        content, expected_part="C", extract_count=_LISTENING_PART_C_EXTRACT_COUNT,
        questions_per_extract=_LISTENING_PART_C_QUESTIONS_PER_EXTRACT, option_count=_LISTENING_PART_C_OPTION_COUNT,
        expected_prep_seconds=_LISTENING_PART_C_PREP_SECONDS, global_audio_mode=None,
    )


# W3.1: deterministic internal-consistency checks layered on top of the W2
# structural contract above. These read only fields the W2 schema already
# defines (patient/recipient/case_notes_structured/case_notes/task/purpose/
# key_points) -- no new Content Studio field is introduced. Every check is
# additive and opt-in the same way _validate_writing's structural checks are:
# a legacy/partial draft that doesn't carry the fields a given check needs
# simply produces no finding from that check, it never raises on absence.
#
# Deliberately NOT implemented here: "letter_type contradicting task type"
# and "purpose differing materially from task intent" via free-text keyword
# inference. A prototype of both reliably fired on ordinary single-field-
# override test fixtures (e.g. letter_type swapped without also rewriting
# task/purpose prose) -- the false-positive rate from crude keyword matching
# on freeform prose was worse than the signal, and the spec asks for
# conservative flagging of *clear* contradictions only. Revisit if the W2
# schema ever gains a structured field to tag intent instead of inferring it
# from prose.
_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")
_TEXT_DATE_RE = re.compile(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b")


def _find_dates(text: str) -> List[date]:
    """dd/mm/yyyy (or dd-mm-yyyy) and 'dd Month yyyy' -- the two date styles
    that actually show up in OET-style case notes. Anything unparseable is
    silently skipped, never raised -- this is a best-effort extractor over
    free text, not a schema field."""
    found: List[date] = []
    for m in _NUMERIC_DATE_RE.finditer(text):
        try:
            found.append(date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
        except ValueError:
            pass
    for m in _TEXT_DATE_RE.finditer(text):
        month = _MONTHS.get(m.group(2).lower())
        if month:
            try:
                found.append(date(int(m.group(3)), month, int(m.group(1))))
            except ValueError:
                pass
    return found


def _writing_text_fragments(content: Dict[str, Any]) -> List[str]:
    """case_notes_structured items + raw case_notes lines + task + purpose,
    each as its own short fragment -- deliberately fragment-level rather than
    one joined blob, so a keyword like 'admission' only labels the date(s)
    actually sitting in the same note line, not every date anywhere."""
    fragments: List[str] = []
    structured = content.get("case_notes_structured")
    if isinstance(structured, list):
        for section in structured:
            if isinstance(section, dict):
                for item in section.get("items") or []:
                    if isinstance(item, str):
                        fragments.append(item)
    case_notes = content.get("case_notes")
    if isinstance(case_notes, str):
        fragments.extend(line for line in case_notes.splitlines() if line.strip())
    for field in ("task", "purpose"):
        value = content.get(field)
        if isinstance(value, str) and value.strip():
            fragments.append(value)
    return fragments


# Order matters: a fragment matching more than one label (e.g. "Follow-up
# treatment arranged") takes the first label it matches, so a treatment note
# explicitly marked as follow-up lands in follow_up, not treatment -- exactly
# the carve-out the spec asks for ("treatment dates not after discharge
# unless explicitly follow-up").
_DATE_LABEL_KEYWORDS = (
    ("dob", ("dob", "date of birth")),
    ("admission", ("admission", "admitted")),
    ("follow_up", ("follow-up", "follow up", "review appointment")),
    ("discharge", ("discharge", "discharged")),
    ("treatment", ("treatment",)),
)


def _labeled_writing_dates(content: Dict[str, Any]) -> Dict[str, List[date]]:
    buckets: Dict[str, List[date]] = {label: [] for label, _ in _DATE_LABEL_KEYWORDS}
    patient = content.get("patient")
    if isinstance(patient, dict) and patient.get("dob"):
        buckets["dob"].extend(_find_dates(str(patient["dob"])))
    for fragment in _writing_text_fragments(content):
        found = _find_dates(fragment)
        if not found:
            continue
        lower = fragment.lower()
        for label, keywords in _DATE_LABEL_KEYWORDS:
            if any(kw in lower for kw in keywords):
                buckets[label].extend(found)
                break
    return {label: list(dict.fromkeys(ds)) for label, ds in buckets.items()}


def _resolve_writing_reference_date(content: Dict[str, Any], dates: Dict[str, List[date]]) -> Optional[date]:
    """Priority: an explicit reference date if the AI ever supplies one (not
    a schema field today, but harmless to honor if present) > admission date
    > discharge date > nothing -- never falls back to real-world 'today',
    per the spec, since a generated case's internal clock is whatever date
    the case notes themselves establish."""
    explicit = content.get("assumed_today") or content.get("reference_date")
    if isinstance(explicit, str) and explicit.strip():
        found = _find_dates(explicit)
        if found:
            return found[0]
    if dates["admission"]:
        return dates["admission"][0]
    if dates["discharge"]:
        return dates["discharge"][0]
    return None


def _calculate_age(dob: date, reference: date) -> int:
    age = reference.year - dob.year
    if (reference.month, reference.day) < (dob.month, dob.day):
        age -= 1
    return age


# W3.4: the AI repeatedly miscalculated patient.age from a DOB it also
# generated (e.g. DOB 14/03/1946 as of 18/10/2023 -> 78, should be 77) --
# a generation-contract problem, not a validation one. Called from
# generate_draft() only, i.e. only for a freshly generated draft, before
# _validate() runs -- so a derivable age is authoritative for new
# generation while an existing/legacy draft (which never passes through
# here) keeps whatever age it already has, still checked for consistency
# by _validate_writing_age_dob below.
def _derive_writing_patient_age(content: Dict[str, Any]) -> None:
    patient = content.get("patient")
    if not isinstance(patient, dict):
        return
    dob_values = _find_dates(str(patient.get("dob") or ""))
    if len(dob_values) != 1:
        return  # no DOB, or an unparseable/ambiguous one -- nothing to derive from
    reference = _resolve_writing_reference_date(content, _labeled_writing_dates(content))
    if reference is None:
        return
    patient["age"] = str(_calculate_age(dob_values[0], reference))


_AGE_FIELD_RE = re.compile(r"\d{1,3}")
_AGE_TEXT_RE = re.compile(r"\b(\d{1,3})[\s-]*(?:y\.?o\.?|years?[\s-]old)\b", re.IGNORECASE)


def _parse_stated_age(value: Any) -> Optional[int]:
    if value is None:
        return None
    m = _AGE_FIELD_RE.search(str(value))
    return int(m.group()) if m else None


def _ages_in_text(content: Dict[str, Any]) -> set:
    ages = set()
    for fragment in _writing_text_fragments(content):
        for m in _AGE_TEXT_RE.finditer(fragment):
            ages.add(int(m.group(1)))
    return ages


def _validate_writing_age_dob(content: Dict[str, Any]) -> List[str]:
    """DOB/age/reference-date consistency (spec section 1) plus conflicting
    DOB or age values for the same patient (spec section 3). Conservative by
    construction: any missing signal (no DOB, no age anywhere, no resolvable
    reference date) means the check has nothing to contradict, so it's
    skipped rather than guessed at."""
    errors: List[str] = []
    patient = content.get("patient")
    if not isinstance(patient, dict):
        return errors

    dates = _labeled_writing_dates(content)
    dob_values = dates["dob"]
    if len(dob_values) > 1:
        errors.append(f"Conflicting DOB values found in patient/case notes: {[d.isoformat() for d in dob_values]}.")
        return errors
    dob = dob_values[0] if dob_values else None

    stated_ages = {a for a in (_parse_stated_age(patient.get("age")),) if a is not None}
    stated_ages |= _ages_in_text(content)
    if len(stated_ages) > 1:
        errors.append(f"Conflicting patient age values found: {sorted(stated_ages)}.")
        return errors

    if dob is None or not stated_ages:
        return errors

    reference = _resolve_writing_reference_date(content, dates)
    if reference is None:
        return errors

    stated_age = next(iter(stated_ages))
    expected_age = _calculate_age(dob, reference)
    if stated_age != expected_age:
        errors.append(
            f"'patient.age' ({stated_age}) is inconsistent with DOB {dob.isoformat()} as of "
            f"reference date {reference.isoformat()}; expected age {expected_age}."
        )
    return errors


def _validate_writing_date_order(content: Dict[str, Any]) -> List[str]:
    """Spec section 2: admission <= discharge, treatment not after discharge
    unless explicitly follow-up, follow-up >= discharge. Only compares dates
    that were actually found and labeled -- an absent date is not an error,
    it's just nothing to check."""
    errors: List[str] = []
    dates = _labeled_writing_dates(content)
    admission = dates["admission"][0] if dates["admission"] else None
    discharge = dates["discharge"][0] if dates["discharge"] else None
    follow_up = dates["follow_up"][0] if dates["follow_up"] else None

    if admission and discharge and admission > discharge:
        errors.append(f"Admission date {admission.isoformat()} is after discharge date {discharge.isoformat()}.")

    if discharge:
        for t in dates["treatment"]:
            if t > discharge:
                errors.append(
                    f"Treatment date {t.isoformat()} falls after discharge date {discharge.isoformat()} "
                    "without being marked as follow-up."
                )

    if follow_up and discharge and follow_up < discharge:
        errors.append(f"Follow-up date {follow_up.isoformat()} is before discharge date {discharge.isoformat()}.")

    return errors


# Matches "... to Ms Georgine Ponsford" style addressing inside the task
# instruction. Deliberately requires an honorific (Dr/Mr/Mrs/Ms/Miss/Prof) --
# without one, "to" precedes far too many non-name phrases in free-form task
# prose to extract a name safely.
_TASK_RECIPIENT_NAME_RE = re.compile(r"\bto\s+((?:Dr|Mr|Mrs|Ms|Miss|Prof)\.?\s+[A-Z][\w'-]+(?:\s+[A-Z][\w'-]+)?)")


def _validate_writing_task_recipient(content: Dict[str, Any]) -> List[str]:
    """Spec section 3: task recipient differing from the recipient object.
    Only fires when the task text names someone with an honorific AND that
    surname doesn't appear anywhere in recipient.name -- a name found in
    task but absent from recipient entirely is the clear contradiction the
    spec asks for; anything looser risks false positives on real names."""
    errors: List[str] = []
    recipient = content.get("recipient")
    task = content.get("task")
    if not isinstance(recipient, dict) or not isinstance(task, str):
        return errors
    recipient_name = str(recipient.get("name") or "").strip()
    if not recipient_name:
        return errors
    match = _TASK_RECIPIENT_NAME_RE.search(task)
    if not match:
        return errors
    task_name = match.group(1)
    task_surname = task_name.split()[-1].lower()
    if task_surname not in recipient_name.lower():
        errors.append(
            f"Task addresses \"{task_name}\" but 'recipient' names \"{recipient_name}\" -- "
            "these must refer to the same person."
        )
    return errors


# Common words that show up in almost any key point regardless of the
# specific clinical fact it's referencing -- excluded so the grounding check
# below compares actual clinical content, not scaffolding vocabulary shared
# by every key point ("mention", "explain", "the letter should note...").
_KEY_POINT_STOPWORDS = {
    "about", "after", "before", "cover", "covers", "discuss", "explain", "explains",
    "flag", "mention", "mentions", "note", "notes", "patient", "should", "their",
    "there", "which", "while", "would", "letter", "include", "includes", "plan",
}
_SIGNIFICANT_WORD_RE = re.compile(r"[a-zA-Z]{5,}")


def _significant_words(text: str) -> set:
    return {w.lower() for w in _SIGNIFICANT_WORD_RE.findall(text)} - _KEY_POINT_STOPWORDS


def _validate_writing_key_points_grounded(content: Dict[str, Any]) -> List[str]:
    """Spec section 3: key_points referring to facts absent from case notes.
    Conservative word-overlap check, not semantic matching: a key point is
    only flagged when NONE of its significant (5+ letter, non-stopword)
    words appear anywhere in case_notes/case_notes_structured -- a single
    shared word (e.g. the condition name) is enough to consider it grounded."""
    errors: List[str] = []
    key_points = content.get("key_points")
    if not isinstance(key_points, list) or not key_points:
        return errors

    notes_only = {k: v for k, v in content.items() if k in ("case_notes_structured", "case_notes")}
    notes_words = _significant_words(" ".join(_writing_text_fragments(notes_only)))
    if not notes_words:
        return errors

    for kp in key_points:
        if not isinstance(kp, str):
            continue
        kp_words = _significant_words(kp)
        if kp_words and not (kp_words & notes_words):
            errors.append(f"key_points entry \"{kp}\" shares no clinical detail with case_notes -- possible fabricated fact.")
    return errors


# W4: distractor/relevance metadata. Internal content metadata only -- never
# exposed through learner-facing Writing endpoints (see draft_publisher.py's
# interlocutor_card home for this and the other W2/W4 structured fields, and
# routers/writing.py's selects, which never name interlocutor_card).
def _normalize_note_text(text: str) -> str:
    return " ".join(text.lower().split())


def _writing_note_fragments(content: Dict[str, Any]) -> List[str]:
    """case_notes_structured items + raw case_notes lines only -- NOT task/
    purpose/recipient/patient. Both the distractor-grounding check and the
    PII check below must only ever look at the learner-facing case notes,
    never at recipient/facility data (which is legitimate task data, not
    patient/social content)."""
    notes_only = {k: v for k, v in content.items() if k in ("case_notes_structured", "case_notes")}
    return _writing_text_fragments(notes_only)


def _text_grounded_in_notes(text: str, fragments: List[str]) -> bool:
    """Verbatim (substring either direction) or near-verbatim (high fuzzy
    similarity to some actual note fragment) -- deterministic, no semantic
    matching. A distractor invented out of whole cloth won't closely match
    any single fragment; a lightly-reworded quote will."""
    normalized = _normalize_note_text(text)
    if not normalized:
        return False
    for fragment in fragments:
        frag_norm = _normalize_note_text(fragment)
        if not frag_norm:
            continue
        if normalized in frag_norm or frag_norm in normalized:
            return True
        if difflib.SequenceMatcher(None, normalized, frag_norm).ratio() >= 0.7:
            return True
    return False


def _validate_writing_distractor_notes(content: Dict[str, Any]) -> List[str]:
    """Optional distractor_notes: [{"text", "reason"}]. Each entry's text must
    be grounded (verbatim/near-verbatim) in case_notes/case_notes_structured,
    and reason must be non-empty. Absent entirely -> no errors (legacy/W2-only
    drafts carry no distractor_notes key)."""
    errors: List[str] = []
    distractor_notes = content.get("distractor_notes")
    if distractor_notes is None:
        return errors
    if not isinstance(distractor_notes, list):
        errors.append("'distractor_notes' must be a list.")
        return errors

    fragments = _writing_note_fragments(content)
    for i, item in enumerate(distractor_notes):
        n = i + 1
        if not isinstance(item, dict):
            errors.append(f"distractor_notes[{n}] must be an object.")
            continue
        text = str(item.get("text") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if not text:
            errors.append(f"distractor_notes[{n}] must have non-empty 'text'.")
        if not reason:
            errors.append(f"distractor_notes[{n}] must have non-empty 'reason'.")
        if text and not _text_grounded_in_notes(text, fragments):
            errors.append(
                f"distractor_notes[{n}] text \"{text[:80]}\" is not grounded in case_notes/"
                "case_notes_structured -- it must exist verbatim or near-verbatim."
            )
    return errors


# W4 PII hygiene: reject invented phone/email-like values inside patient/
# social case-note content. Recipient/facility address and anything else
# outside case_notes/case_notes_structured is never scanned -- those are
# legitimate task data, not the "unnecessary personal contact details" the
# spec targets.
_PII_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[A-Za-z]{2,}\b")
# Requires an 8+ character run of digits/space/dash/parens (not "/", so
# dd/mm/yyyy dates never match) -- a loose but deterministic phone-number shape.
_PII_PHONE_RE = re.compile(r"(?<!\d)\(?\+?\d[\d\-\s()]{6,}\d\)?(?!\d)")


def _validate_writing_pii(content: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for fragment in _writing_note_fragments(content):
        if _PII_EMAIL_RE.search(fragment):
            errors.append(
                f"Case notes contain an invented email address in \"{fragment.strip()[:80]}\" -- "
                "remove unnecessary personal contact details."
            )
            continue
        match = _PII_PHONE_RE.search(fragment)
        if match and sum(c.isdigit() for c in match.group()) >= 7:
            errors.append(
                f"Case notes contain an invented phone number in \"{fragment.strip()[:80]}\" -- "
                "remove unnecessary personal contact details."
            )
    return errors


# W5: admin-only model_answer (reference letter for content reviewers).
# Deterministic and conservative by design (spec explicitly rules out a full
# semantic grader) -- these are structural/grounding smoke checks, not a
# quality judgement on the prose itself. Absent entirely -> no errors, same
# opt-in pattern as distractor_notes above; a legacy draft never carries this
# key. Never sent to the learner scorer and never selected by learner-facing
# writing.py queries (see draft_publisher._scenario_payload's interlocutor_card
# home and routers/writing.py's selects) -- this validator only judges shape.
_MODEL_ANSWER_MIN_WORDS = 100
_MODEL_ANSWER_MAX_WORDS = 350

# Presence of any of these inside model_answer means a prompt/schema detail
# leaked into the reference letter itself -- the letter must read as a letter,
# not as an echo of the content-authoring machinery around it.
_MODEL_ANSWER_METADATA_LEAK_MARKERS = (
    "key_points", "distractor_notes", "case_notes_structured",
    "system prompt", "system instruction", "conditional prompt",
)


def _validate_writing_model_answer(content: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    model_answer = content.get("model_answer")
    if model_answer is None:
        return errors
    if not isinstance(model_answer, str) or not model_answer.strip():
        errors.append("'model_answer' must be a non-empty string when present.")
        return errors

    text = model_answer.strip()
    lower = text.lower()

    word_count = len(text.split())
    if not (_MODEL_ANSWER_MIN_WORDS <= word_count <= _MODEL_ANSWER_MAX_WORDS):
        errors.append(
            f"'model_answer' word count ({word_count}) is outside the expected "
            f"{_MODEL_ANSWER_MIN_WORDS}-{_MODEL_ANSWER_MAX_WORDS} word range for a full letter."
        )

    for marker in _MODEL_ANSWER_METADATA_LEAK_MARKERS:
        if marker in lower:
            errors.append(f"'model_answer' must not expose internal metadata (\"{marker}\").")

    recipient = content.get("recipient")
    if isinstance(recipient, dict):
        recipient_name = str(recipient.get("name") or "").strip()
        if recipient_name:
            surname = recipient_name.split()[-1].lower()
            if surname not in lower:
                errors.append(f"'model_answer' does not appear to address the recipient (\"{recipient_name}\").")

    normalized_answer = _normalize_note_text(text)
    for fragment in _writing_note_fragments(content):
        frag_norm = _normalize_note_text(fragment)
        # Only a substantial fragment counts -- a short shared phrase (a date,
        # a single word) is expected and not "shorthand copied verbatim".
        if len(frag_norm) > 15 and frag_norm in normalized_answer:
            errors.append(
                f"'model_answer' contains case-note shorthand copied verbatim: \"{fragment.strip()[:80]}\"."
            )
            break

    note_dates = set()
    for dates in _labeled_writing_dates(content).values():
        note_dates.update(dates)
    if note_dates:
        for d in _find_dates(text):
            if d not in note_dates:
                errors.append(
                    f"'model_answer' references date {d.isoformat()} not found in the case notes -- "
                    "possible fabricated fact."
                )

    return errors


def _validate_writing(content: Dict[str, Any]) -> List[str]:
    """Structural check for the W2 structured Writing contract. Additive and
    opt-in: legacy drafts (title/case_notes/task/key_points only, already
    covered by _REQUIRED_FIELDS/_REQUIRED_NONEMPTY_LISTS) carry none of the
    keys checked here, so every check below only fires when the field it
    checks is actually present -- a legacy draft returns no errors."""
    errors: List[str] = []

    if "key_points" in content and not isinstance(content.get("key_points"), list):
        errors.append("'key_points' must be a list when present.")

    letter_type = content.get("letter_type")
    if letter_type is not None and letter_type not in _WRITING_LETTER_TYPES:
        errors.append(f"'letter_type' must be one of {_WRITING_LETTER_TYPES}; got {letter_type!r}.")

    recipient = content.get("recipient")
    if recipient is not None:
        if not isinstance(recipient, dict):
            errors.append("'recipient' must be an object.")
        else:
            for field in ("role", "organization", "address"):
                if not str(recipient.get(field) or "").strip():
                    errors.append(f"'recipient.{field}' must not be empty.")

    patient = content.get("patient")
    if patient is not None:
        if not isinstance(patient, dict):
            errors.append("'patient' must be an object.")
        elif not str(patient.get("name") or "").strip():
            errors.append("'patient.name' must not be empty.")

    case_notes_structured = content.get("case_notes_structured")
    if case_notes_structured is not None:
        if not isinstance(case_notes_structured, list) or not case_notes_structured:
            errors.append("'case_notes_structured' must be a non-empty list.")
        else:
            for i, section in enumerate(case_notes_structured):
                n = i + 1
                if not isinstance(section, dict):
                    errors.append(f"case_notes_structured[{n}] must be an object.")
                    continue
                if not str(section.get("section") or "").strip():
                    errors.append(f"case_notes_structured[{n}] must have a non-empty 'section' name.")
                items = section.get("items")
                if not isinstance(items, list) or not items:
                    errors.append(f"case_notes_structured[{n}] must have a non-empty 'items' list.")

    # A structured draft (any of the fields above present) must also carry a
    # purpose -- legacy drafts have none of those fields, so this never fires
    # for them.
    is_structured = any(content.get(k) is not None for k in ("letter_type", "recipient", "patient", "case_notes_structured"))
    if is_structured and not str(content.get("purpose") or "").strip():
        errors.append("'purpose' must not be empty on a structured Writing draft.")

    writing_requirements = content.get("writing_requirements")
    if writing_requirements is not None:
        if not isinstance(writing_requirements, dict):
            errors.append("'writing_requirements' must be an object.")
        else:
            for field in ("reading_minutes", "writing_minutes"):
                if not isinstance(writing_requirements.get(field), int):
                    errors.append(f"'writing_requirements.{field}' must be an integer.")
            if not str(writing_requirements.get("target_word_count") or "").strip():
                errors.append("'writing_requirements.target_word_count' must not be empty.")
            for field in ("letter_format", "no_note_form"):
                if not isinstance(writing_requirements.get(field), bool):
                    errors.append(f"'writing_requirements.{field}' must be a boolean.")

    errors.extend(_validate_writing_age_dob(content))
    errors.extend(_validate_writing_date_order(content))
    errors.extend(_validate_writing_task_recipient(content))
    errors.extend(_validate_writing_key_points_grounded(content))
    errors.extend(_validate_writing_distractor_notes(content))
    errors.extend(_validate_writing_pii(content))
    errors.extend(_validate_writing_model_answer(content))

    return errors


def _validate(module: str, content: Dict[str, Any]) -> List[str]:
    if module == "listening" and content.get("part") in ("A", "B", "C"):
        # Locked Part A/B/C shape ("extracts": [...]) doesn't have the legacy
        # top-level transcript/questions, so it must bypass the generic
        # required-field check below entirely, same reason Reading Part B/C do.
        part = content["part"]
        validator = {
            "A": _validate_listening_part_a,
            "B": _validate_listening_part_b,
            "C": _validate_listening_part_c,
        }[part]
        errors = validator(content)
        if errors:
            raise DraftGenerationError(
                f"Generated Listening Part {part} content violates the locked contract: " + " ".join(errors)
            )
        return []

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

    if module == "writing":
        writing_errors = _validate_writing(content)
        if writing_errors:
            raise DraftGenerationError(
                "Generated Writing content violates the structured contract: " + " ".join(writing_errors)
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

    if module == "writing":
        content.setdefault("writing_requirements", dict(_WRITING_REQUIREMENTS_DEFAULT))
        _derive_writing_patient_age(content)

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
