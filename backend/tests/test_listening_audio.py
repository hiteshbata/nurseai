import pytest

from app.services.listening_audio import assign_voices, timestamped_lines, TtsError, OPENAI_VOICES


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
