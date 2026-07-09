import asyncio
import io
import json
import logging
import re
from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional
from app.core.config import settings
from app.core.supabase import get_supabase, get_auth_client
from app.core.threading import run_sync
from app.core.rate_limit import SlidingWindowRateLimiter
from app.routers.auth import get_current_user, UserInfo
from app.routers.admin import require_admin
from app.services.speech_to_text import speech_to_text
from app.services.ai_scoring import get_patient_response, score_speaking, _call_ai
from app.services.pronunciation import get_pronunciation_feedback
from app.services.plan_gating import (
    get_scoring_model,
    get_plan_from_profile,
    get_scoring_criteria_count,
    has_pronunciation_access,
    get_tts_voice,
    is_premium_voice,
    PREMIUM_PLANS,
)
from app.services import tts_service
from app.services.cost_tracking import increment_session_cost
from app.services.realtime.pricing import estimate_tts_cost
from app.routers.sessions import check_and_increment_session, validate_session, is_first_ever_session
import websockets.exceptions as ws_exc

logger = logging.getLogger(__name__)


async def get_user_profile(supabase, user_id: str) -> dict:
    result = await run_sync(
        supabase.table("user_profiles").select(
            "plan, plan_expires_at, sessions_used_this_month"
        ).eq("user_id", user_id).execute
    )
    return result.data[0] if result.data else {}


def _redact_api_keys(text: str) -> str:
    return re.sub(r'(?i)(key|api[_-]?key|token|secret)(["\s:=]+)([A-Za-z0-9_-]{20,})', r'\1\2***REDACTED***', text)


def _classify_deepgram_error(status_code: int) -> str:
    if status_code in (401, 403):
        return "auth"
    elif status_code == 429:
        return "quota"
    elif status_code == 400:
        return "bad_request"
    elif status_code >= 500:
        return "server_error"
    return "unknown"

router = APIRouter(prefix="/speaking", tags=["speaking"])

MAX_TTS_TEXT_LENGTH = 1000

TTS_RATE_LIMIT_MAX_CALLS = 40
TTS_RATE_LIMIT_WINDOW_SECONDS = 600
_tts_rate_limiter = SlidingWindowRateLimiter(TTS_RATE_LIMIT_MAX_CALLS, TTS_RATE_LIMIT_WINDOW_SECONDS)

SCORE_RATE_LIMIT_MAX_CALLS = 20
SCORE_RATE_LIMIT_WINDOW_SECONDS = 600
_score_rate_limiter = SlidingWindowRateLimiter(SCORE_RATE_LIMIT_MAX_CALLS, SCORE_RATE_LIMIT_WINDOW_SECONDS)

TRANSCRIBE_RATE_LIMIT_MAX_CALLS = 40
TRANSCRIBE_RATE_LIMIT_WINDOW_SECONDS = 600
_transcribe_rate_limiter = SlidingWindowRateLimiter(TRANSCRIBE_RATE_LIMIT_MAX_CALLS, TRANSCRIBE_RATE_LIMIT_WINDOW_SECONDS)
MAX_TRANSCRIBE_AUDIO_BYTES = 10 * 1024 * 1024

PRONUNCIATION_RATE_LIMIT_MAX_CALLS = 20
PRONUNCIATION_RATE_LIMIT_WINDOW_SECONDS = 600
_pronunciation_rate_limiter = SlidingWindowRateLimiter(PRONUNCIATION_RATE_LIMIT_MAX_CALLS, PRONUNCIATION_RATE_LIMIT_WINDOW_SECONDS)
MAX_PRONUNCIATION_AUDIO_BYTES = 25 * 1024 * 1024

MAX_CHAT_HISTORY_MESSAGES = 60
MAX_CHAT_MESSAGE_LENGTH = 2000


