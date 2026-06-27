import io
import json
from typing import Optional
from app.core.config import settings

class SpeechToText:
    async def transcribe_audio(self, audio_data: bytes, filename: str = "audio.wav") -> dict:
        if not settings.OPENAI_API_KEY:
            return {"text": "", "provider": "none", "error": "OPENAI_API_KEY not configured"}

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                files = {"file": (filename, audio_data, "audio/wav")}
                data = {"model": "whisper-1", "language": "en"}
                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    files=files,
                    data=data,
                )
                if response.status_code == 200:
                    result = response.json()
                    return {"text": result.get("text", ""), "provider": "whisper"}
                return {"text": "", "provider": "whisper", "error": f"Whisper API error: {response.status_code}"}
        except Exception as e:
            return {"text": "", "provider": "whisper", "error": str(e)}

speech_to_text = SpeechToText()
