from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.core.supabase import get_supabase
from app.routers.auth import get_current_user, UserInfo
from app.services.ai_scoring import score_writing
from app.services.plan_gating import has_writing_access, get_plan_from_profile
import json

router = APIRouter(prefix="/writing", tags=["writing"])


class WritingSubmitRequest(BaseModel):
    scenario_id: int
    content: str


class WritingImageSubmitRequest(BaseModel):
    scenario_id: int
    image_base64: str


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
    supabase = get_supabase()

    # Plan gate — writing requires Pro or Elite
    profile = supabase.table("user_profiles").select("plan, plan_expires_at").eq("user_id", current_user.id).execute()
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

    scenario_data = supabase.table("scenarios").select(
        "id, title, nurse_card"
    ).eq("id", request.scenario_id).execute()

    if not scenario_data.data:
        raise HTTPException(status_code=404, detail="Scenario not found")

    scenario = scenario_data.data[0]
    nurse_card = scenario.get("nurse_card", {})

    feedback = await score_writing(
        content=request.content,
        nurse_card=nurse_card,
        scenario_title=scenario.get("title", ""),
        supabase=supabase,
    )

    supabase.table("submissions").insert({
        "user_id": current_user.id,
        "question_id": request.scenario_id,
        "module": "writing",
        "answer": request.content,
        "score": feedback.get("overall_score", 0),
        "feedback": json.dumps(feedback),
    }).execute()

    return {"success": True, "feedback": feedback}


@router.post("/submit-image")
async def submit_writing_image(
    request: WritingImageSubmitRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """Submit a photo of handwritten letter - uses Gemini Vision."""
    import httpx
    import base64
    from app.core.config import settings

    supabase = get_supabase()

    # Plan gate — writing requires Pro or Elite
    profile = supabase.table("user_profiles").select("plan, plan_expires_at").eq("user_id", current_user.id).execute()
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

    scenario_data = supabase.table("scenarios").select(
        "id, title, nurse_card"
    ).eq("id", request.scenario_id).execute()

    if not scenario_data.data:
        raise HTTPException(status_code=404, detail="Scenario not found")

    scenario = scenario_data.data[0]
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
    feedback = await score_writing(
        content=extracted_text,
        nurse_card=nurse_card,
        scenario_title=scenario.get("title", ""),
        supabase=supabase,
    )

    supabase.table("submissions").insert({
        "user_id": current_user.id,
        "question_id": request.scenario_id,
        "module": "writing",
        "answer": extracted_text,
        "score": feedback.get("overall_score", 0),
        "feedback": json.dumps(feedback),
    }).execute()

    return {"success": True, "extracted_text": extracted_text, "feedback": feedback}
