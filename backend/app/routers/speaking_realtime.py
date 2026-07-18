"""
WebSocket gateway for live, low-latency voice roleplay in OET Speaking
practice. Provider-agnostic: talks to whichever realtime voice provider
VOICE_PROVIDER selects (see app/services/realtime/factory.py) through the
common RealtimeProviderAdapter interface. Adapters translate one provider's
wire protocol into the canonical events in app/services/realtime/events.py
and contain no business logic; every rule below (auth, quota, session
lifecycle, timers, cost tracking, fallback) lives in this router so it's
identical no matter which provider is active.

Frontend <-> backend wire format on /speaking/realtime/stream is unchanged
from the OpenAI-only version, plus a few additive fields/event types a
provider-agnostic client needs (frontend already ignores unknown event
types, so none of this breaks the deployed hook until it's updated to use
the new fields):
  1. Frontend sends one JSON handshake message first:
       {"token": "<supabase access token>", "scenario_id": 12, "session_id": 456}
  2. Backend replies with the quota session id AND the audio config the
     active provider requires -- the frontend must use these sample rates
     for capture/playback instead of a hardcoded constant, since OpenAI and
     Gemini Live do not use the same input rate:
       {"type": "session.ready", "session_id": 456, "provider": "openai",
        "input_sample_rate": 24000, "output_sample_rate": 24000, "audio_encoding": "pcm16"}
  3. Frontend then streams raw PCM16 mono audio (at input_sample_rate) as
     binary WebSocket frames.
  4. Backend sends JSON control events:
       {"type": "transcript.delta", "role": "patient", "delta": "..."}
       {"type": "transcript.final", "role": "nurse", "transcript": "..."}
       {"type": "response.done"}
       {"type": "interrupted"}
       {"type": "session.warning", "seconds_remaining": 30}
       {"type": "session.ended", "reason": "timeout" | "client_closed" | "provider_error"}
       {"type": "error", "error": "...", "fallback_available": true}   -- fallback_available
         is only set when the realtime provider itself is unusable; the frontend
         should fall back to the existing Deepgram/Gemini/TTS pipeline
         (useSpeakingSession) using the SAME session_id rather than treat this
         as a dead end -- the quota session was already charged and is still valid.
     and raw PCM16 audio bytes (at output_sample_rate) as binary frames.
"""
import asyncio
import json
import logging
import time

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
import websockets.exceptions as ws_exc

from app.core.config import settings
from app.core.supabase import get_supabase, get_auth_client
from app.core.threading import run_sync
from app.routers.auth import UserInfo
from app.routers.sessions import check_and_increment_session, validate_session
from app.core.error_utils import redact_api_keys
from app.services.realtime import (
    Interrupted,
    ProviderConnectError,
    ProviderError,
    ResponseDone,
    SessionReady,
    TranscriptDelta,
    TranscriptFinal,
    capabilities_for,
    get_adapter_class,
)
from app.services.realtime.gemini_adapter import map_gender_to_gemini_voice
from app.services.realtime.pricing import estimate_realtime_cost
from app.services.cost_tracking import increment_session_cost, log_ai_usage
from app.services.ai_scoring import MEDICAL_JARGON
from app.core.feature_flags import close_if_disabled

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/speaking", tags=["speaking"])

REALTIME_HANDSHAKE_TIMEOUT_SECONDS = 10
PCM16_BYTES_PER_SAMPLE = 2


def _map_gender_to_openai_voice(gender: str | None) -> str:
    if gender == "male":
        return "ash"
    if gender == "female":
        return "shimmer"
    return "alloy"


VOICE_MAPPERS = {
    "openai": _map_gender_to_openai_voice,
    "gemini": map_gender_to_gemini_voice,
}


def _get_voice_provider() -> str:
    """DB setting (admin panel) overrides the env default so switching
    providers doesn't require a redeploy."""
    try:
        data = get_supabase().table("settings").select("value").eq("key", "voice_provider").execute()
        if data.data and data.data[0]["value"]:
            return data.data[0]["value"]
    except Exception:
        pass
    return settings.VOICE_PROVIDER


