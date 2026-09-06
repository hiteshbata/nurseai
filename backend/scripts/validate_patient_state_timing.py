"""
Standalone live-validation script for the "Patient-State Feedback Loop
Timing" task (docs/audits/speaking-step3, see repo history/PR description
for the full spec).

GOAL: empirically determine whether a PatientState instructions update
(app.services.patient_state + app.routers.speaking_realtime) reliably
reaches the OpenAI Realtime API before the patient's NEXT response begins
generating, given that OpenAI's server-side VAD can auto-trigger a response
before our whisper-transcription-dependent TranscriptFinal event arrives.

Deliberately reuses REAL, unmodified production code -- no mocks, no new
architecture:
  - app.services.realtime.openai_adapter.OpenAIRealtimeAdapter talks the
    actual OpenAI Realtime wire protocol to the actual API.
  - app.routers.speaking_realtime._SessionMetrics /
    _sync_patient_state_if_changed / _build_realtime_system_prompt are the
    exact functions the live WebSocket router calls.
  - app.services.patient_state.derive_patient_state is the exact state
    derivation logic.

What's NOT reused: the WebSocket router itself, Supabase auth/session
quota/transcript persistence. The race being measured lives entirely
between the router's event handlers and the adapter -- auth/billing is
unrelated plumbing, and driving it would require a real QA user session
just to reach the code path this script calls directly. Step 9 (reconnect)
is validated by re-deriving PatientState from this run's own transcript
(the exact shape _load_prior_history reconstructs from session_transcripts
rows) and opening a second live connection with it -- the DB round-trip
itself already has unit coverage in
tests/test_speaking_realtime_router.py::test_reconnect_restores_patient_state_from_prior_transcript.

Candidate turns are synthesized via OpenAI's TTS endpoint into real PCM16
audio (not typed text), so whisper-1 has to actually transcribe them same
as a real candidate would, preserving the real race condition.

Usage:
    cd backend
    python scripts/validate_patient_state_timing.py

Requires OPENAI_API_KEY (reads backend/.env.qa by default -- see
ENVIRONMENT below) and network access to api.openai.com. Costs a small
amount of real OpenAI usage (~5 short realtime turns + TTS).
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "qa")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.routers.speaking_realtime import (  # noqa: E402
    _SessionMetrics,
    _build_realtime_system_prompt,
    _sync_patient_state_if_changed,
)
from app.services.patient_state import derive_patient_state, render_patient_state_prompt  # noqa: E402
from app.services.realtime.events import (  # noqa: E402
    InstructionsAcked,
    Interrupted,
    ProviderError,
    ResponseCreated,
    ResponseDone,
    SessionReady,
    SpeechStopped,
    TranscriptDelta,
    TranscriptFinal,
)
from app.services.realtime.openai_adapter import OpenAIRealtimeAdapter  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(relativeCreated)8dms %(levelname)s %(message)s")
logger = logging.getLogger("validate_patient_state_timing")

# Step 4's deterministic scenario: hidden info only reveals if asked
# directly, one emotional trigger tied to the surgery topic.
SCENARIO_CARD = {
    "patient_name": "Maria Santos",
    "age": 58,
    "condition": "Scheduled for gallbladder surgery tomorrow morning",
    "mood": "Anxious",
    "background": "Retired teacher, lives alone, worried about the operation.",
    "instructions_for_ai": (
        "You are anxious about tomorrow's surgery. Speak hesitantly, in short sentences. "
        "Only reveal that you stopped taking your prescribed heart medication if the nurse "
        "asks directly about your medication -- do not volunteer it unprompted."
    ),
    "emotional_triggers": ["Mention of the surgery itself or being put under anesthesia"],
    "questions_to_ask": ["Ask whether the surgery is really necessary"],
    "information_to_withhold": [
        "I stopped taking my heart medication two weeks ago because it was making me dizzy"
    ],
}

TURNS = [
    # (label, nurse_text, expect_interrupt)
    ("turn1_reveal_probe", "Hello Maria, I'm one of the nurses looking after you today. Are you taking your medication regularly at home?", False),
    ("turn2_short", "Any allergies?", False),
    ("turn3_emotional_trigger", "How are you feeling about tomorrow's surgery?", False),
    ("turn4_interrupt", "Sorry to interrupt, one more quick question --", True),
]

RECONNECT_TURN = "Just to confirm what you told me earlier -- you said you'd stopped taking your heart medication, is that still the case?"


async def synthesize_pcm16(client: httpx.AsyncClient, text: str) -> bytes:
    resp = await client.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
        json={"model": "tts-1", "voice": "onyx", "input": text, "response_format": "pcm"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.content


async def feed_audio(adapter: OpenAIRealtimeAdapter, pcm: bytes, trailing_silence_s: float = 0.8) -> None:
    chunk = 4800  # 100ms @ 24kHz/16-bit mono
    for i in range(0, len(pcm), chunk):
        await adapter.send_audio(pcm[i:i + chunk])
        await asyncio.sleep(0.05)
    silence = b"\x00" * int(24000 * 2 * trailing_silence_s)
    for i in range(0, len(silence), chunk):
        await adapter.send_audio(silence[i:i + chunk])
        await asyncio.sleep(0.05)


async def consume_events(adapter: OpenAIRealtimeAdapter, metrics: _SessionMetrics, card: dict, tag: str) -> None:
    async for item in adapter.receive_events():
        if isinstance(item, (bytes, bytearray)):
            continue

        if isinstance(item, SessionReady):
            logger.info("[%s] SessionReady", tag)

        elif isinstance(item, TranscriptDelta):
            metrics.append_patient_delta(item.delta)

        elif isinstance(item, TranscriptFinal):
            metrics.transcript_turns.append({"role": item.role, "text": item.transcript})
            metrics.last_transcript_final_at = time.monotonic()
            logger.info("[%s] TranscriptFinal(nurse)=%r", tag, item.transcript)
            await _sync_patient_state_if_changed(adapter, card, metrics, "openai", "transcript_final")

        elif isinstance(item, ResponseDone):
            metrics.flush_patient_turn()
            said = metrics.transcript_turns[-1]["text"] if metrics.transcript_turns else ""
            logger.info("[%s] ResponseDone patient_said=%r", tag, said)
            await _sync_patient_state_if_changed(adapter, card, metrics, "openai", "response_done")

        elif isinstance(item, SpeechStopped):
            now = time.monotonic()
            if metrics.last_speech_stopped_at is not None and (
                metrics.last_transcript_final_at is None
                or metrics.last_transcript_final_at < metrics.last_speech_stopped_at
            ):
                metrics.stale_transcript_at_next_speech_count += 1
                logger.warning("[%s] STALE TRANSCRIPT: new turn started before previous turn's transcript finalized", tag)
            metrics.last_speech_stopped_at = now
            logger.info("[%s] SpeechStopped", tag)

        elif isinstance(item, ResponseCreated):
            logger.info("[%s] ResponseCreated", tag)
            sample = metrics.record_response_created()
            if sample is not None:
                logger.info("[%s] TIMING SAMPLE %s", tag, sample)

        elif isinstance(item, InstructionsAcked):
            logger.info("[%s] InstructionsAcked (session.updated)", tag)

        elif isinstance(item, Interrupted):
            metrics.interrupted_count += 1
            logger.info("[%s] Interrupted (barge-in) -- cancelling response", tag)
            await adapter.cancel_response()

        elif isinstance(item, ProviderError):
            metrics.error_count += 1
            logger.error("[%s] ProviderError %s", tag, item.message)


async def wait_for_new_patient_turn(metrics: _SessionMetrics, baseline: int, timeout: float = 25.0) -> None:
    waited = 0.0
    while len(metrics.transcript_turns) <= baseline:
        await asyncio.sleep(0.1)
        waited += 0.1
        if waited >= timeout:
            logger.warning("wait_for_new_patient_turn timed out after %.1fs", timeout)
            return


async def run_session(card: dict, initial_history: list[dict], turns: list[tuple], tag: str) -> _SessionMetrics:
    initial_state = derive_patient_state(card, initial_history)
    system_prompt = _build_realtime_system_prompt(card, state=initial_state)
    adapter = OpenAIRealtimeAdapter(
        system_prompt=system_prompt, voice="alloy",
        api_key=settings.OPENAI_API_KEY, model=settings.OPENAI_REALTIME_MODEL_MINI,
    )
    await adapter.connect()
    metrics = _SessionMetrics(
        provider="openai", model=settings.OPENAI_REALTIME_MODEL_MINI, session_id=None,
        user_id="validation-script", scenario_id=None,
        prior_history=initial_history, initial_state=initial_state,
    )
    consumer_task = asyncio.create_task(consume_events(adapter, metrics, card, tag))

    async with httpx.AsyncClient() as tts_client:
        for label, text, expect_interrupt in turns:
            baseline = len(metrics.transcript_turns)
            logger.info("=== %s / %s: nurse says %r ===", tag, label, text)
            pcm = await synthesize_pcm16(tts_client, text)
            if expect_interrupt:
                # Fire mid previous response instead of waiting for it to
                # finish, to exercise the barge-in / Interrupted path
                # (Step 5: "candidate interruption").
                await asyncio.sleep(0.6)
            await feed_audio(adapter, pcm)
            await wait_for_new_patient_turn(metrics, baseline)

    await asyncio.sleep(3.0)  # drain trailing events (last state sync, InstructionsAcked)
    await adapter.disconnect()
    consumer_task.cancel()
    try:
        await consumer_task
    except (asyncio.CancelledError, Exception):
        pass
    return metrics


def print_report(metrics: _SessionMetrics, tag: str) -> None:
    print(f"\n--- {tag} summary ---")
    print(f"transcript_turns: {len(metrics.transcript_turns)}")
    for t in metrics.transcript_turns:
        print(f"  [{t['role']}] {t['text']}")
    print(f"interrupted_count: {metrics.interrupted_count}")
    print(f"stale_transcript_at_next_speech_count: {metrics.stale_transcript_at_next_speech_count}")
    print(f"state_timing_samples ({len(metrics.state_timing_samples)}):")
    for s in metrics.state_timing_samples:
        print(f"  {s}")
    if metrics.patient_state:
        print("final_patient_state:")
        print(f"  revealed_information: {metrics.patient_state.revealed_information}")
        print(f"  fired_emotional_triggers: {metrics.patient_state.fired_emotional_triggers}")


async def main() -> None:
    if not settings.OPENAI_API_KEY:
        print("OPENAI_API_KEY not set (check ENVIRONMENT/.env.qa) -- aborting.")
        return

    metrics1 = await run_session(SCENARIO_CARD, [], TURNS, tag="session1")
    print_report(metrics1, "session1")

    # Step 9: reconnect -- rebuild history in the exact {"role","content"}
    # shape _load_prior_history produces from session_transcripts rows, and
    # open a fresh live connection seeded from it.
    prior_history = [{"role": t["role"], "content": t["text"]} for t in metrics1.transcript_turns]
    restored_state = derive_patient_state(SCENARIO_CARD, prior_history)
    print("\n--- reconnect: restored state before new connection ---")
    print(render_patient_state_prompt(restored_state))

    metrics2 = await run_session(
        SCENARIO_CARD, prior_history, [("reconnect_confirm", RECONNECT_TURN, False)], tag="session2_reconnect",
    )
    print_report(metrics2, "session2_reconnect")


if __name__ == "__main__":
    asyncio.run(main())
