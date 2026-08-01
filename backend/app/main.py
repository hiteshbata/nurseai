from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.supabase import get_supabase
from app.core.redis_client import get_redis
from app.routers import auth, questions, speaking, speaking_realtime, scoring, progress, admin, grammar, comparison, writing, onboarding, scenario_generator, payments, sessions, profile, plans, submissions, leads, reading, listening, hub, vocab, mock, referrals, tools
from app.services.oet_questions import oet_service
from app.services.seed_scenarios import seed_scenarios

if settings.SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        send_default_pii=False,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    supabase = get_supabase()

    # Ensure user_roles table exists
    supabase.table("user_roles").select("user_id").limit(1).execute()

    # Verify user_profiles table is accessible (may not exist yet)
    try:
        supabase.table("user_profiles").select("user_id").limit(1).execute()
    except Exception:
        print("[WARN] user_profiles table not found — run the migration SQL to create it")

    try:
        data = supabase.table("questions").select("id").limit(1).execute()
        if not data.data:
            print("Seeding database with OET questions...")
            oet_service.seed_database(supabase)
        data = supabase.table("scenarios").select("id").limit(1).execute()
        if not data.data:
            print("Seeding database with OET scenarios...")
            seed_scenarios()
    except Exception:
        print("[WARN] startup seeding check failed — Supabase unreachable or tables missing, continuing to serve")

    if not settings.REDIS_URL and settings.SENTRY_ENVIRONMENT == "production":
        print(
            "[WARN] REDIS_URL is unset in production — rate limiting and role "
            "caching will silently degrade to per-process memory, which is "
            "wrong once more than one worker/instance is running."
        )

    yield


_docs_enabled = settings.SENTRY_ENVIRONMENT != "production"

app = FastAPI(
    title="NurseAI API",
    description="AI-powered OET coaching platform for nurses",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

origins = settings.ALLOWED_ORIGINS.split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"strict-transport-security", b"max-age=63072000; includeSubDomains; preload"),
]


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + _SECURITY_HEADERS
            await send(message)

        await self.app(scope, receive, send_wrapper)


app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth.router)
app.include_router(questions.router)
app.include_router(speaking.router)
app.include_router(speaking_realtime.router)
app.include_router(scoring.router)
app.include_router(progress.router)
app.include_router(admin.router)
app.include_router(grammar.router)
app.include_router(comparison.router)
app.include_router(writing.router)
app.include_router(onboarding.router)
app.include_router(scenario_generator.router)
app.include_router(payments.router)
app.include_router(sessions.router)
app.include_router(profile.router)
app.include_router(plans.router)
app.include_router(submissions.router)
app.include_router(leads.router)
app.include_router(reading.router)
app.include_router(listening.router)
app.include_router(hub.router)
app.include_router(vocab.router)
app.include_router(mock.router)
app.include_router(referrals.router)
app.include_router(tools.router)

@app.get("/")
def read_root():
    return {
        "message": "Welcome to NurseAI API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
    }

@app.get("/announcement")
def get_announcement():
    """Public, unauthenticated -- powers the site-wide banner every page
    renders. Admin panel writes to the same `settings` table via the
    existing generic PUT /admin/settings/{key}, no dedicated write endpoint
    needed."""
    try:
        rows = (
            get_supabase().table("settings").select("key, value")
            .in_("key", ["announcement_banner_enabled", "announcement_banner_text"])
            .execute().data
        )
        values = {r["key"]: r["value"] for r in rows}
    except Exception:
        return {"enabled": False, "text": ""}
    return {
        "enabled": values.get("announcement_banner_enabled") == "true",
        "text": values.get("announcement_banner_text", ""),
    }


@app.get("/health")
async def health_check():
    timestamp = datetime.now(timezone.utc).isoformat()

    database_status = "ok"
    try:
        supabase = get_supabase()
        supabase.table("scenarios").select("id").limit(1).execute()
    except Exception:
        database_status = "error"

    ai_api_status = "ok" if (settings.OPENROUTER_API_KEY or settings.GEMINI_API_KEY) else "not_configured"

    if not settings.REDIS_URL:
        redis_status = "not_configured"
    else:
        try:
            redis_status = "ok" if get_redis().ping() else "error"
        except Exception:
            redis_status = "error"

    overall = (
        "ok"
        if database_status == "ok" and ai_api_status in ("ok", "not_configured") and redis_status != "error"
        else "degraded"
    )

    return {
        "status": overall,
        "timestamp": timestamp,
        "database": database_status,
        "ai_api": ai_api_status,
        "redis": redis_status,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)