@router.post("/tts")
async def text_to_speech(
    payload: dict = Body(...),
    current_user: UserInfo = Depends(get_current_user),
):
    text = payload.get("text", "")
    if not text:
        return JSONResponse({"fallback": True, "reason": "no_text"})

    if len(text) > MAX_TTS_TEXT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Text exceeds maximum length of {MAX_TTS_TEXT_LENGTH} characters",
        )

    session_id = payload.get("session_id")
    if not session_id or not await run_sync(validate_session, current_user.id, session_id):
        raise HTTPException(
            status_code=400,
            detail="Missing or invalid session — start a speaking session before requesting audio.",
        )

    if _tts_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many audio requests — please slow down.")

    supabase = get_supabase()
    profile = await get_user_profile(supabase, current_user.id)
    plan = get_plan_from_profile(profile)

    is_premium_trial = plan == "free" and await run_sync(is_first_ever_session, current_user.id, "speaking")

    gender = payload.get("gender")
    voice_name = payload.get("voice_name", "")
    if is_premium_trial:
        voice_name = get_tts_voice("pro", gender)
    elif plan in PREMIUM_PLANS and not is_premium_voice(voice_name):
        # Scenario voice_config defaults to WaveNet regardless of plan (see
        # tts_service.get_default_voice_config) -- Pro/Elite need to be
        # upgraded to Chirp3-HD here since nothing upstream requests it.
        voice_name = get_tts_voice(plan, gender)
    elif is_premium_voice(voice_name) and plan not in PREMIUM_PLANS:
        voice_name = get_tts_voice(plan, gender)
    speaking_rate = payload.get("speaking_rate", 0.95)
    pitch = payload.get("pitch", 0.0)
    language_code = payload.get("language_code", "en-GB")

    try:
        audio_bytes = await tts_service.synthesize_speech(
            text=text,
            voice_name=voice_name,
            speaking_rate=speaking_rate,
            pitch=pitch,
            language_code=language_code,
            plan=plan,
        )
        await increment_session_cost(
            session_id,
            tts_cost_usd=estimate_tts_cost(len(text), is_premium_voice(voice_name)),
        )
        return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/mpeg")
    except Exception as e:
        err_str = str(e)
        reason = "no_key" if "no_key" in err_str else "api_error"
        logger.error(
            "[EXTERNAL_API_FAILURE] service=GOOGLE_TTS type=%s detail=%s",
            reason, _redact_api_keys(err_str[:500]),
        )
        return JSONResponse({"fallback": True, "reason": reason})


STT_AUTH_TIMEOUT_SECONDS = 10
# Safely under Deepgram's ~10-12s no-data connection timeout.
DEEPGRAM_KEEPALIVE_INTERVAL_SECONDS = 5