def _provider_credentials(provider: str) -> tuple[str, str]:
    if provider == "openai":
        return settings.OPENAI_API_KEY, settings.OPENAI_REALTIME_MODEL
    if provider == "gemini":
        return settings.GEMINI_API_KEY, settings.GEMINI_LIVE_MODEL
    raise ValueError(f"Unknown VOICE_PROVIDER: {provider!r}")


def _build_realtime_system_prompt(interlocutor_card: dict) -> str:
    """Patient persona for the realtime voice path.

    The JARGON RULE below is the realtime equivalent of the legacy pipeline's
    detect_jargon() short-circuit (services/ai_scoring.py), and shares its term
    list so the two paths stop on the same words. The mechanism differs by
    necessity: legacy is text turn-based, so it can match the nurse's message
    and return a canned interrupt before the model is ever called -- fully
    deterministic. Here the provider hears the audio and starts answering
    before we see TranscriptFinal, so a deterministic intercept would mean
    cancelling a half-spoken response and re-injecting audio. Instructing the
    persona is the native mechanism for a realtime model.

    The trade-off: realtime jargon interrupts are model-compliance, not a
    guarantee. Before making the rollout percentage large, spot-check that the
    active provider actually stops on an unexplained term -- the landing page
    sells this behaviour.
    """
    card = interlocutor_card or {}
    emotional_triggers = card.get("emotional_triggers", [])
    questions_to_ask = card.get("questions_to_ask", card.get("concerns", []))
    info_to_withhold = card.get("information_to_withhold", [])
    instructions = card.get("instructions_for_ai", card.get("persona", ""))

    return f"""You are playing a patient in an OET nursing roleplay exam, speaking live with a nursing student over voice. Follow this card EXACTLY.

PATIENT PROFILE:
- Name: {card.get('patient_name', 'Patient')}
- Age: {card.get('age', 'adult')} years old
- Condition: {card.get('condition', 'Not specified')}
- Mood: {card.get('mood', 'Cooperative')}
- Background: {card.get('background', '')}

PERSONA & BEHAVIOUR:
{instructions}

EMOTIONAL TRIGGERS (react to these topics with genuine emotion):
{chr(10).join(f'- {t}' for t in emotional_triggers) if emotional_triggers else '- Show general anxiety about your condition'}

QUESTIONS YOU MUST ASK (spread these across the conversation naturally):
{chr(10).join(f'- {q}' for q in questions_to_ask) if questions_to_ask else '- Ask about your treatment plan'}

INFORMATION TO WITHHOLD (only reveal if the nurse asks directly):
{chr(10).join(f'- {i}' for i in info_to_withhold) if info_to_withhold else '- Do not volunteer extra information'}

JARGON RULE (CRITICAL):
- You are not a medical person and do not know medical words. If the nurse uses a medical term and does NOT immediately explain it in plain words, stop and ask what it means before responding to anything else — that is the single most useful thing you do for this nurse.
- Ask the way a real patient would, e.g. "I'm sorry sister, I don't understand that word — what does that mean in simple terms?"
- If the nurse does explain the term in plain words in the same breath ("an arrhythmia, that means an uneven heartbeat"), do NOT interrupt — just respond naturally.
- Always stop for these terms when unexplained: {', '.join(MEDICAL_JARGON)}.

VOICE & DELIVERY RULES (CRITICAL):
- Never use text-based stage directions (no asterisks, no brackets, no "[sighs]", no "*wincing*"). Express all emotion — anxiety, pain, hesitation — natively through your vocal tone, pacing, breath, and pauses, never through written description.
- Speak naturally: hesitate, trail off, or pause when anxious, exactly as a real patient would.
- Keep responses short and conversational — 2-4 sentences per turn.
- Stay fully in character at all times. Never break character to explain yourself or acknowledge you are an AI.
- Do NOT reveal withheld information unless the nurse specifically asks.
- Never give medical advice or diagnose yourself."""


