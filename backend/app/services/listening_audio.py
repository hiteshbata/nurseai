"""Two-speaker TTS for Listening extracts.

OpenAI TTS voices each speaker turn (OpenAI has no native multi-speaker -- one
voice per call), then ffmpeg stitches the turns into one mp3 with a short pause
between them. Admin-only content generation, low volume, so per-turn API calls +
an ffmpeg re-encode are fine.

The transcript is a list of turns [{"speaker": "...", "text": "..."}]. Each
distinct speaker label maps to a distinct OpenAI voice so a consult sounds like
two different people.
"""
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.threading import run_sync

logger = logging.getLogger(__name__)

OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"
# Voices supported by BOTH tts-1 and gpt-4o-mini-tts. Ordered so the first two
# distinct speakers get clearly different-sounding voices by default.
OPENAI_VOICES = ["onyx", "nova", "echo", "shimmer", "alloy", "fable"]
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
MAX_TURN_CHARS = 4000   # OpenAI TTS hard limit is 4096 chars/request; stay under
MAX_TURNS = 120
GAP_SECONDS = 0.6       # natural pause between speaker turns
TTS_SAMPLE_RATE = 24000  # OpenAI TTS mp3 output rate; normalize the stitch to it


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


async def _synthesize_turn(client: httpx.AsyncClient, text: str, voice: str, model: str) -> bytes:
    resp = await client.post(
        OPENAI_TTS_URL,
        headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
        json={"model": model, "input": text, "voice": voice, "response_format": "mp3"},
    )
    if resp.status_code != 200:
        # resp.text may include OpenAI's own error JSON; log a slice, never the key.
        logger.error("[listening tts] OpenAI HTTP %s: %s", resp.status_code, resp.text[:300])
        raise RuntimeError(f"openai_tts_http_{resp.status_code}")
    return resp.content


def _run_ffmpeg(cmd: List[str], timeout: int) -> None:
    subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)


def _stitch(segments: List[bytes], gap_seconds: float) -> bytes:
    """Concatenate per-turn mp3 bytes into one mp3, inserting `gap_seconds` of
    silence between turns. Uses the ffmpeg concat FILTER (decodes + re-encodes),
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

        sil_path = os.path.join(tmpdir, "sil.mp3")
        _run_ffmpeg(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             f"anullsrc=r={TTS_SAMPLE_RATE}:cl=mono", "-t", str(gap_seconds),
             "-c:a", "libmp3lame", sil_path],
            timeout=30,
        )

        # interleave: seg0, sil, seg1, sil, ..., segN
        inputs: List[str] = []
        for i, p in enumerate(seg_paths):
            inputs.append(p)
            if i != len(seg_paths) - 1:
                inputs.append(sil_path)

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
        resp = await client.post(
            DEEPGRAM_URL,
            params={"model": "nova-2", "smart_format": "true", "punctuate": "true"},
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


async def generate_two_speaker_audio(
    turns: List[dict],
    voices: Optional[Dict[str, str]] = None,
    model: str = DEFAULT_TTS_MODEL,
) -> bytes:
    """turns: [{"speaker": str, "text": str}]. Returns one stitched mp3 (bytes).
    Raises TtsError for bad input (400-worthy), RuntimeError for a provider/ffmpeg
    failure (502-worthy)."""
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("no_key")
    if not turns:
        raise TtsError("Add at least one line of dialogue before generating audio.")
    if len(turns) > MAX_TURNS:
        raise TtsError(f"Too many lines (max {MAX_TURNS}). Split this into more sections.")
    for t in turns:
        if not t.get("text", "").strip():
            raise TtsError("Every line needs some text.")
        if len(t["text"]) > MAX_TURN_CHARS:
            raise TtsError(f"A line is too long (max {MAX_TURN_CHARS} characters) — split it into shorter turns.")

    voice_map = assign_voices([t["speaker"] for t in turns], voices)

    segments: List[bytes] = []
    async with httpx.AsyncClient(timeout=120.0) as client:
        for t in turns:
            segments.append(await _synthesize_turn(client, t["text"], voice_map[t["speaker"]], model))

    return await run_sync(_stitch, segments, GAP_SECONDS)
