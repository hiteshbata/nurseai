"""TEMPORARY diagnostic tests for the production incident: Gemini returned
HTTP 200 but _try_parse_json() (app/services/ai_scoring.py) failed to parse
a Reading Part A draft-generation response.

This file covers two things:
1. The bounded, secret-safe parse-failure diagnostic record
   (_build_parse_diagnostic / _log_parse_failure) -- proves it's bounded,
   hashed, redacted, and never contains the full AI response.
2. That none of this changed _try_parse_json's actual parsing behavior --
   same inputs still produce the same parsed dict or None as before the
   diagnostic record existed.

No production behavior, prompt, parser logic, retry/fallback behavior, or
schema is changed here -- delete this file once the real cause is confirmed
and (if needed) a fix ships separately.
"""
import hashlib
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.ai_scoring import _try_parse_json, _build_parse_diagnostic


# ── Evidence from the Render log (2026-08-18T17:20:05Z, model=gemini-flash-latest,
# module=reading, part=A) -- exactly what draft_generator.py logged, i.e.
# str(result["raw_feedback"])[:500]. This is a SUBSTRING, not a complete
# response -- it cuts off mid-word ("meas") because of the [:500] truncation,
# not because that's where the JSON actually broke.
PRODUCTION_RAW_HEAD = (
    '{\n'
    '  "title": "Diagnosis and Management of Heart Failure",\n'
    '  "part": "A",\n'
    '  "difficulty": "intermediate",\n'
    '  "body": "Text A\\nAssessment and Diagnostic Thresholds for Chronic Heart Failure\\n\\n'
    'Clinical features of heart failure commonly include exertional dyspnoea, fatigue, orthopnoea, '
    'paroxysmal nocturnal dyspnoea, and bilateral ankle oedema. Initial diagnostic evaluation requires '
    'a 12-lead ECG and serum B-type natriuretic peptide (BNP) or N-terminal pro-B-type natriuretic '
    'peptide (NT-proBNP) meas'
)


def test_production_raw_head_is_incomplete_by_construction():
    """The logged 500-char prefix alone is not valid/complete JSON -- it's a
    substring. This proves nothing about the real failure location; it only
    confirms the log line itself can't be used to pinpoint the bug."""
    assert not PRODUCTION_RAW_HEAD.rstrip().endswith(("}", "]"))
    try:
        json.loads(PRODUCTION_RAW_HEAD)
        assert False, "500-char prefix should not parse as complete JSON"
    except json.JSONDecodeError:
        pass


def test_production_raw_head_prefix_is_well_formed_up_to_the_cut():
    """Everything captured IS valid so far (proper top-level keys, and the
    body string's internal \\n sequences are correctly-escaped JSON escapes,
    not raw control characters) -- whatever broke the real response happened
    at or after byte 500, never confirmed by this log line alone."""
    closed = PRODUCTION_RAW_HEAD + 'urement..."}'
    parsed = json.loads(closed)
    assert parsed["title"] == "Diagnosis and Management of Heart Failure"
    assert parsed["part"] == "A"
    assert parsed["body"].startswith("Text A\nAssessment")


# ── _build_parse_diagnostic: the bounded record itself ───────────────────

def _decode_error(content: str) -> json.JSONDecodeError:
    try:
        json.loads(content)
    except json.JSONDecodeError as e:
        return e
    raise AssertionError("expected content to be invalid JSON")


def test_diagnostic_has_exactly_the_required_fields():
    content = '{"title": "bad'
    exc = _decode_error(content)
    diagnostic = _build_parse_diagnostic("google", "gemini-flash-latest", content, exc, finish_reason="MAX_TOKENS")
    assert set(diagnostic) == {
        "provider", "model", "finish_reason", "response_length",
        "parse_error", "error_pos", "context", "truncated", "response_sha256",
    }
    assert diagnostic["provider"] == "google"
    assert diagnostic["model"] == "gemini-flash-latest"
    assert diagnostic["finish_reason"] == "MAX_TOKENS"
    assert diagnostic["response_length"] == len(content)
    assert diagnostic["parse_error"] == exc.msg
    assert diagnostic["error_pos"] == exc.pos
    assert diagnostic["truncated"] is True


def test_diagnostic_finish_reason_defaults_to_none_when_not_provided():
    content = '{"title": "bad'
    exc = _decode_error(content)
    diagnostic = _build_parse_diagnostic("google", "gemini-flash-latest", content, exc)
    assert diagnostic["finish_reason"] is None


def test_diagnostic_context_is_bounded_regardless_of_response_size():
    """The single most important guarantee for this incident's log line: no
    matter how large the real response is, the diagnostic's context window
    stays a small fixed size -- it must never scale with response_length."""
    huge = "x" * 500_000 + '{"title": "unterminated'  # 500K of padding, then a real JSON error
    exc = _decode_error(huge)
    diagnostic = _build_parse_diagnostic("google", "gemini-flash-latest", huge, exc)
    assert diagnostic["response_length"] == len(huge)
    assert len(diagnostic["context"]) <= 80  # 2 * _PARSE_DIAGNOSTIC_CONTEXT_RADIUS
    assert diagnostic["context"] != huge