@router.websocket("/stt/stream")
async def stt_deepgram_stream(websocket: WebSocket):
    """
    WebSocket proxy: frontend first sends {"token": "<supabase access token>"},
    then audio chunks -> backend forwards audio to Deepgram Nova-3 -> Deepgram
    returns transcripts -> backend forwards to frontend.
    Audio format: audio/webm (from browser MediaRecorder).
    """
    await websocket.accept()

    token = None
    try:
        auth_message = await asyncio.wait_for(
            websocket.receive_json(), timeout=STT_AUTH_TIMEOUT_SECONDS
        )
        if isinstance(auth_message, dict):
            token = auth_message.get("token")
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError, KeyError):
        token = None

    user = None
    if token:
        try:
            auth_result = await run_sync(get_auth_client().auth.get_user, token)
            user = auth_result.user
        except Exception as e:
            logger.warning("STT stream auth failed: %s", _redact_api_keys(str(e)[:200]))
            user = None

    if not user:
        try:
            await websocket.send_json({"error": "Unauthorized", "is_final": True})
        except (RuntimeError, ws_exc.ConnectionClosed):
            pass
        await websocket.close(code=4401, reason="Unauthorized")
        return

    logger.info("STT stream authenticated | user_id=%s", user.id)

    if not settings.DEEPGRAM_API_KEY:
        await websocket.send_json({"error": "DEEPGRAM_API_KEY not configured", "is_final": True})
        await websocket.close()
        return

    deepgram_url = (
        f"wss://api.deepgram.com/v1/listen"
        # nova-3 is English-only and defaults to a US-accent acoustic model;
        # nova-2 has a dedicated en-IN locale, which is what our nursing
        # students actually speak -- switching both together, since en-IN
        # isn't a supported language option under nova-3.
        f"?model=nova-2"
        f"&language=en-IN"
        f"&interim_results=true"
        f"&endpointing=1500"
        f"&utterance_end_ms=1500"
        f"&smart_format=true"
        f"&encoding=opus"
        f"&container=webm"
    )

    safe_url = re.sub(r'(Token\s+)[A-Za-z0-9_\-]{20,}', r'\1***REDACTED***', deepgram_url)
    logger.info("Connecting to Deepgram: %s", safe_url)

    try:
        import websockets as ws_lib
        try:
            dg_ws = await ws_lib.connect(
                deepgram_url,
                extra_headers={"Authorization": f"Token {settings.DEEPGRAM_API_KEY}"},
                close_timeout=1,
                open_timeout=30,
            )
        except ws_exc.InvalidStatus as e:
            resp = e.response
            status = resp.status_code
            body_text = resp.body.decode('utf-8', errors='replace')[:500] if resp.body else ""
            logger.error(
                "[DEEPGRAM_CONNECT_FAIL] type=InvalidStatus status=%s body=%s",
                status, _redact_api_keys(body_text),
            )
            raise
        except ws_exc.InvalidStatusCode as e:
            dg_error = e.headers.get("dg-error", "N/A") if hasattr(e, 'headers') else "N/A"
            logger.error(
                "[DEEPGRAM_CONNECT_FAIL] type=InvalidStatusCode status=%s dg_error=%s",
                e.status_code, dg_error,
            )
            raise
        except ws_exc.WebSocketException as e:
            if isinstance(e, ws_exc.ConnectionClosed):
                logger.error(
                    "[DEEPGRAM_CONNECT_FAIL] type=ConnectionClosed code=%s reason=%s",
                    e.code, e.reason,
                )
            else:
                logger.error(
                    "[DEEPGRAM_CONNECT_FAIL] type=%s detail=%s",
                    type(e).__name__, _redact_api_keys(str(e)[:500]),
                )
            raise
        except asyncio.TimeoutError:
            logger.error("[DEEPGRAM_CONNECT_FAIL] type=TimeoutError open_timeout=30s")
            raise
        except Exception as e:
            logger.error(
                "[DEEPGRAM_CONNECT_FAIL] type=%s detail=%s",
                type(e).__name__, _redact_api_keys(str(e)[:500]),
            )
            raise

        if dg_ws.close_code is not None:
            logger.warning(
                "[DEEPGRAM_CLOSED_IMMEDIATELY] code=%s reason=%s state=%s",
                dg_ws.close_code, dg_ws.close_reason, dg_ws.state,
            )

        try:
            _done = asyncio.Event()

            async def forward_audio():
                try:
                    done_task = asyncio.create_task(_done.wait())
                    while not _done.is_set():
                        recv_task = asyncio.create_task(websocket.receive_bytes())
                        finished, pending = await asyncio.wait(
                            {recv_task, done_task},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if recv_task in finished:
                            try:
                                data = recv_task.result()
                            except WebSocketDisconnect:
                                _done.set()
                                logger.info("Client WebSocket disconnected — stopping audio forward")
                                return
                            try:
                                await dg_ws.send(data)
                            except ws_exc.ConnectionClosed:
                                _done.set()
                                logger.info("Deepgram connection closed — stopping audio forward")
                                return
                        else:
                            recv_task.cancel()
                            try:
                                await recv_task
                            except asyncio.CancelledError:
                                pass
                            break
                except WebSocketDisconnect:
                    _done.set()
                    logger.info("Client WebSocket disconnected — stopping audio forward")
                except Exception as e:
                    _done.set()
                    logger.warning("forward_audio error: %s", str(e)[:200])

            async def forward_transcripts():
                try:
                    async for message in dg_ws:
                        if _done.is_set():
                            break
                        if isinstance(message, bytes):
                            continue
                        parsed = json.loads(message)
                        if not isinstance(parsed, dict):
                            logger.error(
                                "forward_transcripts non-dict type=%s data=%s",
                                type(parsed).__name__, str(parsed)[:500],
                            )
                            continue
                        msg_type = parsed.get("type", "unknown")

                        if msg_type in ("Error", "Warning"):
                            logger.warning("Deepgram %s: %s", msg_type, json.dumps(parsed)[:500])
                            continue

                        if msg_type == "Results":
                            channel = parsed.get("channel", {})
                            if not isinstance(channel, dict):
                                logger.error(
                                    "forward_transcripts channel not dict type=%s msg_type=%s channel=%s",
                                    type(channel).__name__, msg_type, str(channel)[:500],
                                )
                                transcript_data = ""
                            else:
                                alternatives = channel.get("alternatives", [])
                                if not alternatives:
                                    transcript_data = ""
                                else:
                                    transcript_data = alternatives[0].get("transcript", "")
                            try:
                                await websocket.send_json({
                                    "type": "Results",
                                    "transcript": transcript_data,
                                    "is_final": parsed.get("is_final", False),
                                    "speech_final": parsed.get("speech_final", False),
                                })
                            except (RuntimeError, ws_exc.ConnectionClosed):
                                _done.set()
                                logger.debug("Client connection closed while forwarding Results")
                                return
                        elif msg_type == "UtteranceEnd":
                            logger.info("Deepgram UtteranceEnd received — forwarding to client")
                            try:
                                await websocket.send_json({
                                    "type": msg_type,
                                    "transcript": "",
                                    "is_final": False,
                                    "speech_final": False,
                                })
                            except (RuntimeError, ws_exc.ConnectionClosed):
                                _done.set()
                                logger.debug("Client connection closed while forwarding UtteranceEnd")
                                return
                except ws_exc.ConnectionClosed as e:
                    _done.set()
                    logger.warning(
                        "Deepgram connection closed: code=%s reason=%s",
                        e.code, e.reason,
                    )
                except Exception as e:
                    _done.set()
                    logger.error(
                        "forward_transcripts error: type=%s detail=%s",
                        type(e).__name__, str(e)[:500],
                    )

            async def keepalive():
                # Deepgram closes the socket if it goes ~10-12s without
                # receiving any message (audio or otherwise) -- MediaRecorder
                # chunks cover that while the mic is actively capturing, but
                # nothing sends anything during a long LLM/TTS think-time
                # between turns. A periodic KeepAlive message is Deepgram's
                # documented way to hold the connection open through that gap
                # without it being mistaken for an abandoned session.
                try:
                    while not _done.is_set():
                        try:
                            await asyncio.wait_for(_done.wait(), timeout=DEEPGRAM_KEEPALIVE_INTERVAL_SECONDS)
                        except asyncio.TimeoutError:
                            pass
                        if _done.is_set():
                            break
                        try:
                            await dg_ws.send(json.dumps({"type": "KeepAlive"}))
                        except ws_exc.ConnectionClosed:
                            _done.set()
                            return
                except Exception as e:
                    logger.warning("Deepgram keepalive error: %s", str(e)[:200])

            await asyncio.gather(forward_audio(), forward_transcripts(), keepalive())
        finally:
            try:
                await dg_ws.close()
            except Exception:
                pass

    except ws_exc.InvalidStatus as e:
        resp = e.response
        status = resp.status_code
        body_text = ""
        if resp.body:
            body_text = resp.body.decode('utf-8', errors='replace')[:500]
        error_type = _classify_deepgram_error(status)
        detail = _redact_api_keys(f"HTTP {status}: {body_text}")
        logger.error(
            "[EXTERNAL_API_FAILURE] service=DEEPGRAM type=%s status=%d detail=%s",
            error_type, status, detail,
        )
        try:
            await websocket.send_json({"error": f"Deepgram connection failed (HTTP {status})", "is_final": True})
        except Exception:
            pass

    except ws_exc.InvalidStatusCode as e:
        status = e.status_code
        error_type = _classify_deepgram_error(status)
        dg_error = e.headers.get("dg-error", "no dg-error header present") if hasattr(e, 'headers') else "N/A"
        logger.error(
            "[EXTERNAL_API_FAILURE] service=DEEPGRAM type=%s status=%s dg_error=%s",
            error_type, status, dg_error,
        )
        try:
            await websocket.send_json({"error": f"Deepgram connection failed (HTTP {status})", "is_final": True})
        except Exception:
            pass

    except ws_exc.WebSocketException as e:
        if isinstance(e, ws_exc.ConnectionClosed):
            error_type = "connection_closed"
            close_info = f"code={e.code} reason={e.reason}"
            logger.error(
                "[EXTERNAL_API_FAILURE] service=DEEPGRAM type=%s detail=%s",
                error_type, close_info,
            )
        else:
            error_type = "network"
            logger.error(
                "[EXTERNAL_API_FAILURE] service=DEEPGRAM type=%s detail=%s",
                error_type, _redact_api_keys(str(e)[:500]),
            )
        try:
            await websocket.send_json({"error": f"Deepgram connection error: {type(e).__name__}", "is_final": True})
        except Exception:
            pass

    except Exception as e:
        error_msg = str(e)[:500] or repr(e)[:500]
        resp = getattr(e, 'response', None)
        if resp is not None:
            body = getattr(resp, 'body', None)
            if isinstance(body, bytes):
                body_text = body.decode('utf-8', errors='replace')[:500]
            else:
                body_text = str(body or '')[:500]
            status = getattr(resp, 'status_code', '?')
            error_type = _classify_deepgram_error(status) if isinstance(status, int) else "unknown"
            detail = _redact_api_keys(f"HTTP {status}: {body_text}")
        else:
            error_type = "unknown"
            detail = _redact_api_keys(error_msg)
        logger.error(
            "[EXTERNAL_API_FAILURE] service=DEEPGRAM type=%s detail=%s",
            error_type, detail,
        )
        try:
            await websocket.send_json({"error": error_msg, "is_final": True})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    current_user: UserInfo = Depends(get_current_user),
):
    if _transcribe_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many transcription requests — please slow down.")

    audio_data = await audio.read()
    if len(audio_data) > MAX_TRANSCRIBE_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Audio file too large")

    result = await speech_to_text.transcribe_audio(audio_data, audio.filename or "audio.wav")
    return result


