from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.core.supabase import get_supabase
from app.core.threading import run_sync
from app.core.rate_limit import SlidingWindowRateLimiter
from app.routers.auth import get_current_user, UserInfo
from app.core.feature_flags import require_feature
from app.services.ai_scoring import score_writing
from app.services.plan_gating import has_writing_access, get_plan_from_profile
import base64
import json

router = APIRouter(prefix="/writing", tags=["writing"], dependencies=[Depends(require_feature("writing_practice"))])

SUBMIT_RATE_LIMIT_MAX_CALLS = 20
SUBMIT_RATE_LIMIT_WINDOW_SECONDS = 600
_submit_rate_limiter = SlidingWindowRateLimiter(SUBMIT_RATE_LIMIT_MAX_CALLS, SUBMIT_RATE_LIMIT_WINDOW_SECONDS, name="writing:submit")

SUBMIT_IMAGE_RATE_LIMIT_MAX_CALLS = 10
SUBMIT_IMAGE_RATE_LIMIT_WINDOW_SECONDS = 600
_submit_image_rate_limiter = SlidingWindowRateLimiter(SUBMIT_IMAGE_RATE_LIMIT_MAX_CALLS, SUBMIT_IMAGE_RATE_LIMIT_WINDOW_SECONDS, name="writing:submit_image")

MAX_IMAGE_BYTES = 5 * 1024 * 1024
# base64 inflates size ~4/3; reject oversized payloads before spending CPU on decode.
MAX_IMAGE_BASE64_CHARS = MAX_IMAGE_BYTES * 4 // 3 + 4


class WritingSubmitRequest(BaseModel):
    scenario_id: int
    content: str


class WritingImageSubmitRequest(BaseModel):
    scenario_id: int
    image_base64: str


async def _require_writing_scenario(supabase, user_id: str, scenario_id: int) -> dict:
    """Plan-gate writing access and fetch the scenario. Shared by /submit and /submit-image."""
    profile = await run_sync(
        supabase.table("user_profiles").select("plan, plan_expires_at").eq("user_id", user_id).execute
    )
    plan = get_plan_from_profile(profile.data[0] if profile.data else {})
    if not has_writing_access(plan):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Writing practice requires Pro or Elite plan",
                "upgrade_required": True,
                "current_plan": plan,
            },
        )

    scenario_data = await run_sync(
        supabase.table("scenarios").select("id, title, nurse_card").eq("id", scenario_id).execute
    )
    if not scenario_data.data:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return scenario_data.data[0]


async def _score_and_save(supabase, user_id: str, scenario_id: int, content: str, nurse_card: dict, scenario_title: str) -> dict:
    """Score writing content and persist the submission. Shared by /submit and /submit-image."""
    feedback = await score_writing(
        content=content,
        nurse_card=nurse_card,
        scenario_title=scenario_title,
        supabase=supabase,
    )

    if feedback.get("provider_failure"):
        raise HTTPException(
            status_code=503,
            detail="Scoring is temporarily unavailable. Please try again in a few minutes.",
        )

    await run_sync(
        supabase.table("submissions").insert({
            "user_id": user_id,
            "scenario_id": scenario_id,
            "module": "writing",
            "answer": content,
            "score": feedback.get("overall_score") or 0,
            "feedback": json.dumps(feedback),
        }).execute
    )

    return feedback


@router.get("/scenarios")
def list_scenarios(current_user: UserInfo = Depends(get_current_user)):
    """List all active writing scenarios."""
    supabase = get_supabase()
    data = supabase.table("scenarios").select(
        "id, title, setting, difficulty, nurse_card"
    ).eq("module", "writing").eq("is_active", True).execute()
    return data.data


@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: int, current_user: UserInfo = Depends(get_current_user)):
    """Get a writing scenario with nurse card (scoring rubric NOT sent to student)."""
    supabase = get_supabase()
    data = supabase.table("scenarios").select(
        "id, title, setting, difficulty, nurse_card"
    ).eq("id", scenario_id).eq("is_active", True).execute()
    if not data.data:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return data.data[0]


@router.post("/submit")
async def submit_writing(
    request: WritingSubmitRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """Submit a typed writing response for scoring."""
    if _submit_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many submissions — please slow down.")

    supabase = get_supabase()
    scenario = await _require_writing_scenario(supabase, current_user.id, request.scenario_id)

    feedback = await _score_and_save(
        supabase, current_user.id, request.scenario_id,
        request.content, scenario.get("nurse_card", {}), scenario.get("title", ""),
    )

    return {"success": True, "feedback": feedback}


@router.post("/submit-image")
async def submit_writing_image(
    request: WritingImageSubmitRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """Submit a photo of handwritten letter - uses Gemini Vision."""
    import httpx
    from app.core.config import settings

    if _submit_image_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many submissions — please slow down.")

    if len(request.image_base64) > MAX_IMAGE_BASE64_CHARS:
        raise HTTPException(status_code=400, detail="Image must be under 5MB")

    try:
        decoded_image = base64.b64decode(request.image_base64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image data")
    if len(decoded_image) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image must be under 5MB")

    supabase = get_supabase()
    scenario = await _require_writing_scenario(supabase, current_user.id, request.scenario_id)
    nurse_card = scenario.get("nurse_card", {})

    # Use Gemini Vision to read the handwritten letter
    extracted_text = None
    last_error = ""
    models_to_try = [
        "google/gemma-4-31b-it:free",
        "google/gemini-2.5-flash",
    ]
    async with httpx.AsyncClient(timeout=60.0) as client:
        for model in models_to_try:
            try:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Read this handwritten nursing letter. Extract and return ONLY the text content. Preserve structure."},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{request.image_base64}"}}
                            ],
                        }],
                        "max_tokens": 1000,
                    },
                )
                if response.status_code == 200:
                    result = response.json()
                    extracted_text = result["choices"][0]["message"]["content"]
                    break
                else:
                    last_error = f"{model} returned HTTP {response.status_code}"
            except Exception as exc:
                last_error = f"{model} failed: {str(exc)}"
                continue
    if not extracted_text:
        raise HTTPException(status_code=500, detail=f"Image OCR failed: {last_error}")

    # Score the extracted text
    feedback = await _score_and_save(
        supabase, current_user.id, request.scenario_id,
        extracted_text, nurse_card, scenario.get("title", ""),
    )

    return {"success": True, "extracted_text": extracted_text, "feedback": feedback}
