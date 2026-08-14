import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# Which dotenv backs each ENVIRONMENT. Read from the real process env (never
# from a dotenv) since this decides *which* dotenv to load -- Render/Vercel
# set ENVIRONMENT as a real env var for QA/production; local dev falls back
# to "production" to match this repo's existing convention of backend/.env
# doubling as the local-dev config source. qa intentionally has its own
# entry so backend/.env.qa is the ONLY dotenv read for ENVIRONMENT=qa --
# backend/.env (which holds production secrets like GEMINI_API_KEY /
# TURNSTILE_SECRET_KEY) must never be consulted as a fallback, or a QA
# process would silently inherit production credentials it never asked for.
_ENV_FILENAMES = {"production": ".env", "qa": ".env.qa", "development": ".env"}


def _resolve_env_file(environment: str, backend_dir: Path = _BACKEND_DIR) -> Path:
    return backend_dir / _ENV_FILENAMES.get((environment or "").strip().lower(), ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_resolve_env_file(os.environ.get("ENVIRONMENT", "production"))), extra="ignore")

    # production | qa | development -- which backend deployment this is.
    # Distinct from SENTRY_ENVIRONMENT (development/rc1/production, a Sentry
    # tag only). Used by app.core.env_guard to fail startup closed if a
    # non-production environment is accidentally pointed at the production
    # Supabase project. Defaults to "production" so existing deployments
    # that don't set this var yet keep today's behavior.
    ENVIRONMENT: str = "production"
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_ANON_KEY: str = ""
    # Project ref (the "xxxxx" in https://xxxxx.supabase.co) of the
    # PRODUCTION Supabase project. Not secret on its own -- it's just an
    # id, not a credential -- but every environment's .env should set it so
    # app.core.env_guard can recognize "this is production" and refuse to
    # boot a qa/development environment against it. Leave unset to skip the
    # check (e.g. before QA is provisioned).
    PRODUCTION_SUPABASE_PROJECT_REF: str = ""
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
    # No longer read directly for the live realtime call (Admin > AI Models'
    # "realtime_voice_openai_standard"/"_mini" purposes control that --
    # see plan_gating.get_realtime_purpose) -- kept as the mini-tier
    # reference value for realtime/pricing.py's cost estimator.
    OPENAI_REALTIME_MODEL: str = "gpt-realtime"
    OPENAI_REALTIME_MODEL_MINI: str = "gpt-realtime-mini"
    GEMINI_API_KEY: str = ""
    AI_PROVIDER: str = "gemini"

    # --- Realtime voice provider (OET Speaking live roleplay) ---
    # "openai" or "gemini". This is the ONLY line that should need to
    # change to switch which upstream realtime provider the
    # /speaking/realtime/stream websocket talks to -- see
    # app/services/realtime/factory.py.
    VOICE_PROVIDER: str = "openai"
    # Backend-enforced hard cap on a single realtime voice session, plus a
    # heads-up sent to the client before the cutoff. Enforced by the
    # router (app/routers/speaking_realtime.py), not by either provider.
    REALTIME_SESSION_MAX_SECONDS: int = 300
    REALTIME_SESSION_WARNING_SECONDS: int = 270

    # Same idea, tighter cap for the scenario-less onboarding voice check
    # (see realtime_stream's is_warmup path) -- a single-question mic-check
    # (see _build_warmup_system_prompt) normally wraps up in well under a
    # minute on its own; this is a safety backstop, not the expected path,
    # so the warning is set close to the cap rather than deep into it.
    REALTIME_WARMUP_MAX_SECONDS: int = 45
    REALTIME_WARMUP_WARNING_SECONDS: int = 35
    # Deepgram STT proxy (app/routers/speaking.py stt_deepgram_stream) has no
    # natural end signal like the realtime voice pipeline does -- cap wall-
    # clock connection time so a client can't hold it open indefinitely.
    STT_STREAM_MAX_SECONDS: int = 600

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
    # Audio-token rates for gpt-realtime (flagship), uncached: $32/$64 per 1M
    # input/output audio tokens x 600/1200 tokens-per-minute (see
    # app/services/realtime/pricing.py docstring for the token-rate math).
    # Mini rates are gpt-realtime-mini's $10/$20 per 1M equivalent. Both
    # verify against https://developers.openai.com/api/docs/pricing --
    # these numbers move and this constant will go stale.
    OPENAI_REALTIME_USD_PER_MIN_INPUT: float = 0.0192
    OPENAI_REALTIME_USD_PER_MIN_OUTPUT: float = 0.0768
    OPENAI_REALTIME_USD_PER_MIN_INPUT_MINI: float = 0.006
    OPENAI_REALTIME_USD_PER_MIN_OUTPUT_MINI: float = 0.024
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
    # Shared secret for external cron services (cron-job.org, Render Cron Job)
    # to trigger /admin/logs/prune, /admin/subscriptions/sweep-expired, and
    # the reminder-email crons below without a human admin JWT. Sent as the
    # X-Cron-Secret header. Unset -> those endpoints stay admin-JWT-only.
    # See app/routers/admin.py.
    CRON_SECRET: str = ""
    # Transactional email (expiry/failed-payment reminders -- see
    # app/services/email.py). Unset -> send_email logs and no-ops, so the
    # reminder crons stay safe to run before an account exists.
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "SpeakOET <notifications@speakoet.com>"
    FRONTEND_URL: str = "https://www.speakoet.com"
    # Hard cap on total AI spend (LLM + STT + TTS + realtime) per UTC day, across
    # all users -- see app/core/cost_circuit_breaker.py. Blocks new AI calls with
    # a 503 once tripped, so a bug or an attack can't run up unbounded provider
    # cost. Adjustable at runtime via PUT /admin/spend-cap (owner-only).
    MAX_DAILY_AI_SPEND_USD: float = 50.0
    # Cloudflare Turnstile secret for the public /tools/study-plan endpoint
    # (see app/routers/tools.py) -- unset -> captcha check is skipped, same
    # no-op-when-unset pattern as CRON_SECRET/RESEND_API_KEY above.
    TURNSTILE_SECRET_KEY: str = ""
    # Slack Incoming Webhook URL for same-day-worthy failures (payment
    # amount mismatch, realtime provider connect failure, prune-cron
    # failure -- see app/services/alerts.py). Unset -> alerts no-op and
    # just log, same pattern as RESEND_API_KEY/TURNSTILE_SECRET_KEY above.
    SLACK_ALERT_WEBHOOK_URL: str = ""

settings = Settings()