class _SessionMetrics:
    """Router-owned bookkeeping for cost tracking and the provider
    comparison view -- adapters never see or touch this."""

    __slots__ = (
        "provider", "session_id", "user_id", "started_at", "input_bytes", "output_bytes",
        "interrupted_count", "error_count", "ended_reason", "provider_ready_at",
    )

    def __init__(self, provider: str, session_id: int, user_id: str):
        self.provider = provider
        self.session_id = session_id
        self.user_id = user_id
        self.started_at = time.monotonic()
        self.provider_ready_at: float | None = None
        self.input_bytes = 0
        self.output_bytes = 0
        self.interrupted_count = 0
        self.error_count = 0
        self.ended_reason = "unknown"


def _insert_realtime_metrics_row_sync(row: dict) -> None:
    get_supabase().table("realtime_session_metrics").insert(row).execute()


async def _persist_realtime_metrics(metrics: _SessionMetrics, capabilities) -> None:
    duration_seconds = time.monotonic() - metrics.started_at
    input_seconds = metrics.input_bytes / (capabilities.input_sample_rate * PCM16_BYTES_PER_SAMPLE)
    output_seconds = metrics.output_bytes / (capabilities.output_sample_rate * PCM16_BYTES_PER_SAMPLE)
    cost = estimate_realtime_cost(metrics.provider, input_seconds, output_seconds)
    time_to_ready_ms = (
        round((metrics.provider_ready_at - metrics.started_at) * 1000)
        if metrics.provider_ready_at is not None else None
    )

    try:
        await run_sync(_insert_realtime_metrics_row_sync, {
            "session_usage_id": metrics.session_id,
            "provider": metrics.provider,
            "duration_seconds": round(duration_seconds, 2),
            "input_audio_seconds": round(input_seconds, 2),
            "output_audio_seconds": round(output_seconds, 2),
            "realtime_cost_usd": cost.realtime_usd,
            "time_to_ready_ms": time_to_ready_ms,
            "interrupted_count": metrics.interrupted_count,
            "error_count": metrics.error_count,
            "ended_reason": metrics.ended_reason,
            "capabilities_snapshot": {
                "supports_barge_in": capabilities.supports_barge_in,
                "supports_partial_transcripts": capabilities.supports_partial_transcripts,
                "input_sample_rate": capabilities.input_sample_rate,
                "output_sample_rate": capabilities.output_sample_rate,
            },
        })
    except Exception as e:
        # Cost/metrics logging must never take down a live session or mask
        # the real teardown reason.
        logger.warning("[REALTIME_METRICS_PERSIST_FAILED] %s", str(e)[:300])

    # Rolled up onto the umbrella session_usage ledger row too, so cost
    # reporting doesn't require joining realtime_session_metrics for the
    # (much more common) case of a session that never reconnected.
    await increment_session_cost(metrics.session_id, provider=metrics.provider, realtime_cost_usd=cost.realtime_usd)

    await log_ai_usage(
        "realtime", metrics.provider, cost.realtime_usd,
        user_id=metrics.user_id, session_id=metrics.session_id, is_estimate=True,
        detail={"input_seconds": round(input_seconds, 2), "output_seconds": round(output_seconds, 2)},
    )


async def _send_json_safe(websocket: WebSocket, payload: dict) -> bool:
    try:
        await websocket.send_json(payload)
        return True
    except (RuntimeError, ws_exc.ConnectionClosed):
        return False


