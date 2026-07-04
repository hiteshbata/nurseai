import base64
import httpx
import logging
import re
from app.core.config import settings
from app.services.plan_gating import get_tts_voice

logger = logging.getLogger(__name__)

GOOGLE_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"


def _redact_api_keys(text: str) -> str:
    return re.sub(r'(?i)(key|api[_-]?key|token|secret)(["\s:=]+)([A-Za-z0-9_-]{20,})', r'\1\2***REDACTED***', text)


def _classify_tts_error(status_code: int) -> str:
    if status_code in (401, 403):
        return "auth"
    elif status_code == 429:
        return "quota"
    elif status_code == 400:
        return "bad_request"
    elif status_code == 404:
        return "bad_request"
    elif status_code >= 500:
        return "server_error"
    return "unknown"


async def synthesize_speech(
    text: str,
    voice_name: str = "",
    speaking_rate: float = 0.95,
    pitch: float = 0.0,
    language_code: str = "en-GB",
    plan: str = "free",
) -> bytes:
    if not settings.GOOGLE_TTS_API_KEY:
        logger.error("[EXTERNAL_API_FAILURE] service=GOOGLE_TTS type=auth detail=no_key_configured")
        raise Exception("no_key")

    effective_voice = voice_name or get_tts_voice(plan)
    payload = {
        "input": {"text": text},
        "voice": {
            "languageCode": language_code,
            "name": effective_voice,
        },
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": speaking_rate,
            "pitch": pitch,
        },
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{GOOGLE_TTS_URL}?key={settings.GOOGLE_TTS_API_KEY}",
            json=payload,
        )

    if response.status_code != 200:
        status = response.status_code
        error_type = _classify_tts_error(status)
        detail = _redact_api_keys(response.text[:500])
        logger.error(
            "[EXTERNAL_API_FAILURE] service=GOOGLE_TTS type=%s status=%d detail=%s",
            error_type, status, detail,
        )
        raise Exception(f"api_error: {status} {detail}")

    data = response.json()
    audio_content = data.get("audioContent")
    if not audio_content:
        logger.error(
            "[EXTERNAL_API_FAILURE] service=GOOGLE_TTS type=bad_request detail=no_audioContent_in_response"
        )
        raise Exception("api_error: no audioContent in response")

    return base64.b64decode(audio_content)


def get_default_voice_config(gender: str | None, age: int | None = None) -> dict:
    if gender == "male":
        if age and age > 60:
            return {"voice_name": "en-GB-Wavenet-D", "speaking_rate": 0.80, "pitch": -3.0, "language_code": "en-GB"}
        return {"voice_name": "en-GB-Wavenet-B", "speaking_rate": 0.90, "pitch": -1.0, "language_code": "en-GB"}
    if gender == "female":
        if age and age > 60:
            return {"voice_name": "en-GB-Wavenet-C", "speaking_rate": 0.85, "pitch": -1.0, "language_code": "en-GB"}
        return {"voice_name": "en-GB-Wavenet-A", "speaking_rate": 0.95, "pitch": 0.0, "language_code": "en-GB"}
    return {"voice_name": "en-GB-Wavenet-A", "speaking_rate": 0.95, "pitch": 0.0, "language_code": "en-GB"}
