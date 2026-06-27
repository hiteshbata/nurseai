from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
from app.core.config import settings
from app.core.supabase import get_supabase
from app.routers import auth, questions, speaking, scoring, progress, admin, grammar, comparison, writing, onboarding, scenario_generator
from app.services.oet_questions import oet_service
from app.services.seed_scenarios import seed_scenarios

app = FastAPI(
    title="NurseAI API",
    description="AI-powered OET coaching platform for nurses",
    version="1.0.0",
)

origins = settings.ALLOWED_ORIGINS.split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(questions.router)
app.include_router(speaking.router)
app.include_router(scoring.router)
app.include_router(progress.router)
app.include_router(admin.router)
app.include_router(grammar.router)
app.include_router(comparison.router)
app.include_router(writing.router)
app.include_router(onboarding.router)
app.include_router(scenario_generator.router)

@app.get("/")
def read_root():
    return {
        "message": "Welcome to NurseAI API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
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

    ai_api_status = "ok"
    if settings.OPENROUTER_API_KEY or settings.GEMINI_API_KEY:
        try:
            headers = {"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"} if settings.OPENROUTER_API_KEY else {}
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get("https://openrouter.ai/api/v1/auth/key", headers=headers)
                if resp.status_code >= 500:
                    ai_api_status = "error"
        except Exception:
            ai_api_status = "error"
    else:
        ai_api_status = "not_configured"

    overall = "ok" if database_status == "ok" and ai_api_status in ("ok", "not_configured") else "degraded"

    return {
        "status": overall,
        "timestamp": timestamp,
        "database": database_status,
        "ai_api": ai_api_status,
    }

@app.on_event("startup")
def startup_event():
    supabase = get_supabase()

    # Ensure user_roles table exists
    supabase.table("user_roles").select("user_id").limit(1).execute()

    # Verify user_profiles table is accessible (may not exist yet)
    try:
        supabase.table("user_profiles").select("user_id").limit(1).execute()
    except Exception:
        print("[WARN] user_profiles table not found — run the migration SQL to create it")

    data = supabase.table("questions").select("id").limit(1).execute()
    if not data.data:
        print("Seeding database with OET questions...")
        oet_service.seed_database(supabase)
    data = supabase.table("scenarios").select("id").limit(1).execute()
    if not data.data:
        print("Seeding database with OET scenarios...")
        seed_scenarios()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)