"""
Test Deepgram STT endpointing behavior directly — no browser, no microphone, no manual speaking.

WHAT THIS DOES
1. Generates a synthetic speech clip with TWO sentences separated by a deliberate
   3-second silence (simulating a real thinking pause).
2. Streams that audio directly to Deepgram's WebSocket API — bypassing your backend
   and frontend entirely.
3. Logs every message Deepgram sends back, with timestamps, so you can see EXACTLY
   when Deepgram declares "speech_final" relative to when the pause happened.

WHY THIS MATTERS
Your backend currently uses endpointing=200 (200ms of silence = utterance finished).
Real speech pauses (thinking, breathing, hesitation) are often longer than 200ms.
If Deepgram fires "speech_final":true during the pause, BEFORE sentence 2 starts,
that confirms endpointing is too aggressive — and explains why it "stops listening"
before you're done talking.

If Deepgram does NOT fire early (waits correctly through the pause), the cutoff is
happening somewhere in YOUR frontend/backend code instead — a different bug.

SETUP
    pip install websockets gTTS pydub
    (requires ffmpeg installed and on PATH — check with `ffmpeg -version`)

    Set your Deepgram API key as an environment variable before running:
        Windows (PowerShell):  $env:DEEPGRAM_API_KEY = "your-key-here"
        Mac/Linux:              export DEEPGRAM_API_KEY="your-key-here"

    (Copy the value from backend/.env — do not paste it into this script directly,
    and do not commit this script anywhere with a key hardcoded.)

RUN
    python test_deepgram_endpointing.py

You can freely edit ENDPOINTING_MS below and re-run to compare behavior at
different settings (e.g. 200 vs 500 vs 800) without re-recording anything.
"""

import asyncio
import json
import os
import sys
import time

from gtts import gTTS
from pydub import AudioSegment

try:
    import websockets
except ImportError:
    print("Missing dependency. Run: pip install websockets gTTS pydub")
    sys.exit(1)

# ── Config — edit these to experiment ────────────────────────────────────────
ENDPOINTING_MS = int(os.environ.get("TEST_ENDPOINTING_MS", "200"))
PAUSE_SECONDS = 3             # deliberate silence between the two sentences
SENTENCE_1 = "Hello doctor, I have had chest pain since this morning."
SENTENCE_2 = "It started after I climbed the stairs at home."
MODEL = "nova-3"
LANGUAGE = "en-US"
# ──────────────────────────────────────────────────────────────────────────────

API_KEY = os.environ.get("DEEPGRAM_API_KEY")
if not API_KEY:
    print("ERROR: Set the DEEPGRAM_API_KEY environment variable first (see script header).")
    sys.exit(1)


def build_test_audio() -> str:
    """Generate sentence1 + silence + sentence2, exported as webm/opus (matches
    what MediaRecorder produces in the browser). Caches result locally so repeated
    runs (e.g. comparing different ENDPOINTING_MS values) don't re-hit gTTS's
    network endpoint every time — gTTS can rate-limit repeated automated calls."""
    out_path = "_test_audio.webm"
    meta_path = "_test_audio_meta.json"

    if os.path.exists(out_path) and os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        print("Using cached audio (delete _test_audio.webm + _test_audio_meta.json to regenerate).")
        print(f"  Sentence 1 ends at ~{meta['sentence1_end_s']:.1f}s")
        print(f"  Silence duration: {meta['silence_len_s']:.1f}s")
        print(f"  Sentence 2 starts at ~{meta['sentence2_start_s']:.1f}s")
        print(f"  Total duration: {meta['total_duration_s']:.1f}s\n")
        return out_path, meta["sentence1_end_s"], meta["sentence2_start_s"], meta["total_duration_s"]

    print("Generating TTS audio (network call to Google TTS)...")
    gTTS(SENTENCE_1).save("_part1.mp3")
    gTTS(SENTENCE_2).save("_part2.mp3")

    part1 = AudioSegment.from_mp3("_part1.mp3")
    silence = AudioSegment.silent(duration=PAUSE_SECONDS * 1000)
    part2 = AudioSegment.from_mp3("_part2.mp3")

    combined = part1 + silence + part2
    combined = combined.set_frame_rate(48000).set_channels(1)

    combined.export(out_path, format="webm", codec="libopus")

    sentence1_end_s = len(part1) / 1000
    silence_len_s = len(silence) / 1000
    sentence2_start_s = (len(part1) + len(silence)) / 1000
    total_duration_s = len(combined) / 1000

    with open(meta_path, "w") as f:
        json.dump({
            "sentence1_end_s": sentence1_end_s,
            "silence_len_s": silence_len_s,
            "sentence2_start_s": sentence2_start_s,
            "total_duration_s": total_duration_s,
        }, f)

    print(f"  Sentence 1 ends at ~{sentence1_end_s:.1f}s")
    print(f"  Silence duration: {silence_len_s:.1f}s (from {sentence1_end_s:.1f}s -> {sentence2_start_s:.1f}s)")
    print(f"  Sentence 2 starts at ~{sentence2_start_s:.1f}s")
    print(f"  Total duration: {total_duration_s:.1f}s\n")

    for f in ("_part1.mp3", "_part2.mp3"):
        os.remove(f)

    return out_path, sentence1_end_s, sentence2_start_s, total_duration_s


