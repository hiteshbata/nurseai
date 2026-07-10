from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env"), extra="ignore"
    )

    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_ANON_KEY: str = ""
    # Project Settings -> API -> JWT Secret in the Supabase dashboard. Used to
    # verify access-token signatures locally (see app/routers/auth.py
    # get_current_user) instead of round-tripping to Supabase Auth on every
    # request.
    SUPABASE_JWT_SECRET: str = ""
    # Shared Redis instance for the rate limiter and role cache (see
    # app/core/rate_limit.py, app/routers/auth.py). Required once the app
    # runs as more than one instance/worker -- an unset value falls back to
    # a per-process dict, which is fine for local dev but wrong for any
    # deployment with >1 process, since limits/cache stop being shared.
    REDIS_URL: str = ""
    OPENROUTER_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_REALTIME_MODEL: str = "gpt-realtime"
    GEMINI_API_KEY: str = ""
    AI_PROVIDER: str = "gemini"

    # --- Realtime voice provider (OET Speaking live roleplay) ---
    # "openai" or "gemini". This is the ONLY line that should need to
    # change to switch which upstream realtime provider the
    # /speaking/realtime/stream websocket talks to -- see
    # app/services/realtime/factory.py.
    VOICE_PROVIDER: str = "openai"
    # Verify the current live-capable model name in Google AI Studio before
    # changing this -- the Gemini Live model catalog moves fast. See
    # app/services/realtime/gemini_adapter.py module docstring.
    GEMINI_LIVE_MODEL: str = "models/gemini-2.0-flash-live-001"
    # Backend-enforced hard cap on a single realtime voice session, plus a
    # heads-up sent to the client before the cutoff. Enforced by the
    # router (app/routers/speaking_realtime.py), not by either provider.
    REALTIME_SESSION_MAX_SECONDS: int = 300
    REALTIME_SESSION_WARNING_SECONDS: int = 270

    # Hard cap on how long a text-chat session_id (check_and_increment_session)
    # stays valid, enforced in app/routers/sessions.py validate_session. Without
    # this, a free user's first ("premium trial") session -- which gets the
    # paid-tier scoring model and TTS voice for as long as it's their first
    # session -- could be held open indefinitely and re-hit /chat and /tts to
    # run up premium-tier cost for free.
    CHAT_SESSION_MAX_SECONDS: int = 1800

    # --- Realtime cost estimation (see app/services/realtime/pricing.py) ---
    # Blended $/minute-of-conversation estimates, NOT exact -- both
    # providers bill per audio token/second with input and output priced
    # differently, and rates change. These exist so /admin cost dashboards
    # and the side-by-side provider comparison have *some* number to show;
    # verify against the OpenAI and Gemini billing consoles periodically
    # and override here (or via env) when they drift.
    OPENAI_REALTIME_USD_PER_MIN_INPUT: float = 0.0024
    OPENAI_REALTIME_USD_PER_MIN_OUTPUT: float = 0.0192
    GEMINI_LIVE_USD_PER_MIN_INPUT: float = 0.015
    GEMINI_LIVE_USD_PER_MIN_OUTPUT: float = 0.022
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    RAZORPAY_PLAN_ID_BASIC: str = ""
    RAZORPAY_PLAN_ID_PRO: str = ""
    RAZORPAY_PLAN_ID_ELITE: str = ""
    DEEPGRAM_API_KEY: str = ""
    GOOGLE_TTS_API_KEY: str = ""
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000"
    AZURE_SPEECH_KEY: str = ""
    AZURE_SPEECH_REGION: str = "southeastasia"
    POSTHOG_API_KEY: str = ""
    POSTHOG_HOST: str = "https://us.i.posthog.com"
    # Backend error tracking (app/main.py). Unset -> Sentry init is skipped
    # entirely, no-op. Get a DSN from sentry.io -> Project Settings -> Client Keys.
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = "production"

settings = Settings()