class ChatMessage(BaseModel):
    role: str  # "nurse" or "patient"
    content: str


class PatientChatRequest(BaseModel):
    scenario_id: int
    message: str
    history: List[ChatMessage] = Field(default_factory=list)
    session_id: Optional[int] = None


class PatientChatResponse(BaseModel):
    patient_reply: str
    updated_history: List[ChatMessage]
    session_id: Optional[int] = None


class SpeakingSubmitRequest(BaseModel):
    scenario_id: int
    history: List[ChatMessage]
    audio_base64: Optional[str] = None
    duration_seconds: Optional[int] = None
    session_id: Optional[int] = None


@router.get("/scenarios")
def list_scenarios(current_user: UserInfo = Depends(get_current_user)):
    """List all active speaking scenarios."""
    supabase = get_supabase()
    data = supabase.table("scenarios").select(
        "id, title, setting, difficulty, nurse_card, specialty, voice_config, patient_gender, patient_age"
    ).eq("module", "speaking").eq("is_active", True).execute()
    for scenario in data.data:
        if not scenario.get("voice_config"):
            scenario["voice_config"] = tts_service.get_default_voice_config(
                gender=scenario.get("patient_gender"),
                age=scenario.get("patient_age"),
            )
    return data.data


def _recommend_scenarios(current_user: UserInfo, limit: int) -> list:
    """Shared ranking used by both /scenarios/recommend (single) and
    /scenarios/recommendations (row): unattempted scenarios first (shuffled,
    so repeat visits don't always see the same one), then the user's
    lowest-scored attempted scenarios, weakest first."""
    import random

    supabase = get_supabase()

    all_scenarios = supabase.table("scenarios").select(
        "id, title, setting, difficulty, nurse_card"
    ).eq("module", "speaking").eq("is_active", True).execute()
    if not all_scenarios.data:
        raise HTTPException(status_code=404, detail="No scenarios available")

    attempted_ids = supabase.table("submissions").select(
        "scenario_id"
    ).eq("user_id", current_user.id).eq("module", "speaking").execute()
    attempted_set = {s["scenario_id"] for s in attempted_ids.data if s.get("scenario_id")}

    unattempted = [s for s in all_scenarios.data if s["id"] not in attempted_set]
    random.shuffle(unattempted)

    feedback_data = supabase.table("submissions").select(
        "scenario_id, score"
    ).eq("user_id", current_user.id).eq("module", "speaking").execute()
    avg_scores = {}
    for s in feedback_data.data:
        qid = s.get("scenario_id")
        if qid:
            avg_scores.setdefault(qid, []).append(s.get("score", 0))
    weakest_first = sorted(avg_scores.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
    scenarios_by_id = {s["id"]: s for s in all_scenarios.data}

    recs = []
    seen_ids = set()

    for s in unattempted:
        if len(recs) >= limit:
            break
        recs.append({
            "scenario_id": s["id"],
            "title": s["title"],
            "setting": s["setting"],
            "difficulty": s["difficulty"],
            "reason": "New - you haven't tried this scenario yet",
        })
        seen_ids.add(s["id"])

    for qid, scores in weakest_first:
        if len(recs) >= limit:
            break
        if qid in seen_ids:
            continue
        pick = scenarios_by_id.get(qid)
        if not pick:
            continue
        avg = sum(scores) / len(scores)
        recs.append({
            "scenario_id": pick["id"],
            "title": pick["title"],
            "setting": pick["setting"],
            "difficulty": pick["difficulty"],
            "reason": f"Needs practice - your average score for this scenario is {avg:.1f}/6",
        })
        seen_ids.add(qid)

    if not recs:
        for s in random.sample(all_scenarios.data, min(limit, len(all_scenarios.data))):
            recs.append({
                "scenario_id": s["id"],
                "title": s["title"],
                "setting": s["setting"],
                "difficulty": s["difficulty"],
                "reason": "Try this scenario",
            })

    return recs


@router.get("/scenarios/recommend")
def recommend_scenario(current_user: UserInfo = Depends(get_current_user)):
    """Recommend a single scenario \u2014 used by the dashboard's recommended-case card."""
    return _recommend_scenarios(current_user, limit=1)[0]


@router.get("/scenarios/recommendations")
def recommend_scenarios(limit: int = 3, current_user: UserInfo = Depends(get_current_user)):
    """Recommend up to `limit` scenarios \u2014 used by the picker's recommended row."""
    return _recommend_scenarios(current_user, limit=limit)


@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: int, current_user: UserInfo = Depends(get_current_user)):
    """Get a single scenario with nurse card (interlocutor card and scoring rubric NOT sent to student)."""
    supabase = get_supabase()
    data = supabase.table("scenarios").select(
        "id, title, setting, difficulty, nurse_card, voice_config, patient_gender, patient_age"
    ).eq("id", scenario_id).eq("is_active", True).execute()
    if not data.data:
        raise HTTPException(status_code=404, detail="Scenario not found")
    scenario = data.data[0]
    if not scenario.get("voice_config"):
        scenario["voice_config"] = tts_service.get_default_voice_config(
            gender=scenario.get("patient_gender"),
            age=scenario.get("patient_age"),
        )
    return scenario


