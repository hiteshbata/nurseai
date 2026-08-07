import httpx
import logging
from typing import Optional
from app.core.config import settings
from app.core.error_utils import redact_api_keys, classify_http_error
from app.core.ai_pricing import estimate_deepgram_cost
from app.core import cost_circuit_breaker
from app.services import ai_registry
from app.services.cost_tracking import log_ai_usage

logger = logging.getLogger(__name__)


class SpeechToText:
    async def transcribe_audio(
        self,
        audio_data: bytes,
        filename: str = "audio.webm",
        user_id: Optional[str] = None,
    ) -> dict:
        if not settings.DEEPGRAM_API_KEY:
            return {"text": "", "provider": "none", "error": "DEEPGRAM_API_KEY not configured"}

        cost_circuit_breaker.raise_if_tripped()
        deepgram_model = (await ai_registry.get_model_config("stt_deepgram_rest")).model_name

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
                        "model": deepgram_model,
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
                    duration = result.get("metadata", {}).get("duration")
                    if duration is not None:
                        await log_ai_usage(
                            "stt", "deepgram", estimate_deepgram_cost(deepgram_model, duration),
                            user_id=user_id, model=deepgram_model, purpose="stt_deepgram_rest",
                            detail={"audio_seconds": duration},
                        )
                    return {"text": transcript, "provider": "deepgram"}
                status = response.status_code
                error_type = classify_http_error(status)
                detail = redact_api_keys(response.text[:500])
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
                redact_api_keys(str(e)[:500]),
            )
            return {"text": "", "provider": "deepgram", "error": str(e)}

    async def close(self):
        pass

speech_to_text = SpeechToText()
