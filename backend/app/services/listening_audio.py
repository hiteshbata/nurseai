"""TTS for Listening extracts, dialogue or monologue.

OpenAI TTS voices each turn (OpenAI has no native multi-speaker -- one voice
per call), then ffmpeg stitches the turns into one mp3 with a pause between
them. Admin-only content generation, low volume, so per-turn API calls + an
ffmpeg re-encode are fine.

The transcript is a list of turns [{"speaker": "...", "text": "..."}]. Each
distinct speaker label maps to a distinct, stable OpenAI voice. A transcript
with exactly one distinct speaker is a monologue (Part B/C lecture, single
narrator) and takes the single-call path instead; this is detected from the
transcript itself, never from the OET part number.
"""
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.threading import run_sync
from app.services import ai_registry

logger = logging.getLogger(__name__)

OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"
# gpt-4o-mini-tts voice pool. marin/cedar lead the pool -- best-sounding pair
# for a two-speaker consult -- with the rest available as explicit overrides.
OPENAI_VOICES = [
    "marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "fable",
    "nova", "onyx", "sage", "shimmer", "verse",
]
MAX_TURN_CHARS = 4000   # OpenAI TTS hard limit is 4096 chars/request; stay under
MAX_TURNS = 120
GAP_MIN_SECONDS = 0.25   # dialogue turn-gap range -- deterministic per turn, not
GAP_MAX_SECONDS = 0.75   # random, so regenerating the same transcript is a no-op diff
MONO_CHUNK_GAP_SECONDS = 0.15  # gap between sentence-chunk splits within one monologue
TTS_SAMPLE_RATE = 24000  # OpenAI TTS mp3 output rate; normalize the stitch to it


def instructions_for_speaker(speaker: str) -> str:
    """Role-aware delivery instructions for gpt-4o-mini-tts, keyed off the
    speaker label already used throughout Listening content (e.g. "professional"
    / "patient" for a consult; anything else -- lecturer, narrator, colleague --
    falls back to a neutral informative delivery for monologue/interview parts)."""
    s = speaker.strip().lower()
    if "patient" in s:
        return ("Speak as a patient describing their own situation: natural, "
                "conversational pace, mild everyday hesitation, no performance polish.")
    if any(k in s for k in ("professional", "nurse", "doctor", "clinician", "health")):
        return ("Speak as a health professional: calm, clear, measured pace, "
                "reassuring and unhurried.")
    return ("Speak clearly at a moderate, even pace suited to note-taking, "
            "as in a lecture or briefing.")


def _deterministic_gap(text: str) -> float:
    """A gap duration in [GAP_MIN_SECONDS, GAP_MAX_SECONDS] derived from the turn's
    own text, so pacing varies turn-to-turn but regenerating the same transcript
    reproduces byte-identical audio."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    frac = (int(digest[:8], 16) % 1000) / 999.0
    return round(GAP_MIN_SECONDS + frac * (GAP_MAX_SECONDS - GAP_MIN_SECONDS), 3)


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _chunk_by_sentence(text: str, max_chars: int) -> List[str]:
    """Split text on sentence boundaries into chunks each <= max_chars, so a
    monologue longer than one TTS call still reads as continuous prose. A single
    sentence longer than max_chars is kept whole (falls back to a hard cut)."""
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s]
    chunks: List[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(sentence) <= max_chars:
            current = sentence
        else:
            for i in range(0, len(sentence), max_chars):
                chunks.append(sentence[i:i + max_chars])
            current = ""
    if current:
        chunks.append(current)
    return chunks


class TtsError(Exception):
    """Raised for a bad request (surfaceable to the admin) — empty turns, a turn
    over the char limit, an unknown voice, etc. The router turns this into a 400."""


def assign_voices(speakers: List[str], provided: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Map each distinct speaker label to an OpenAI voice. Honors any admin-provided
    mapping and auto-assigns the rest from the pool in first-seen order, so two
    speakers always get two different voices. Pure/testable."""
    provided = provided or {}
    for v in provided.values():
        if v not in OPENAI_VOICES:
            raise TtsError(f"Unknown voice '{v}'. Choose from: {', '.join(OPENAI_VOICES)}")
    mapping: Dict[str, str] = {}
    pool = [v for v in OPENAI_VOICES if v not in provided.values()]
    for sp in speakers:
        if sp in mapping:
            continue
        if sp in provided:
            mapping[sp] = provided[sp]
        elif pool:
            mapping[sp] = pool.pop(0)
        else:
            # More distinct speakers than voices in the pool -- wrap around. OET
            # extracts are 1-2 speakers, so this is only a safety fallback.
            mapping[sp] = OPENAI_VOICES[len(mapping) % len(OPENAI_VOICES)]
    return mapping


