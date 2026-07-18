"""Kill switches for user-facing features -- toggled from the admin panel,
no redeploy needed. Reuses the same `settings` table + fresh-read-per-request
pattern already used for voice_provider/ai_model (see speaking_realtime.py's
_get_voice_provider)."""
from fastapi import HTTPException, WebSocket
from app.core.supabase import get_supabase

# key -> human label shown in the admin panel. Add an entry here to make a
# feature killable; the DB row only needs to exist when someone flips it off.
FEATURE_FLAGS = {
    "speaking_practice": "Speaking practice (TTS/STT, chat, scoring, pronunciation)",
    "voice_realtime": "Real-time voice-to-voice mode",
    "writing_practice": "Writing practice (submission + AI scoring)",
    "grammar_checker": "Grammar checker tool",
}


def is_feature_enabled(key: str) -> bool:
    try:
        data = get_supabase().table("settings").select("value").eq("key", f"feature_{key}_enabled").execute()
        if data.data:
            return data.data[0]["value"] != "false"
    except Exception:
        pass
    return True  # missing row = on, matches every other settings-table default in this codebase


def require_feature(key: str):
    """FastAPI dependency: gate an HTTP router/endpoint behind a kill switch."""
    def _dep():
        if not is_feature_enabled(key):
            raise HTTPException(status_code=503, detail="This feature is temporarily disabled. Please try again later.")
    return _dep


async def close_if_disabled(websocket: WebSocket, key: str) -> bool:
    """Same kill switch for a websocket route, which can't raise HTTPException.
    Call right after websocket.accept(); returns True if the caller should stop."""
    if is_feature_enabled(key):
        return False
    await websocket.close(code=4503, reason="Feature disabled")
    return True
