"""Phase 3A -- build_listening_prompt(part=...) dispatch to the dedicated
Listening Part A/B/C schema/instructions, mirroring
test_content_studio_part_wiring.py's Reading dispatch tests (bottom section).
No AI call -- pure string-building checks against prompt_builder.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import prompt_builder


def test_build_listening_prompt_dispatches_part_a_branch():
    _, user = prompt_builder.build_listening_prompt("intermediate", "cardiology", "chest pain", part="A")
    for marker in ["Listening Part A", "EXACTLY 2", "EXACTLY 12", "short_answer", "prep_seconds"]:
        assert marker in user


def test_build_listening_prompt_dispatches_part_b_branch():
    _, user = prompt_builder.build_listening_prompt("intermediate", "cardiology", "chest pain", part="B")
    for marker in ["Listening Part B", "EXACTLY 6", "mcq", "prep_seconds"]:
        assert marker in user


def test_build_listening_prompt_dispatches_part_c_branch():
    _, user = prompt_builder.build_listening_prompt("intermediate", "cardiology", "chest pain", part="C")
    for marker in ["Listening Part C", "EXACTLY 2", "EXACTLY 6", "dialogue", "monologue"]:
        assert marker in user


def test_build_listening_prompt_dispatches_default_branch_when_part_none():
    """part omitted -> unchanged legacy generic Listening prompt (still used
    by any direct caller outside the Content Studio generator, which now
    requires a part -- see admin_content_studio.GenerateDraftsRequest)."""
    _, user = prompt_builder.build_listening_prompt("intermediate", "cardiology", "chest pain")
    assert "Listening Part A" not in user
    assert "Pick ONE of Part A, B, or C at random" in user


def test_build_prompt_dispatches_listening_part_a_via_module_router():
    _, user = prompt_builder.build_prompt("listening", "intermediate", "cardiology", "chest pain", part="A")
    assert "Listening Part A" in user
    assert "EXACTLY 12" in user


def test_build_prompt_dispatches_listening_part_b_via_module_router():
    _, user = prompt_builder.build_prompt("listening", "intermediate", "cardiology", "chest pain", part="B")
    assert "Listening Part B" in user


def test_build_prompt_dispatches_listening_part_c_via_module_router():
    _, user = prompt_builder.build_prompt("listening", "intermediate", "cardiology", "chest pain", part="C")
    assert "Listening Part C" in user


# ── schemas carry the locked-contract fields the generator/validator expect ──

def test_part_a_schema_has_extracts_prep_seconds_audio_mode():
    for marker in ['"extracts"', '"prep_seconds": 30', '"audio_mode": "dialogue"', '"body"', '"accepted_answers"']:
        assert marker in prompt_builder._LISTENING_PART_A_SCHEMA


def test_part_b_schema_has_extracts_prep_seconds_audio_mode():
    for marker in ['"extracts"', '"prep_seconds": 15', '"audio_mode": "dialogue"']:
        assert marker in prompt_builder._LISTENING_PART_B_SCHEMA


def test_part_c_schema_has_per_extract_audio_mode():
    assert '"prep_seconds": 90' in prompt_builder._LISTENING_PART_C_SCHEMA
    # audio_mode lives per-extract in Part C, not as a single top-level field.
    assert prompt_builder._LISTENING_PART_C_SCHEMA.count('"audio_mode"') == 2