@router.post("/chat")
async def chat_with_patient(
    request: PatientChatRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """
    Multi-turn conversation with AI patient.
    Student sends a message -> AI responds as the patient (following interlocutor card).
    A session is only ever charged once: the client must present the session_id
    issued by check_and_increment_session for every turn after the first. A
    missing or unrecognized session_id (whether forged or genuinely absent)
    always triggers a fresh quota check — the client's self-reported `history`
    is never trusted for billing purposes.
    """
    session_id = request.session_id
    if session_id is not None and not await run_sync(validate_session, current_user.id, session_id):
        session_id = None
    if session_id is None:
        usage = await run_sync(check_and_increment_session, current_user)
        session_id = usage["session_id"]

    supabase = get_supabase()

    # Get scenario with interlocutor card
    scenario_data = await run_sync(
        supabase.table("scenarios").select("*")
        .eq("id", request.scenario_id).eq("is_active", True).execute
    )

    if not scenario_data.data:
        raise HTTPException(status_code=404, detail="Scenario not found")

    scenario = scenario_data.data[0]
    interlocutor_card = scenario.get("interlocutor_card", {})

    # Build conversation history
    history = [{"role": msg.role, "content": msg.content} for msg in request.history]

    # Get AI patient response
    patient_reply = await get_patient_response(
        interlocutor_card=interlocutor_card,
        conversation_history=history,
        nurse_message=request.message,
        supabase=supabase,
    )

    # Update history
    updated_history = request.history + [
        ChatMessage(role="nurse", content=request.message),
        ChatMessage(role="patient", content=patient_reply),
    ]

    return PatientChatResponse(
        patient_reply=patient_reply,
        updated_history=updated_history,
        session_id=session_id,
    )


@router.post("/score")
async def score_speaking_session(
    request: SpeakingSubmitRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """
    Score a completed speaking session.
    Uses nurse card tasks as scoring criteria.
    """
    if not request.session_id or not await run_sync(validate_session, current_user.id, request.session_id):
        raise HTTPException(
            status_code=400,
            detail="Missing or invalid session — start a new conversation before scoring.",
        )

    if _score_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many scoring requests — please slow down.")

    supabase = get_supabase()

    # Get user plan for model selection
    profile = await get_user_profile(supabase, current_user.id)
    plan = get_plan_from_profile(profile)

    is_premium_trial = plan == "free" and await run_sync(is_first_ever_session, current_user.id, "speaking")
    effective_plan = "pro" if is_premium_trial else plan
    scoring_model = get_scoring_model(effective_plan)

    # Get scenario
    scenario_data = await run_sync(
        supabase.table("scenarios").select("id, title, nurse_card, scoring_criteria")
        .eq("id", request.scenario_id).execute
    )

    if not scenario_data.data:
        raise HTTPException(status_code=404, detail="Scenario not found")

    scenario = scenario_data.data[0]
    nurse_card = scenario.get("nurse_card", {})

    # Build conversation history
    history = [{"role": msg.role, "content": msg.content} for msg in request.history]

    # Score with plan-appropriate model and criteria count
    criteria_count = get_scoring_criteria_count(effective_plan)
    feedback = await score_speaking(
        nurse_card=nurse_card,
        conversation_history=history,
        scenario_title=scenario.get("title", ""),
        supabase=supabase,
        model=scoring_model,
        criteria_count=criteria_count,
        enhanced_feedback=effective_plan in PREMIUM_PLANS,
    )

    if feedback.get("provider_failure"):
        # The AI service itself was unreachable -- don't persist a fake 0/6
        # or let the client mistake this for a real score. The session was
        # already charged when the conversation started; the client can
        # retry scoring without redoing the conversation.
        raise HTTPException(
            status_code=503,
            detail="Scoring is temporarily unavailable. Please try again in a few minutes.",
        )

    # Save submission
    transcript = "\n".join([
        f"{'Nurse' if m.role == 'nurse' else 'Patient'}: {m.content}"
        for m in request.history
    ])

    await run_sync(
        supabase.table("submissions").insert({
            "user_id": current_user.id,
            "scenario_id": request.scenario_id,
            "module": "speaking",
            "answer": transcript,
            "score": feedback.get("overall_band", 0),
            "feedback": json.dumps(feedback),
            "duration_seconds": request.duration_seconds,
        }).execute
    )

    return {
        "success": True,
        "feedback": feedback,
        "is_premium_trial": is_premium_trial,
        "plan": plan,
        "criteria_count": criteria_count,
    }


@router.post("/pronunciation")
async def assess_pronunciation(
    audio: UploadFile = File(...),
    nurse_transcript: str = Form(...),
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Assess pronunciation from audio recording.
    Called after session ends alongside /score.
    """
    supabase = get_supabase()
    profile = await get_user_profile(supabase, current_user.id)
    plan = get_plan_from_profile(profile)

    try:
        audio_data = await audio.read()
        audio_format = "webm"

        # Determine format from content type
        if audio.content_type:
            if "ogg" in audio.content_type:
                audio_format = "ogg"
            elif "mp4" in audio.content_type:
                audio_format = "mp4"
            elif "wav" in audio.content_type:
                audio_format = "wav"

        if has_pronunciation_access(plan):
            # Elite — full Azure phoneme-level assessment
            result = await get_pronunciation_feedback(
                audio_data=audio_data,
                nurse_transcript=nurse_transcript,
                audio_format=audio_format
            )
        else:
            # Free/Basic/Pro — pattern analysis only, no Azure
            from app.services.pronunciation import analyze_indian_patterns
            pattern_findings = analyze_indian_patterns(nurse_transcript)
            result = {
                "method": "pattern_analysis",
                "azure": None,
                "pattern_analysis": pattern_findings,
                "has_azure": False,
            }

        return {
            "success": True,
            "pronunciation": result,
            "plan_limited": not has_pronunciation_access(plan),
            "upgrade_required": not has_pronunciation_access(plan),
        }

    except Exception as e:
        logger.error("[PRONUNCIATION_FAILURE] /speaking/pronunciation failed: %s", str(e))
        return {
            "success": False,
            "error": "Pronunciation analysis is currently unavailable.",
            "pronunciation": {
                "method": "error",
                "pattern_analysis": [],
                "has_azure": False
            }
        }


@router.post("/scenarios/generate")
async def generate_scenario(
    payload: dict,
    _admin: UserInfo = Depends(require_admin),
):
    """Admin-only: generate a new OET scenario (includes examiner-only interlocutor card)."""
    from app.services.ai_scoring import _call_ai
    import json
    
    specialty = payload.get("specialty", "general")
    difficulty = payload.get("difficulty", "intermediate")
    setting = payload.get("setting", "")
    
    prompt = f"""You are an OET exam content creator. Generate a realistic OET Speaking roleplay card for a nursing student.

REQUIREMENTS:
- Specialty: {specialty}
- Difficulty: {difficulty}
{f'- Setting: {setting}' if setting else ''}
- Must be clinically realistic
- Tasks must follow real OET format (5-6 specific tasks)
- Patient must have a clear emotional state and believable background

Return ONLY this JSON, no other text:
{{
  "title": "short scenario title",
  "setting": "ward/clinic description and patient context paragraph",
  "difficulty": "{difficulty}",
  "nurse_card": {{
    "role": "You are the nurse. Describe the situation briefly.",
    "tasks": [
      "Task 1",
      "Task 2", 
      "Task 3",
      "Task 4",
      "Task 5"
    ]
  }},
  "interlocutor_card": {{
    "patient_name": "First name only",
    "age": 35,
    "condition": "presenting condition",
    "mood": "anxious|worried|confused|resistant|cooperative",
    "background": "2 sentence patient background",
    "emotional_triggers": ["trigger 1", "trigger 2"],
    "questions_to_ask": ["question 1", "question 2", "question 3"],
    "information_to_withhold": ["info to withhold 1", "info to withhold 2"],
    "instructions_for_ai": "detailed persona description"
  }}
}}"""

    result = await _call_ai(
        [{"role": "user", "content": prompt}],
        max_tokens=1500,
        json_mode=True,
        provider="openrouter",
        model="google/gemini-3.5-flash",
    )
    
    if "nurse_card" not in result:
        raise HTTPException(status_code=502, detail="Failed to generate scenario")
    
    return result
