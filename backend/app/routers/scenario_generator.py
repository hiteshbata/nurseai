import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from app.core.supabase import get_supabase
from app.core.config import settings
from app.core.error_utils import redact_api_keys
from app.routers.admin import require_admin
import httpx
import base64
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/scenario", tags=["admin"])

VISION_MODEL = "google/gemini-2.5-flash"


async def _call_vision_api(image_base64: str, prompt: str, json_mode: bool = True) -> Dict[str, Any]:
    """Send image + prompt to Gemini via OpenRouter or direct Gemini API."""
    openrouter_key = settings.OPENROUTER_API_KEY
    gemini_key = settings.GEMINI_API_KEY

    # Try OpenRouter first (supports multimodal)
    if openrouter_key:
        try:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                        },
                    ],
                }
            ]
            payload = {
                "model": VISION_MODEL,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 4000,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}

            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openrouter_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"]
                    if json_mode:
                        return json.loads(content)
                    return {"raw_feedback": content}
        except Exception as e:
            logger.error(
                "[EXTERNAL_API_FAILURE] service=OPENROUTER type=unknown detail=%s",
                redact_api_keys(str(e)[:500]),
            )
            print(f"[OpenRouter vision] failed: {e}")

    raise HTTPException(status_code=502, detail="AI vision provider unavailable")


EXTRACT_PROMPT = """You are an OET exam content specialist. Analyze this image of an OET roleplay card and extract all content into a structured JSON format. If the image is not an OET roleplay card, return an error. Extract exactly what is written, do not invent or add content that is not visible in the image.

Return ONLY this JSON structure, no other text:
{
  "title": "short descriptive title for this scenario",
  "setting": "the ward/clinic/location and context paragraph",
  "difficulty": "beginner|intermediate|advanced",
  "specialty": "general|surgical|paediatric|aged_care|mental_health|ICU|emergency|community",
  "patient_details": {
    "name": "",
    "age": 0,
    "occupation": "",
    "reason_for_admission": "",
    "emotional_state": "",
    "background": ""
  },
  "nurse_card": {
    "role": "You are the nurse in charge of this patient",
    "tasks": [
      "Task 1 description",
      "Task 2 description",
      "Task 3 description",
      "Task 4 description",
      "Task 5 description"
    ]
  },
  "interlocutor_card": {
    "persona": "how the patient should behave",
    "emotional_triggers": ["trigger 1", "trigger 2"],
    "questions_to_ask": ["question 1", "question 2"],
    "information_to_withhold": ["info 1", "info 2"]
  },
  "tags": ["tag1", "tag2"],
  "is_original": false
}"""


@router.post("/extract-from-image")
async def extract_from_image(
    file: UploadFile = File(...),
    _admin=Depends(require_admin),
):
    """Extract OET scenario from roleplay card image using AI vision."""
    allowed_types = ["image/jpeg", "image/png", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only JPG, PNG, and WebP images are supported")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 5MB")

    image_base64 = base64.b64encode(contents).decode("utf-8")

    try:
        result = await _call_vision_api(image_base64, EXTRACT_PROMPT, json_mode=True)
        if "error" in result:
            return result
        return result
    except Exception:
        return {
            "error": "Could not extract scenario from image. Please ensure the image is a clear OET roleplay card."
        }


GENERATE_PROMPT_TEMPLATE = """You are an OET content creator. Based on the structure and format of this OET roleplay card, create a completely ORIGINAL scenario inspired by the same nursing specialty and difficulty level.

IMPORTANT RULES:
- Change the patient name, age, occupation, and condition
- Change the specific tasks while keeping the same OET format
- Keep the same specialty: {specialty}
- Keep the same difficulty: {difficulty}
- The scenario must be clinically realistic for a nurse
- Do NOT copy any text from the original
- Set is_original to true in your response

Return the same JSON structure as the input but with completely new original content."""


@router.post("/generate-original")
async def generate_original(payload: Dict[str, Any], _admin=Depends(require_admin)):
    """Generate an original scenario inspired by the extracted one."""
    specialty = payload.get("specialty", "general")
    difficulty = payload.get("difficulty", "intermediate")
    prompt = GENERATE_PROMPT_TEMPLATE.format(specialty=specialty, difficulty=difficulty)

    try:
        result = await _call_vision_api(
            image_base64="",
            prompt=f"{prompt}\n\nInput scenario:\n{json.dumps(payload, indent=2)}",
            json_mode=True,
        )
        return result
    except Exception:
        raise HTTPException(status_code=502, detail="AI generation failed")


SCORING_CRITERIA = {
    "criteria": [
        "empathy", "patient_perspective", "providing_structure",
        "information_gathering", "information_giving",
        "intelligibility", "fluency", "appropriateness_of_language", "grammar",
    ]
}


@router.post("/save")
def save_scenario(payload: Dict[str, Any], _admin=Depends(require_admin)):
    """Save scenario to the database."""
    required = ["title", "setting", "difficulty"]
    for field in required:
        if not payload.get(field):
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    patient = payload.get("patient_details", {}) or {}
    nurse = payload.get("nurse_card", {}) or {}
    inter = payload.get("interlocutor_card", {}) or {}

    supabase = get_supabase()
    data = supabase.table("scenarios").insert({
        "module": "speaking",
        "is_active": True,
        "title": payload["title"],
        "setting": payload.get("setting", ""),
        "difficulty": payload.get("difficulty", "intermediate"),
        "nurse_card": {
            "role": nurse.get("role", "You are the nurse in charge"),
            "tasks": nurse.get("tasks", []),
            "setting_description": payload.get("setting", ""),
            "patient_summary": f"{patient.get('name', '')}, {patient.get('age', '')}, {patient.get('reason_for_admission', '')}",
        },
        "interlocutor_card": {
            "patient_name": patient.get("name", "Patient"),
            "age": str(patient.get("age", "")),
            "condition": patient.get("reason_for_admission", ""),
            "mood": patient.get("emotional_state", "Cooperative"),
            "background": patient.get("background", ""),
            "concerns": inter.get("questions_to_ask", []),
            "instructions_for_ai": inter.get("persona", ""),
        },
        "scoring_criteria": SCORING_CRITERIA,
        "specialty": payload.get("specialty", ""),
    }).execute()
    return data.data[0]
