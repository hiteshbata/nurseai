import httpx
import logging
import re
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


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

class SpeechToText:
    async def transcribe_audio(self, audio_data: bytes, filename: str = "audio.webm") -> dict:
        if not settings.DEEPGRAM_API_KEY:
            return {"text": "", "provider": "none", "error": "DEEPGRAM_API_KEY not configured"}

        try:
            ext = filename.rsplit(".", 1)[-1] if "." in filename else "webm"
            mime_map = {"webm": "audio/webm", "wav": "audio/wav", "ogg": "audio/ogg", "mp3": "audio/mpeg", "mp4": "audio/mp4"}
            content_type = mime_map.get(ext, "audio/webm")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.deepgram.com/v1/listen",
                    headers={
                        "Authorization": f"Token {settings.DEEPGRAM_API_KEY}",
                        "Content-Type": content_type,
                    },
                    params={
                        "model": "nova-3",
                        "language": "en",
                        "smart_format": "true",
                        "punctuate": "true",
                    },
                    content=audio_data,
                )
                if response.status_code == 200:
                    result = response.json()
                    transcript = (
                        result.get("results", {})
                        .get("channels", [{}])[0]
                        .get("alternatives", [{}])[0]
                        .get("transcript", "")
                    )
                    return {"text": transcript, "provider": "deepgram"}
                status = response.status_code
                error_type = _classify_deepgram_error(status)
                detail = _redact_api_keys(response.text[:500])
                logger.error(
                    "[EXTERNAL_API_FAILURE] service=DEEPGRAM type=%s status=%d detail=%s",
                    error_type, status, detail,
                )
                return {"text": "", "provider": "deepgram", "error": f"Deepgram API error: {status}"}
        except httpx.TimeoutException as e:
            logger.error(
                "[EXTERNAL_API_FAILURE] service=DEEPGRAM type=network detail=timeout:%s",
                str(e)[:200],
            )
            return {"text": "", "provider": "deepgram", "error": "Deepgram request timed out"}
        except Exception as e:
            logger.error(
                "[EXTERNAL_API_FAILURE] service=DEEPGRAM type=unknown detail=%s",
                _redact_api_keys(str(e)[:500]),
            )
            return {"text": "", "provider": "deepgram", "error": str(e)}

    async def close(self):
        pass

speech_to_text = SpeechToText()