async def _synthesize_turn(
    client: httpx.AsyncClient, text: str, voice: str, model: str, instructions: str,
) -> bytes:
    resp = await client.post(
        OPENAI_TTS_URL,
        headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
        json={
            "model": model, "input": text, "voice": voice, "response_format": "mp3",
            "instructions": instructions,
        },
    )
    if resp.status_code != 200:
        # resp.text may include OpenAI's own error JSON; log a slice, never the key.
        logger.error("[listening tts] OpenAI HTTP %s: %s", resp.status_code, resp.text[:300])
        raise RuntimeError(f"openai_tts_http_{resp.status_code}")
    return resp.content


def _run_ffmpeg(cmd: List[str], timeout: int) -> None:
    subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)


def _stitch(segments: List[bytes], gaps: List[float]) -> bytes:
    """Concatenate per-turn mp3 bytes into one mp3, inserting each gaps[i] seconds
    of silence between segment i and i+1 (len(gaps) == len(segments) - 1, so gaps
    can vary turn-to-turn). Uses the ffmpeg concat FILTER (decodes + re-encodes),
    which tolerates any per-segment codec/param differences -- unlike the concat
    demuxer, which needs identical params. Blocking; call via run_sync."""
    if not segments:
        raise TtsError("No audio was generated to stitch.")
    if len(segments) == 1:
        return segments[0]

    tmpdir = tempfile.mkdtemp(prefix="listening_tts_")
    try:
        seg_paths = []
        for i, data in enumerate(segments):
            p = os.path.join(tmpdir, f"seg{i}.mp3")
            with open(p, "wb") as f:
                f.write(data)
            seg_paths.append(p)

        # One silence file per distinct gap duration used (usually all distinct,
        # since gaps are deterministic-per-text, but cache in case of repeats).
        sil_paths: Dict[float, str] = {}
        for gap in set(gaps):
            sil_path = os.path.join(tmpdir, f"sil_{gap}.mp3")
            _run_ffmpeg(
                ["ffmpeg", "-y", "-f", "lavfi", "-i",
                 f"anullsrc=r={TTS_SAMPLE_RATE}:cl=mono", "-t", str(gap),
                 "-c:a", "libmp3lame", sil_path],
                timeout=30,
            )
            sil_paths[gap] = sil_path

        # interleave: seg0, sil(gaps[0]), seg1, sil(gaps[1]), ..., segN
        inputs: List[str] = []
        for i, p in enumerate(seg_paths):
            inputs.append(p)
            if i != len(seg_paths) - 1:
                inputs.append(sil_paths[gaps[i]])

        cmd = ["ffmpeg", "-y"]
        for p in inputs:
            cmd += ["-i", p]
        filt = "".join(f"[{i}:a]" for i in range(len(inputs))) + f"concat=n={len(inputs)}:v=0:a=1[out]"
        out_path = os.path.join(tmpdir, "out.mp3")
        cmd += ["-filter_complex", filt, "-map", "[out]",
                "-ar", str(TTS_SAMPLE_RATE), "-ac", "1", "-c:a", "libmp3lame", out_path]
        _run_ffmpeg(cmd, timeout=300)

        with open(out_path, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"


async def deepgram_transcribe(audio: bytes, content_type: str) -> List[dict]:
    """Pre-recorded transcription with word-level timestamps. Returns
    [{word, punctuated_word, start, end}] (empty on a shape we don't recognise).
    Raises RuntimeError for a missing key / HTTP failure."""
    key = settings.DEEPGRAM_API_KEY
    if not key:
        raise RuntimeError("no_deepgram_key")
    async with httpx.AsyncClient(timeout=300.0) as client:
        deepgram_model = (await ai_registry.get_model_config("stt_deepgram_content_rest")).model_name
        resp = await client.post(
            DEEPGRAM_URL,
            params={"model": deepgram_model, "smart_format": "true", "punctuate": "true"},
            headers={"Authorization": f"Token {key}", "Content-Type": content_type},
            content=audio,
        )
    if resp.status_code != 200:
        logger.error("[deepgram] HTTP %s: %s", resp.status_code, resp.text[:300])
        raise RuntimeError(f"deepgram_http_{resp.status_code}")
    try:
        return resp.json()["results"]["channels"][0]["alternatives"][0]["words"]
    except (KeyError, IndexError, TypeError):
        return []


def timestamped_lines(words: List[dict], words_per_line: int = 18) -> List[str]:
    """Group words into compact lines, each prefixed with the start time (seconds)
    of its first word: "[132.4] some words here". Small enough for one LLM pass, and
    the LLM reads the boundary timestamps straight off the accurate ASR output."""
    lines: List[str] = []
    for i in range(0, len(words), words_per_line):
        chunk = words[i:i + words_per_line]
        if not chunk:
            continue
        start = chunk[0].get("start", 0) or 0
        text = " ".join((w.get("punctuated_word") or w.get("word") or "") for w in chunk)
        lines.append(f"[{start:.1f}] {text}")
    return lines


def cut_segment(src_path: str, start: float, end: float) -> bytes:
    """Extract [start, end] seconds from an audio file as mp3 bytes. Uses `-ss` +
    `-t DURATION` (unambiguous, accurate — avoids the `-ss`/`-to` timeline gotcha)
    and re-encodes to the same 24kHz mono mp3 as generated clips. Blocking; call via
    run_sync. Lets an admin cut one full-test recording into per-section extracts."""
    duration = end - start
    if duration <= 0:
        raise TtsError("Each section's end time must be after its start time.")
    out_path = tempfile.mktemp(suffix=".mp3")
    try:
        _run_ffmpeg(
            ["ffmpeg", "-y", "-i", src_path, "-ss", str(start), "-t", str(duration),
             "-ar", str(TTS_SAMPLE_RATE), "-ac", "1", "-c:a", "libmp3lame", out_path],
            timeout=120,
        )
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(out_path)
        except OSError:
            pass


def _probe_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
        check=True, capture_output=True, timeout=30,
    )
    data = json.loads(result.stdout)
    return round(float(data["format"]["duration"]), 2)