@router.websocket("/realtime/stream")
async def realtime_stream(websocket: WebSocket):
    await websocket.accept()

    if await close_if_disabled(websocket, "voice_realtime"):
        return

    init_message = None
    try:
        init_message = await asyncio.wait_for(
            websocket.receive_json(), timeout=REALTIME_HANDSHAKE_TIMEOUT_SECONDS
        )
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError, KeyError):
        init_message = None

    token = init_message.get("token") if isinstance(init_message, dict) else None
    raw_scenario_id = init_message.get("scenario_id") if isinstance(init_message, dict) else None

    user = None
    if token:
        try:
            auth_result = await run_sync(get_auth_client().auth.get_user, token)
            user = auth_result.user
        except Exception as e:
            logger.warning("Realtime stream auth failed: %s", redact_api_keys(str(e)[:200]))
            user = None

    scenario_id = None
    if raw_scenario_id is not None:
        try:
            scenario_id = int(raw_scenario_id)
        except (TypeError, ValueError):
            scenario_id = None

    if not user or scenario_id is None:
        await _send_json_safe(websocket, {"type": "error", "error": "Unauthorized or missing scenario_id"})
        await websocket.close(code=4401, reason="Unauthorized")
        return

    logger.info("Realtime stream authenticated | user_id=%s scenario_id=%s", user.id, scenario_id)

    provider = _get_voice_provider()
    try:
        capabilities = capabilities_for(provider)
        adapter_class = get_adapter_class(provider)
    except ValueError as e:
        logger.error("[REALTIME_CONFIG_ERROR] %s", e)
        await _send_json_safe(websocket, {"type": "error", "error": "Voice provider misconfigured"})
        await websocket.close()
        return

    api_key, model = _provider_credentials(provider)
    if not api_key:
        logger.error("[REALTIME_CONFIG_ERROR] API key not configured for provider=%s", provider)
        await _send_json_safe(websocket, {"type": "error", "error": f"{provider} voice provider not configured"})
        await websocket.close()
        return

    supabase = get_supabase()

    # Reuse the session minted by the text-chat flow if the client has one;
    # otherwise charge a new one now. Mirrors POST /speaking/chat exactly so
    # a realtime conversation can't dodge the monthly session quota.
    session_id = init_message.get("session_id") if isinstance(init_message, dict) else None
    if session_id is not None and not await run_sync(validate_session, user.id, session_id):
        session_id = None
    if session_id is None:
        try:
            current_user = UserInfo(id=user.id, email=user.email)
            usage = await run_sync(check_and_increment_session, current_user)
            session_id = usage["session_id"]
        except HTTPException as e:
            await _send_json_safe(websocket, {"type": "error", "error": "session_limit_reached", "detail": e.detail})
            await websocket.close(code=4429, reason="session_limit_reached")
            return

    scenario_data = await run_sync(
        supabase.table("scenarios").select("*").eq("id", scenario_id).eq("is_active", True).execute
    )
    if not scenario_data.data:
        await _send_json_safe(websocket, {"type": "error", "error": "Scenario not found"})
        await websocket.close(code=4404, reason="Scenario not found")
        return

    scenario = scenario_data.data[0]
    interlocutor_card = scenario.get("interlocutor_card", {})
    system_prompt = _build_realtime_system_prompt(interlocutor_card)
    voice = VOICE_MAPPERS[provider](scenario.get("patient_gender"))

    # Sent BEFORE the provider connection is attempted -- and carries the
    # audio config the frontend must capture/play back at -- so a slow or
    # failed provider handshake can never (a) leave the frontend guessing
    # its sample rate or (b) cause a duplicate quota charge on client retry.
    ready_sent = await _send_json_safe(websocket, {
        "type": "session.ready",
        "session_id": session_id,
        "provider": provider,
        "input_sample_rate": capabilities.input_sample_rate,
        "output_sample_rate": capabilities.output_sample_rate,
        "audio_encoding": capabilities.input_audio_encoding,
    })
    if not ready_sent:
        return

    adapter = adapter_class(system_prompt=system_prompt, voice=voice, api_key=api_key, model=model)
    metrics = _SessionMetrics(provider=provider, session_id=session_id, user_id=user.id)

    try:
        await adapter.connect()
    except ProviderConnectError as e:
        logger.error("[REALTIME_CONNECT_FAIL] provider=%s detail=%s", provider, str(e)[:500])
        await _send_json_safe(websocket, {
            "type": "error",
            "error": "voice_provider_unavailable",
            "fallback_available": True,
            "session_id": session_id,
        })
        await websocket.close(code=4503, reason="provider_unavailable")
        return

    _done = asyncio.Event()

    async def forward_client_audio():
        try:
            done_task = asyncio.create_task(_done.wait())
            while not _done.is_set():
                recv_task = asyncio.create_task(websocket.receive_bytes())
                finished, _pending = await asyncio.wait(
                    {recv_task, done_task}, return_when=asyncio.FIRST_COMPLETED,
                )
                if recv_task in finished:
                    try:
                        data = recv_task.result()
                    except WebSocketDisconnect:
                        return
                    metrics.input_bytes += len(data)
                    try:
                        await adapter.send_audio(data)
                    except Exception:
                        return
                else:
                    recv_task.cancel()
                    try:
                        await recv_task
                    except asyncio.CancelledError:
                        pass
                    break
        except WebSocketDisconnect:
            logger.info("Client WebSocket disconnected — stopping audio forward")
        except Exception as e:
            logger.warning("realtime forward_client_audio error: %s", str(e)[:200])
        finally:
            if metrics.ended_reason == "unknown":
                metrics.ended_reason = "client_closed"
            _done.set()
            await adapter.disconnect()

    async def forward_provider_events():
        try:
            async for item in adapter.receive_events():
                if _done.is_set():
                    break

                if isinstance(item, (bytes, bytearray)):
                    metrics.output_bytes += len(item)
                    try:
                        await websocket.send_bytes(item)
                    except (RuntimeError, ws_exc.ConnectionClosed):
                        return
                    continue

                if isinstance(item, SessionReady):
                    metrics.provider_ready_at = time.monotonic()
                    continue

                if isinstance(item, TranscriptDelta):
                    if not await _send_json_safe(websocket, {
                        "type": "transcript.delta", "role": item.role, "delta": item.delta,
                    }):
                        return

                elif isinstance(item, TranscriptFinal):
                    if not await _send_json_safe(websocket, {
                        "type": "transcript.final", "role": item.role, "transcript": item.transcript,
                    }):
                        return

                elif isinstance(item, ResponseDone):
                    if not await _send_json_safe(websocket, {"type": "response.done"}):
                        return

                elif isinstance(item, Interrupted):
                    metrics.interrupted_count += 1
                    if not await _send_json_safe(websocket, {"type": "interrupted"}):
                        return
                    await adapter.cancel_response()

                elif isinstance(item, ProviderError):
                    metrics.error_count += 1
                    payload = {"type": "error", "error": item.message}
                    if not item.recoverable:
                        payload["fallback_available"] = True
                        payload["session_id"] = metrics.session_id
                    await _send_json_safe(websocket, payload)
                    if not item.recoverable:
                        if metrics.ended_reason == "unknown":
                            metrics.ended_reason = "provider_error"
                        return
        except Exception as e:
            logger.error(
                "realtime forward_provider_events error: provider=%s type=%s detail=%s",
                provider, type(e).__name__, str(e)[:500],
            )
            metrics.error_count += 1
            if metrics.ended_reason == "unknown":
                metrics.ended_reason = "provider_error"
        finally:
            _done.set()

    async def enforce_session_timer():
        warning_at = settings.REALTIME_SESSION_WARNING_SECONDS
        max_at = settings.REALTIME_SESSION_MAX_SECONDS
        try:
            await asyncio.wait_for(_done.wait(), timeout=warning_at)
            return
        except asyncio.TimeoutError:
            pass
        if _done.is_set():
            return
        await _send_json_safe(websocket, {
            "type": "session.warning",
            "seconds_remaining": max_at - warning_at,
        })
        try:
            await asyncio.wait_for(_done.wait(), timeout=max_at - warning_at)
            return
        except asyncio.TimeoutError:
            pass
        if _done.is_set():
            return
        logger.info("[REALTIME_SESSION_TIMEOUT] session_id=%s provider=%s", session_id, provider)
        metrics.ended_reason = "timeout"
        await _send_json_safe(websocket, {"type": "session.ended", "reason": "timeout"})
        _done.set()
        await adapter.disconnect()

    try:
        await asyncio.gather(forward_client_audio(), forward_provider_events(), enforce_session_timer())
    finally:
        await adapter.disconnect()
        await _persist_realtime_metrics(metrics, capabilities)
        try:
            await websocket.close()
        except Exception:
            pass