async def stream_to_deepgram(audio_path: str, sentence1_end_s: float, sentence2_start_s: float, total_duration_s: float):
    url = (
        "wss://api.deepgram.com/v1/listen"
        f"?model={MODEL}"
        f"&language={LANGUAGE}"
        f"&interim_results=true"
        f"&endpointing={ENDPOINTING_MS}"
        f"&smart_format=true"
        f"&encoding=opus"
        f"&container=webm"
    )

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    print(f"Connecting to Deepgram (endpointing={ENDPOINTING_MS}ms)...\n")
    start_time = time.monotonic()

    # NOTE: websockets 12.x uses extra_headers; websockets 13+ renamed this to
    # additional_headers. This script targets 12.x (matches the backend's installed
    # version, confirmed earlier). If you upgrade websockets later, change this back.
    async with websockets.connect(url, extra_headers={"Authorization": f"Token {API_KEY}"}, open_timeout=60) as ws:

        async def sender():
            # Simulate MediaRecorder sending ~250ms chunks in real time.
            # Use the ACTUAL audio duration (not a guess) so pacing matches real-time.
            target_chunk_duration_s = 0.25
            num_chunks = max(1, int(total_duration_s / target_chunk_duration_s))
            chunk_size = max(1, len(audio_bytes) // num_chunks)
            delay = total_duration_s / num_chunks

            pos = 0
            while pos < len(audio_bytes):
                chunk = audio_bytes[pos:pos + chunk_size]
                await ws.send(chunk)
                pos += chunk_size
                await asyncio.sleep(delay)

            await asyncio.sleep(1)
            await ws.send(json.dumps({"type": "CloseStream"}))

        async def receiver():
            async for message in ws:
                elapsed = time.monotonic() - start_time
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    print(f"[{elapsed:6.2f}s] non-JSON message: {message}")
                    continue

                msg_type = data.get("type", "?")

                if msg_type == "Results":
                    alt = data.get("channel", {}).get("alternatives", [{}])[0]
                    transcript = alt.get("transcript", "")
                    is_final = data.get("is_final", False)
                    speech_final = data.get("speech_final", False)
                    if transcript:
                        tag = "FINAL" if is_final else "interim"
                        extra = " <-- SPEECH_FINAL (Deepgram thinks utterance is DONE)" if speech_final else ""
                        print(f"[{elapsed:6.2f}s] [{tag:7}] \"{transcript}\"{extra}")
                elif msg_type == "UtteranceEnd":
                    print(f"[{elapsed:6.2f}s] [UtteranceEnd event fired]")
                elif msg_type == "Metadata":
                    pass
                else:
                    print(f"[{elapsed:6.2f}s] [{msg_type}] {data}")

        await asyncio.gather(sender(), receiver())

    print("\nDone. Compare the timestamps above against:")
    print(f"  Sentence 1 ends ~{sentence1_end_s:.1f}s (actual, from generated audio)")
    print(f"  Pause: ~{sentence1_end_s:.1f}s -> ~{sentence2_start_s:.1f}s")
    print(f"  Sentence 2 starts ~{sentence2_start_s:.1f}s")
    print("\nIf SPEECH_FINAL fires during the pause (before sentence 2's transcript")
    print("appears), that confirms endpointing is cutting you off too early.")


if __name__ == "__main__":
    path, s1_end, s2_start, total_dur = build_test_audio()
    asyncio.run(stream_to_deepgram(path, s1_end, s2_start, total_dur))
    print("\n(Audio cached as _test_audio.webm — future runs with different ENDPOINTING_MS")
    print(" will reuse it instantly. Delete _test_audio.webm + _test_audio_meta.json to")
    print(" regenerate with different sentences.)")