def test_diagnostic_total_size_stays_small_for_a_huge_response():
    """The record as a whole (what actually gets logged) must not grow with
    the response -- this is the direct proof it never persists the full
    response, not just the context field in isolation."""
    huge = "y" * 200_000 + '{"body": "unterminated'
    exc = _decode_error(huge)
    diagnostic = _build_parse_diagnostic("openrouter", "google/gemini-flash-latest", huge, exc)
    serialized = json.dumps(diagnostic)
    assert len(serialized) < 1000
    assert len(serialized) < len(huge) / 100


def test_diagnostic_hash_matches_sha256_of_full_content():
    """response_sha256 lets an operator correlate this diagnostic against a
    provider-side/observability-side copy of the response (if one exists
    elsewhere) without the diagnostic itself ever holding that content."""
    content = '{"title": "unterminated'
    exc = _decode_error(content)
    diagnostic = _build_parse_diagnostic("google", "gemini-flash-latest", content, exc)
    assert diagnostic["response_sha256"] == hashlib.sha256(content.encode("utf-8")).hexdigest()


def test_diagnostic_redacts_api_key_like_pattern_in_context_window():
    """Defense in depth: content here is always AI-generated draft text, not
    a credential -- but if anything resembling a key/token/secret ever
    landed inside the context window, it must never appear in the clear."""
    # Error position lands right after the fake key, so the ~40-char
    # look-back window covers it.
    content = '{"api_key": "AIzaSyD1234567890ABCDEFGHIJKLMNOPQRSTUV' + 'x' * 30 + ' bad'
    exc = _decode_error(content)
    diagnostic = _build_parse_diagnostic("google", "gemini-flash-latest", content, exc)
    assert "AIzaSyD1234567890ABCDEFGHIJKLMNOPQRSTUV" not in diagnostic["context"]


# ── _try_parse_json logging: the record is what gets logged, nothing else ─

def test_log_line_contains_diagnostic_marker_and_bounded_fields(caplog):
    content = '{"title": "bad'
    with caplog.at_level(logging.ERROR, logger="app.services.ai_scoring"):
        result = _try_parse_json("google", "gemini-flash-latest", content, "STOP")
    assert result is None
    assert "[SCORING_PARSE_FAILURE]" in caplog.text
    assert "'provider': 'google'" in caplog.text
    assert "'finish_reason': 'STOP'" in caplog.text
    assert "'response_sha256'" in caplog.text


def test_log_line_never_contains_the_full_response(caplog):
    """The actual regression this whole change guards against: a large
    response failing to parse must not put that response's full content
    into the logs, only the bounded diagnostic record."""
    huge = "z" * 50_000 + '{"body": "unterminated'
    with caplog.at_level(logging.DEBUG, logger="app.services.ai_scoring"):
        result = _try_parse_json("google", "gemini-flash-latest", huge, "MAX_TOKENS")
    assert result is None
    assert huge not in caplog.text
    assert "z" * 1000 not in caplog.text  # no long unbroken run of the padding either
    assert "[SCORING_PARSE_FAILURE]" in caplog.text


def test_fence_stripped_failure_also_logs_bounded_record_not_full_content(caplog):
    huge_fenced = "```json\n" + "w" * 50_000 + '{"body": "unterminated\n```'
    with caplog.at_level(logging.DEBUG, logger="app.services.ai_scoring"):
        result = _try_parse_json("google", "gemini-flash-latest", huge_fenced, "STOP")
    assert result is None
    assert huge_fenced not in caplog.text
    assert "note=fence_stripped_also_failed" in caplog.text


# ── Parser behavior is unchanged: same 8 categories, same outcomes ───────
# Re-verifies the exact same input/output contract from before provider/
# finish_reason were added to the signature -- proves the diagnostic work
# didn't touch what gets parsed or how.

def test_valid_json_parses():
    content = json.dumps({"title": "t", "part": "A", "body": "b", "questions": []})
    assert _try_parse_json("google", "gemini-flash-latest", content) == {"title": "t", "part": "A", "body": "b", "questions": []}


def test_json_with_markdown_fences_parses():
    content = "```json\n" + json.dumps({"title": "t"}) + "\n```"
    assert _try_parse_json("google", "gemini-flash-latest", content) == {"title": "t"}


def test_json_with_bare_fences_no_json_tag_parses():
    content = "```\n" + json.dumps({"title": "t"}) + "\n```"
    assert _try_parse_json("google", "gemini-flash-latest", content) == {"title": "t"}


def test_json_with_trailing_prose_parses():
    content = json.dumps({"title": "t"}) + "\n\nLet me know if you'd like any changes!"
    assert _try_parse_json("google", "gemini-flash-latest", content) == {"title": "t"}


