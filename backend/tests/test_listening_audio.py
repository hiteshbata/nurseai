import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services import listening_audio
from app.services.listening_audio import (
    assign_voices, timestamped_lines, TtsError, OPENAI_VOICES,
    instructions_for_speaker, generate_two_speaker_audio,
    GAP_MIN_SECONDS, GAP_MAX_SECONDS, MONO_CHUNK_GAP_SECONDS,
)


def test_timestamped_lines_groups_and_prefixes_start():
    words = [{"word": f"w{i}", "start": float(i)} for i in range(40)]
    lines = timestamped_lines(words, words_per_line=18)
    assert len(lines) == 3  # 18 + 18 + 4
    assert lines[0].startswith("[0.0] ") and "w0" in lines[0]
    assert lines[1].startswith("[18.0] ") and "w18" in lines[1]


def test_timestamped_lines_prefers_punctuated_and_handles_empty():
    assert timestamped_lines([]) == []
    lines = timestamped_lines([{"word": "hi", "punctuated_word": "Hi,", "start": 2.0}], words_per_line=18)
    assert lines == ["[2.0] Hi,"]


def test_two_speakers_get_two_different_voices():
    m = assign_voices(["professional", "patient"], None)
    assert m["professional"] != m["patient"]
    assert m["professional"] in OPENAI_VOICES and m["patient"] in OPENAI_VOICES


def test_repeated_speaker_keeps_same_voice():
    m = assign_voices(["a", "b", "a", "b", "a"], None)
    assert len({m["a"], m["b"]}) == 2  # only two distinct voices for two speakers


def test_provided_voice_is_honored_and_not_reused():
    m = assign_voices(["doc", "pt"], {"doc": "nova"})
    assert m["doc"] == "nova"
    assert m["pt"] != "nova"  # auto-assigned speaker must not collide with a pinned voice


def test_unknown_voice_rejected():
    with pytest.raises(TtsError):
        assign_voices(["doc"], {"doc": "not_a_real_voice"})


def test_more_speakers_than_pool_wraps_without_crashing():
    speakers = [f"s{i}" for i in range(len(OPENAI_VOICES) + 2)]
    m = assign_voices(speakers, None)
    assert len(m) == len(speakers)
    assert all(v in OPENAI_VOICES for v in m.values())


def test_voice_pool_leads_with_marin_cedar():
    assert OPENAI_VOICES[:2] == ["marin", "cedar"]
    # full approved pool, no old tts-1-only restriction
    assert set(OPENAI_VOICES) == {
        "marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "fable",
        "nova", "onyx", "sage", "shimmer", "verse",
    }


def test_two_speakers_default_to_marin_and_cedar():
    m = assign_voices(["professional", "patient"], None)
    assert {m["professional"], m["patient"]} == {"marin", "cedar"}


def test_explicit_voice_override_still_honored():
    m = assign_voices(["professional", "patient"], {"professional": "onyx"})
    assert m["professional"] == "onyx"
    assert m["patient"] != "onyx"


def test_instructions_are_role_aware_and_distinct():
    patient = instructions_for_speaker("patient")
    professional = instructions_for_speaker("professional")
    narrator = instructions_for_speaker("narrator")
    assert len({patient, professional, narrator}) == 3
    assert "patient" in patient.lower()
    assert "health professional" in professional.lower()


def test_deterministic_gap_is_reproducible_and_in_range():
    from app.services.listening_audio import _deterministic_gap
    g1 = _deterministic_gap("Good morning, how can I help you today?")
    g2 = _deterministic_gap("Good morning, how can I help you today?")
    g3 = _deterministic_gap("A completely different line of dialogue.")
    assert g1 == g2  # same text -> same gap, so regeneration is a no-op diff
    assert GAP_MIN_SECONDS <= g1 <= GAP_MAX_SECONDS
    assert GAP_MIN_SECONDS <= g3 <= GAP_MAX_SECONDS
    assert g1 != g3  # different text -> (almost certainly) a different gap


