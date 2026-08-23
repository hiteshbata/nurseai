import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.env_guard import verify_production_isolation
from app.core.supabase import get_supabase
from app.core.redis_client import get_redis
from app.core import circuit_breaker
from app.core.request_id import RequestIDMiddleware, RequestIDLogFilter, get_request_id
from app.routers import auth, questions, speaking, speaking_realtime, scoring, progress, admin, admin_ai_models, admin_content_studio, grammar, comparison, writing, onboarding, scenario_generator, payments, sessions, profile, plans, submissions, leads, reading, listening, hub, vocab, mock, referrals, tools, technique, practice
from app.services.oet_questions import oet_service
from app.services.seed_scenarios import seed_scenarios

_log_handler = logging.StreamHandler()
_log_handler.addFilter(RequestIDLogFilter())
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s",
    handlers=[_log_handler],
)
logger = logging.getLogger(__name__)

# Fail closed: refuse to boot a qa/development ENVIRONMENT against the
# production Supabase project. No-ops until PRODUCTION_SUPABASE_PROJECT_REF
# is configured (see app/core/env_guard.py).
verify_production_isolation(settings.ENVIRONMENT, settings.SUPABASE_URL, settings.PRODUCTION_SUPABASE_PROJECT_REF)

# Mirrors the frontend's dev skip (frontend/app/providers.tsx) -- default
# SENTRY_ENVIRONMENT stays "production" so an unset var never silently
# disables prod reporting; local .env sets it to "development" to opt out.
if settings.SENTRY_DSN and settings.SENTRY_ENVIRONMENT != "development":
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

class UnhandledExceptionMiddleware:
    """Catches anything a route/dependency raises that FastAPI's own routing
    doesn't turn into a response (HTTPException/RequestValidationError are
    already handled inside ExceptionMiddleware and never reach here).

    This has to be a middleware, not @app.exception_handler(Exception): FastAPI
    special-cases a handler registered for Exception (or status 500) by wiring
    it into Starlette's ServerErrorMiddleware instead of ExceptionMiddleware
    (see FastAPI.build_middleware_stack), and ServerErrorMiddleware sits
    OUTSIDE CORSMiddleware -- so that response never gets CORS headers, which
    is exactly the bug this exists to fix (browsers report it as a
    network/CORS failure instead of a readable error). A plain middleware
    added here, before CORSMiddleware below, ends up INSIDE it (Starlette
    middleware added earlier ends up closer to the router), so the JSON
    response built here still passes back out through CORSMiddleware and
    gets normal CORS headers.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        response_started = False

        async def send_wrapper(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            if response_started:
                # Body already streaming -- headers are long gone, nothing
                # safe left to do but let Starlette's default handling apply.
                raise
            request_id = get_request_id()
            logger.error(
                "[UNHANDLED_EXCEPTION] method=%s path=%s request_id=%s",
                scope.get("method"), scope.get("path"), request_id, exc_info=exc,
            )
            response = JSONResponse(
                status_code=500,
                content={
                    "error": "internal_server_error",
                    "message": "Something went wrong. Please try again.",
                    "request_id": request_id,
                },
            )
            await response(scope, receive, send)


app.add_middleware(UnhandledExceptionMiddleware)

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

# Every route here is a per-user authenticated JSON API (progress, scoring,
# sessions, etc.) except these three, so default to uncacheable and
# allowlist the public ones rather than the other way round.
_PUBLIC_CACHE_PATHS = {
    "/": "public, max-age=300, stale-while-revalidate=600",
    "/announcement": "public, max-age=300, stale-while-revalidate=600",
}
_DEFAULT_CACHE_CONTROL = b"private, max-age=0, no-store"


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        cache_control = _PUBLIC_CACHE_PATHS.get(scope["path"], _DEFAULT_CACHE_CONTROL.decode()).encode()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + _SECURITY_HEADERS + [(b"cache-control", cache_control)]
            await send(message)

        await self.app(scope, receive, send_wrapper)


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)

app.include_router(auth.router)
app.include_router(questions.router)
app.include_router(speaking.router)
app.include_router(speaking_realtime.router)
app.include_router(scoring.router)
app.include_router(progress.router)
app.include_router(admin.router)
app.include_router(admin_ai_models.router)
app.include_router(admin_content_studio.router)
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
app.include_router(technique.router)
app.include_router(practice.router)

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
        "ai_providers": circuit_breaker.snapshot(),
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)