from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional
from app.core.supabase import get_supabase
from app.routers.auth import get_current_user, UserInfo
from app.services.speech_to_text import speech_to_text
from app.services.ai_scoring import get_patient_response, score_speaking, _call_ai
import json

router = APIRouter(prefix="/speaking", tags=["speaking"])


@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    current_user: UserInfo = Depends(get_current_user),
):
    audio_data = await audio.read()
    result = await speech_to_text.transcribe_audio(audio_data, audio.filename or "audio.wav")
    return result


class ChatMessage(BaseModel):
    role: str  # "nurse" or "patient"
    content: str


class PatientChatRequest(BaseModel):
    scenario_id: int
    message: str
    history: List[ChatMessage] = []


class PatientChatResponse(BaseModel):
    patient_reply: str
    updated_history: List[ChatMessage]


class SpeakingSubmitRequest(BaseModel):
    scenario_id: int
    history: List[ChatMessage]
    audio_base64: Optional[str] = None


@router.get("/scenarios")
def list_scenarios(current_user: UserInfo = Depends(get_current_user)):
    """List all active speaking scenarios."""
    supabase = get_supabase()
    data = supabase.table("scenarios").select(
        "id, title, setting, difficulty, nurse_card, interlocutor_card"
    ).eq("module", "speaking").eq("is_active", True).execute()
    return data.data


@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: int, current_user: UserInfo = Depends(get_current_user)):
    """Get a single scenario with nurse card (interlocutor card NOT sent to student)."""
    supabase = get_supabase()
    data = supabase.table("scenarios").select(
        "id, title, setting, difficulty, nurse_card, scoring_criteria"
    ).eq("id", scenario_id).eq("is_active", True).execute()
    if not data.data:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return data.data[0]


@router.post("/chat")
async def chat_with_patient(
    request: PatientChatRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """
    Multi-turn conversation with AI patient.
    Student sends a message -> AI responds as the patient (following interlocutor card).
    """
    supabase = get_supabase()

    # Get scenario with interlocutor card
    scenario_data = supabase.table("scenarios").select(
        "*"
    ).eq("id", request.scenario_id).eq("is_active", True).execute()

    if not scenario_data.data:
        raise HTTPException(status_code=404, detail="Scenario not found")

    scenario = scenario_data.data[0]
    interlocutor_card = scenario.get("interlocutor_card", {})

    # Build conversation history
    history = [{"role": msg.role, "content": msg.content} for msg in request.history]

    # Get AI patient response
    patient_reply = await get_patient_response(
        interlocutor_card=interlocutor_card,
        conversation_history=history,
        nurse_message=request.message,
        supabase=supabase,
    )

    # Update history
    updated_history = request.history + [
        ChatMessage(role="nurse", content=request.message),
        ChatMessage(role="patient", content=patient_reply),
    ]

    return PatientChatResponse(
        patient_reply=patient_reply,
        updated_history=updated_history,
    )


@router.post("/score")
async def score_speaking_session(
    request: SpeakingSubmitRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """
    Score a completed speaking session.
    Uses nurse card tasks as scoring criteria.
    """
    supabase = get_supabase()

    # Get scenario
    scenario_data = supabase.table("scenarios").select(
        "id, title, nurse_card, scoring_criteria"
    ).eq("id", request.scenario_id).execute()

    if not scenario_data.data:
        raise HTTPException(status_code=404, detail="Scenario not found")

    scenario = scenario_data.data[0]
    nurse_card = scenario.get("nurse_card", {})

    # Build conversation history
    history = [{"role": msg.role, "content": msg.content} for msg in request.history]

    # Score
    feedback = await score_speaking(
        nurse_card=nurse_card,
        conversation_history=history,
        scenario_title=scenario.get("title", ""),
        supabase=supabase,
    )

    # Save submission
    transcript = "\n".join([
        f"{'Nurse' if m.role == 'nurse' else 'Patient'}: {m.content}"
        for m in request.history
    ])

    supabase.table("submissions").insert({
        "user_id": current_user.id,
        "question_id": request.scenario_id,
        "module": "speaking",
        "answer": transcript,
        "score": feedback.get("overall_band", 0),
        "feedback": json.dumps(feedback),
    }).execute()

    return {"success": True, "feedback": feedback}


@router.post("/scenarios/generate")
async def generate_scenario(payload: dict):
    """Generate a new OET scenario dynamically for student practice."""
    from app.services.ai_scoring import _call_ai
    import json
    
    specialty = payload.get("specialty", "general")
    difficulty = payload.get("difficulty", "intermediate")
    setting = payload.get("setting", "")
    
    prompt = f"""You are an OET exam content creator. Generate a realistic OET Speaking roleplay card for a nursing student.

REQUIREMENTS:
- Specialty: {specialty}
- Difficulty: {difficulty}
{f'- Setting: {setting}' if setting else ''}
- Must be clinically realistic
- Tasks must follow real OET format (5-6 specific tasks)
- Patient must have a clear emotional state and believable background

Return ONLY this JSON, no other text:
{{
  "title": "short scenario title",
  "setting": "ward/clinic description and patient context paragraph",
  "difficulty": "{difficulty}",
  "nurse_card": {{
    "role": "You are the nurse. Describe the situation briefly.",
    "tasks": [
      "Task 1",
      "Task 2", 
      "Task 3",
      "Task 4",
      "Task 5"
    ]
  }},
  "interlocutor_card": {{
    "patient_name": "First name only",
    "age": 35,
    "condition": "presenting condition",
    "mood": "anxious|worried|confused|resistant|cooperative",
    "background": "2 sentence patient background",
    "emotional_triggers": ["trigger 1", "trigger 2"],
    "questions_to_ask": ["question 1", "question 2", "question 3"],
    "information_to_withhold": ["info to withhold 1", "info to withhold 2"],
    "instructions_for_ai": "detailed persona description"
  }}
}}"""

    result = await _call_ai(
        [{"role": "user", "content": prompt}],
        max_tokens=1500,
        json_mode=True
    )
    
    if "nurse_card" not in result:
        raise HTTPException(status_code=502, detail="Failed to generate scenario")
    
    return result


# Legacy endpoint for backward compatibility
@router.post("/submit")
async def submit_speaking_response(
    audio: UploadFile = File(...),
    question_id: int = None,
    current_user: UserInfo = Depends(get_current_user),
):
    """Legacy endpoint - uses old questions table."""
    supabase = get_supabase()
    try:
        audio_data = await audio.read()
        # Fall back to old scoring for backward compatibility
        transcription = await speech_to_text.transcribe_audio(audio_data)
        # Use legacy mock feedback for now
        feedback = {
            "overall_score": 7.8,
            "score": 78,
            "grade": "B",
            "fluency": "Good - minimal hesitation",
            "vocabulary": "Good use of medical terminology",
            "grammar": "Mostly accurate with minor errors",
            "pronunciation": "Clear with understandable accent",
            "medical_communication": "Well-structured handover with appropriate clinical language",
            "overall_feedback": "Good performance overall. Your communication was clear and professional.",
        }
        supabase.table("submissions").insert({
            "user_id": current_user.id,
            "question_id": question_id,
            "module": "speaking",
            "answer": transcription,
            "score": feedback["score"],
            "feedback": json.dumps(feedback),
        }).execute()

        return {"success": True, "transcription": transcription, "feedback": feedback}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to process audio")