def test_chunk_by_sentence_packs_under_limit_and_preserves_text():
    from app.services.listening_audio import _chunk_by_sentence
    text = "One. Two. Three. Four. Five."
    chunks = _chunk_by_sentence(text, max_chars=10)
    assert all(len(c) <= 10 for c in chunks)
    assert " ".join(chunks) == text  # no dropped or reordered words
    assert "One." in chunks[0]


def test_chunk_by_sentence_single_chunk_when_short():
    from app.services.listening_audio import _chunk_by_sentence
    chunks = _chunk_by_sentence("Just one short sentence.", max_chars=4000)
    assert chunks == ["Just one short sentence."]


def test_monologue_single_call_bypasses_stitch(monkeypatch):
    """One distinct speaker, short transcript -> exactly one TTS call, no ffmpeg stitch."""
    synth = AsyncMock(return_value=b"solo-audio")
    stitch_called = []
    monkeypatch.setattr(listening_audio, "_synthesize_turn", synth)
    monkeypatch.setattr(listening_audio, "_stitch", lambda *a, **k: stitch_called.append(1) or b"")

    turns = [
        {"speaker": "narrator", "text": "Welcome to today's lecture on wound care."},
        {"speaker": "narrator", "text": "We'll start with the basics."},
    ]
    result = asyncio.run(generate_two_speaker_audio(turns, model="gpt-4o-mini-tts"))

    assert result == b"solo-audio"
    assert synth.await_count == 1  # single call, not one per turn
    assert not stitch_called  # ffmpeg bypassed entirely
    call_args = synth.await_args
    assert "wound care" in call_args.args[1] and "basics" in call_args.args[1]
    assert call_args.args[4] == instructions_for_speaker("narrator")


def test_monologue_over_limit_chunks_and_stitches_with_small_gap(monkeypatch):
    synth = AsyncMock(return_value=b"chunk")
    captured = {}
    monkeypatch.setattr(listening_audio, "_synthesize_turn", synth)

    def fake_stitch(segments, gaps):
        captured["gaps"] = gaps
        return b"stitched-mono"

    monkeypatch.setattr(listening_audio, "_stitch", fake_stitch)

    # Two turns, each within the 4000-char per-turn limit, whose combined
    # length exceeds it -- forces the monologue path into multi-chunk mode.
    sentence = "This is one sentence of the lecture transcript. "
    turns = [
        {"speaker": "narrator", "text": sentence * 60},   # ~3000 chars
        {"speaker": "narrator", "text": sentence * 40},   # ~2000 chars
    ]
    result = asyncio.run(generate_two_speaker_audio(turns, model="gpt-4o-mini-tts"))

    assert result == b"stitched-mono"
    assert synth.await_count > 1  # split into multiple chunks
    assert captured["gaps"] == [MONO_CHUNK_GAP_SECONDS] * (synth.await_count - 1)


def test_dialogue_uses_per_turn_instructions_and_variable_gaps(monkeypatch):
    synth = AsyncMock(return_value=b"turn-audio")
    captured = {}
    monkeypatch.setattr(listening_audio, "_synthesize_turn", synth)

    def fake_stitch(segments, gaps):
        captured["gaps"] = gaps
        return b"stitched-dialogue"

    monkeypatch.setattr(listening_audio, "_stitch", fake_stitch)

    turns = [
        {"speaker": "professional", "text": "Good morning, how are you feeling today?"},
        {"speaker": "patient", "text": "I've had this cough for about a week now."},
        {"speaker": "professional", "text": "Let's take a look at that for you."},
    ]
    result = asyncio.run(generate_two_speaker_audio(turns, model="gpt-4o-mini-tts"))

    assert result == b"stitched-dialogue"
    assert synth.await_count == 3  # one call per turn, not one for the whole transcript
    voices_used = {c.args[2] for c in synth.await_args_list}
    assert voices_used == {"marin", "cedar"}
    instructions_used = [c.args[4] for c in synth.await_args_list]
    assert instructions_used == [
        instructions_for_speaker("professional"),
        instructions_for_speaker("patient"),
        instructions_for_speaker("professional"),
    ]
    assert len(captured["gaps"]) == 2
    assert all(GAP_MIN_SECONDS <= g <= GAP_MAX_SECONDS for g in captured["gaps"])