async def probe_duration_seconds(audio_bytes: bytes) -> float:
    """ffprobe the stitched mp3 for its length in seconds. Blocking (subprocess),
    run via run_sync -- same pattern as _stitch/cut_segment above."""
    tmp_path = tempfile.mktemp(suffix=".mp3")
    try:
        with open(tmp_path, "wb") as f:
            f.write(audio_bytes)
        return await run_sync(_probe_duration, tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def transcript_hash(turns: List[dict]) -> str:
    """Deterministic hash over turn order + speaker labels + text. The one
    canonical definition of "has this extract's script changed" -- reused by
    audio generation (to stamp what was voiced), get_audio_status below (to
    detect staleness), and publish validation."""
    canonical = json.dumps(
        [[str(t.get("speaker", "")), str(t.get("text", ""))] for t in (turns or [])],
        ensure_ascii=True, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_audio_status(extract: Dict[str, Any]) -> str:
    """NOT_GENERATED / READY / OUTDATED for one extract. Never deletes audio on
    a transcript edit -- OUTDATED just means "stale, regenerate when ready";
    the old file stays live and playable until a fresh generate-audio call
    replaces it."""
    if not extract.get("audio_url") or not extract.get("audio_transcript_hash"):
        return "NOT_GENERATED"
    current = transcript_hash(extract.get("transcript") or [])
    return "READY" if current == extract["audio_transcript_hash"] else "OUTDATED"


async def _generate_monologue_audio(
    client: httpx.AsyncClient, turns: List[dict], voice: str, model: str,
) -> bytes:
    """One speaker. A single TTS call when the joined transcript fits inside one
    request (bypasses ffmpeg entirely); otherwise sentence-boundary chunks synthesized
    with the same voice/instructions and stitched with a small fixed gap."""
    speaker = turns[0]["speaker"]
    instructions = instructions_for_speaker(speaker)
    full_text = " ".join(t["text"].strip() for t in turns)

    if len(full_text) <= MAX_TURN_CHARS:
        return await _synthesize_turn(client, full_text, voice, model, instructions)

    chunks = _chunk_by_sentence(full_text, MAX_TURN_CHARS)
    segments = [await _synthesize_turn(client, c, voice, model, instructions) for c in chunks]
    gaps = [MONO_CHUNK_GAP_SECONDS] * (len(segments) - 1)
    return await run_sync(_stitch, segments, gaps)


async def _generate_dialogue_audio(
    client: httpx.AsyncClient, turns: List[dict], voice_map: Dict[str, str], model: str,
) -> bytes:
    """2+ speakers. One TTS call per turn (stable voice + role-aware instructions
    per speaker), stitched with a deterministic variable gap between turns."""
    segments = [
        await _synthesize_turn(
            client, t["text"], voice_map[t["speaker"]], model, instructions_for_speaker(t["speaker"]),
        )
        for t in turns
    ]
    gaps = [_deterministic_gap(t["text"]) for t in turns[:-1]]
    return await run_sync(_stitch, segments, gaps)


async def generate_two_speaker_audio(
    turns: List[dict],
    voices: Optional[Dict[str, str]] = None,
    model: Optional[str] = None,
) -> bytes:
    """turns: [{"speaker": str, "text": str}]. Returns one mp3 (bytes) -- stitched
    for dialogue, single-pass for a monologue (transcripts with exactly one distinct
    speaker), detected from the transcript itself rather than any OET part number.
    Raises TtsError for bad input (400-worthy), RuntimeError for a provider/ffmpeg
    failure (502-worthy). model=None resolves to the "tts_openai" purpose
    (Admin > AI Models) -- pass an explicit model to override."""
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("no_key")
    if model is None:
        model = (await ai_registry.get_model_config("tts_openai")).model_name
    if not turns:
        raise TtsError("Add at least one line of dialogue before generating audio.")
    if len(turns) > MAX_TURNS:
        raise TtsError(f"Too many lines (max {MAX_TURNS}). Split this into more sections.")
    for t in turns:
        if not t.get("text", "").strip():
            raise TtsError("Every line needs some text.")
        if len(t["text"]) > MAX_TURN_CHARS:
            raise TtsError(f"A line is too long (max {MAX_TURN_CHARS} characters) — split it into shorter turns.")

    speakers = [t["speaker"] for t in turns]
    voice_map = assign_voices(speakers, voices)

    async with httpx.AsyncClient(timeout=120.0) as client:
        if len(set(speakers)) == 1:
            return await _generate_monologue_audio(client, turns, voice_map[speakers[0]], model)
        return await _generate_dialogue_audio(client, turns, voice_map, model)
