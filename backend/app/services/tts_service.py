import base64
import httpx
import logging
import re
from app.core.config import settings
from app.core.error_utils import redact_api_keys, classify_http_error
from app.services.plan_gating import get_tts_voice

logger = logging.getLogger(__name__)

GOOGLE_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"


# The patient-persona LLM sometimes narrates non-verbal stage directions
# inline, e.g. "*starts to tear up* I just don't know what to do." These are
# written for the transcript, not meant to be read aloud -- without stripping
# them, Google TTS synthesizes the literal words "starts to tear up" audibly.
# Matches *...* spans up to 80 chars (no nested asterisk/newline) so a lone
# "*" used for emphasis or multiplication in normal text is left untouched.
_ACTION_TAG_RE = re.compile(r'\*[^*\n]{1,80}\*')


def strip_action_tags(text: str) -> str:
    cleaned = _ACTION_TAG_RE.sub('', text)
    return re.sub(r'[ \t]{2,}', ' ', cleaned).strip()


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

    text = strip_action_tags(text) or text
    effective_voice = voice_name or await get_tts_voice(plan)
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
        error_type = classify_http_error(status)
        detail = redact_api_keys(response.text[:500])
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