def test_unescaped_quote_fails():
    content = '{"title": "the "best" title"}'
    assert _try_parse_json("google", "gemini-flash-latest", content) is None


def test_invalid_escape_sequence_fails():
    content = r'{"title": "bad \x escape"}'
    assert _try_parse_json("google", "gemini-flash-latest", content) is None


def test_truncated_unicode_escape_fails():
    content = '{"title": "bad \\u12 escape"}'
    assert _try_parse_json("google", "gemini-flash-latest", content) is None


def test_raw_control_character_in_string_fails():
    content = '{"body": "line one\nline two"}'
    assert _try_parse_json("google", "gemini-flash-latest", content) is None


def test_raw_tab_character_in_string_fails():
    content = '{"body": "col1\tcol2"}'
    assert _try_parse_json("google", "gemini-flash-latest", content) is None


def test_truncated_mid_string_fails():
    content = '{"title": "Diagnosis and Management of Heart Fail'
    assert _try_parse_json("google", "gemini-flash-latest", content) is None


def test_truncated_mid_array_fails():
    content = '{"title": "t", "questions": [{"content": "q1"}, {"content": "q2"'
    assert _try_parse_json("google", "gemini-flash-latest", content) is None


# ── large Reading Part A payload (realistic size) ─────────────────────────

def _big_part_a_body() -> str:
    paragraph = (
        "Clinical features commonly include exertional dyspnoea, fatigue, orthopnoea, "
        "paroxysmal nocturnal dyspnoea, and bilateral ankle oedema. Initial diagnostic "
        "evaluation requires a 12-lead ECG and serum BNP or NT-proBNP measurement, "
        "followed by transthoracic echocardiography to confirm ejection fraction. "
    ) * 20
    return "\n\n".join(f"Text {label}\n{paragraph}" for label in "ABCD")


def _big_part_a_questions() -> list:
    match_options = ["Text A", "Text B", "Text C", "Text D"]
    questions = [
        {"content": f"In which text is finding {n} discussed?", "type": "mcq",
         "options": match_options, "correct_answer": match_options[n % 4]}
        for n in range(1, 6)
    ]
    questions += [
        {"content": f"Question {n}: what is the recommended threshold for finding {n}?",
         "type": "short_answer", "options": [], "correct_answer": f"answer {n}"}
        for n in range(6, 21)
    ]
    return questions


def test_large_reading_part_a_payload_parses():
    """Confirms response *size* alone (this is roughly the shape/scale of a
    real Part A generation -- 4 long texts, 20 questions) is not, by itself,
    a reason _try_parse_json fails."""
    content = json.dumps({
        "title": "Diagnosis and Management of Heart Failure",
        "part": "A",
        "difficulty": "intermediate",
        "body": _big_part_a_body(),
        "questions": _big_part_a_questions(),
    })
    assert len(content) > 8000
    result = _try_parse_json("google", "gemini-flash-latest", content)
    assert result is not None
    assert len(result["questions"]) == 20


def test_large_payload_truncated_at_max_tokens_boundary_fails():
    """The one hypothesis draft_generator.py's own comments already flag as
    plausible for Reading (max_tokens=6000 override) -- a large, otherwise-
    valid Part A payload chopped mid-stream, like a real MAX_TOKENS cutoff."""
    full = json.dumps({
        "title": "Diagnosis and Management of Heart Failure",
        "part": "A",
        "difficulty": "intermediate",
        "body": _big_part_a_body(),
        "questions": _big_part_a_questions(),
    }, indent=2)
    chopped = full[:len(full) // 2]
    assert _try_parse_json("google", "gemini-flash-latest", chopped) is None


# ── draft_generator.py: no content leaks into its warning log either ─────

def test_draft_generator_parse_failure_log_never_contains_response_content(monkeypatch, caplog):
    from app.services import draft_generator, ai_registry

    secret_marker = "SECRET_RESPONSE_MARKER_" + "x" * 200

    async def fake_get_model_config(purpose):
        raise ai_registry.PurposeNotConfigured("no purpose configured in test")

    async def fake_call_ai(*args, **kwargs):
        return {"raw_feedback": secret_marker, "finish_reason": "STOP"}

    monkeypatch.setattr(ai_registry, "get_model_config", fake_get_model_config)
    monkeypatch.setattr(draft_generator, "_call_ai", fake_call_ai)
    monkeypatch.setattr(
        draft_generator.prompt_builder, "build_prompt",
        lambda *a, **k: ("system prompt", "user prompt"),
    )

    import asyncio

    with caplog.at_level(logging.WARNING, logger="app.services.draft_generator"):
        with pytest.raises(draft_generator.DraftGenerationError):
            asyncio.run(draft_generator.generate_draft(
                module="reading", difficulty="intermediate", specialty="cardiology",
                topic="t", part="A",
            ))

    assert secret_marker not in caplog.text
    assert "[draft_generator] JSON parse failed | module=reading" in caplog.text


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
