"""AI scoring and patient role-play using the card system."""
import httpx
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from app.core.config import settings
from app.core.supabase import get_supabase

GEMINI_MODEL = "gemini-2.0-flash"
OPENAI_MODEL = "gpt-4o-mini"
OPENROUTER_MODEL = "openai/gpt-4o-mini"


def _log_ai_error(
    function_name: str,
    error_type: str,
    error_message: str,
    user_id: str = "",
):
    """Log an AI API error to the database logs table."""
    try:
        supabase = get_supabase()
        supabase.table("logs").insert({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "function_name": function_name,
            "error_type": error_type,
            "error_message": str(error_message)[:500],
            "resolved": False,
        }).execute()
    except Exception as log_err:
        print(f"[LOGGING FAILED] Could not write to logs table: {log_err}")


async def _call_ai(
    messages: list,
    model: str = "",
    max_tokens: int = 1000,
    json_mode: bool = False,
    provider: str = "",
    user_id: str = "",
) -> Dict[str, Any]:
    """Call AI via the configured provider. Supports Gemini, OpenAI, and OpenRouter."""
    provider = provider or settings.AI_PROVIDER
    gemini_key = settings.GEMINI_API_KEY
    openai_key = settings.OPENAI_API_KEY
    openrouter_key = settings.OPENROUTER_API_KEY

    # Try providers in priority order: configured provider first, then fallbacks
    providers_to_try = []
    if provider == "gemini" and gemini_key:
        providers_to_try.append(("gemini", gemini_key, model or GEMINI_MODEL))
    if provider == "openai" and openai_key:
        providers_to_try.append(("openai", openai_key, model or OPENAI_MODEL))
    if provider == "openrouter" and openrouter_key:
        providers_to_try.append(("openrouter", openrouter_key, model or OPENROUTER_MODEL))

    # Fallbacks if configured provider fails or has no key
    if not providers_to_try:
        if gemini_key:
            providers_to_try.append(("gemini", gemini_key, model or GEMINI_MODEL))
        if openai_key:
            providers_to_try.append(("openai", openai_key, model or OPENAI_MODEL))
        if openrouter_key:
            providers_to_try.append(("openrouter", openrouter_key, model or OPENROUTER_MODEL))

    last_error = ""
    for prov, key, mdl in providers_to_try:
        try:
            if prov == "gemini":
                result = await _call_gemini(messages, key, mdl, max_tokens, json_mode)
            elif prov == "openai":
                result = await _call_openai(messages, key, mdl, max_tokens, json_mode)
            else:
                result = await _call_openrouter(messages, key, mdl, max_tokens, json_mode)
            if result.get("raw_feedback") or (json_mode and result):
                return result
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if e.response else 0
            err_msg = f"HTTP {status_code}: {str(e)[:200]}"
            print(f"[{prov}] {mdl} HTTP error: {err_msg}")
            _log_ai_error("_call_ai", f"{prov}_http_error", err_msg, user_id)
            last_error = err_msg
            continue
        except httpx.TimeoutException as e:
            err_msg = f"Timeout after {max_tokens} tokens: {str(e)[:200]}"
            print(f"[{prov}] {mdl} timeout: {err_msg}")
            _log_ai_error("_call_ai", f"{prov}_timeout", err_msg, user_id)
            last_error = err_msg
            continue
        except json.JSONDecodeError as e:
            err_msg = f"JSON parse error: {str(e)[:200]}"
            print(f"[{prov}] {mdl} JSON error: {err_msg}")
            _log_ai_error("_call_ai", f"{prov}_json_error", err_msg, user_id)
            last_error = err_msg
            continue
        except Exception as e:
            err_msg = str(e)[:300]
            print(f"[{prov}] {mdl} failed: {err_msg}")
            _log_ai_error("_call_ai", f"{prov}_error", err_msg, user_id)
            last_error = err_msg
            continue

    _log_ai_error("_call_ai", "all_providers_failed", last_error, user_id)
    return {"raw_feedback": "I'm sorry, the AI service is temporarily unavailable. Please try again later."}


async def _call_gemini(
    messages: list, api_key: str, model: str, max_tokens: int, json_mode: bool
) -> Dict[str, Any]:
    """Call Google Gemini API directly."""
    system_parts = []
    contents = []
    for msg in messages:
        if msg["role"] == "system":
            system_parts.append({"text": msg["content"]})
        elif msg["role"] == "user":
            contents.append({"role": "user", "parts": [{"text": msg["content"]}]})
        elif msg["role"] == "assistant":
            contents.append({"role": "model", "parts": [{"text": msg["content"]}]})
        else:
            contents.append({"role": "user", "parts": [{"text": msg["content"]}]})

    payload: Dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": max_tokens,
        },
    }
    if system_parts:
        payload["systemInstruction"] = {"parts": system_parts}
    if json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload)
        if response.status_code != 200:
            err = response.text[:200]
            raise Exception(f"Gemini API error {response.status_code}: {err}")
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise Exception("No candidates in Gemini response")
        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        if json_mode:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"raw_feedback": text}
        return {"raw_feedback": text}


async def _call_openai(
    messages: list, api_key: str, model: str, max_tokens: int, json_mode: bool
) -> Dict[str, Any]:
    """Call OpenAI API directly."""
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        if response.status_code != 200:
            err = response.text[:200]
            raise Exception(f"OpenAI API error {response.status_code}: {err}")
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        if json_mode:
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"raw_feedback": content}
        return {"raw_feedback": content}


async def _call_openrouter(
    messages: list, api_key: str, model: str, max_tokens: int, json_mode: bool
) -> Dict[str, Any]:
    """Call OpenRouter API."""
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        if response.status_code != 200:
            err = response.text[:200]
            raise Exception(f"OpenRouter API error {response.status_code}: {err}")
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        if json_mode:
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"raw_feedback": content}
        return {"raw_feedback": content}


def _get_setting(supabase, key: str, default: str = "") -> str:
    """Read a setting from the settings table at runtime."""
    try:
        data = supabase.table("settings").select("value").eq("key", key).execute()
        if data.data:
            return data.data[0]["value"]
    except Exception:
        pass
    return default


# ── LEGACY WRAPPER FUNCTIONS (for simple question-based scoring) ─────

async def analyze_writing_submission(response: str, question_content: str) -> Dict[str, Any]:
    """Legacy wrapper: simple question -> score, without card system."""
    nurse_card = {"tasks": [f"Respond to: {question_content}"]}
    return await score_writing(
        content=response, nurse_card=nurse_card, scenario_title=question_content
    )


async def analyze_speaking_submission(response: str, question_content: str) -> Dict[str, Any]:
    """Legacy wrapper: simple question -> score, without card system."""
    nurse_card = {"tasks": [f"Respond to: {question_content}"]}
    return await score_speaking(
        nurse_card=nurse_card,
        conversation_history=[{"role": "nurse", "content": response}],
        scenario_title=question_content,
    )


# ── PATIENT ROLE-PLAY ────────────────────────────────────────────────

async def get_patient_response(
    interlocutor_card: Dict[str, Any],
    conversation_history: List[Dict[str, str]],
    nurse_message: str,
    supabase=None,
    user_id: str = "",
) -> str:
    """
    Get AI patient response based on interlocutor card.
    The interlocutor card IS the instruction — no custom prompt needed.
    """
    card = interlocutor_card
    emotional_triggers = card.get('emotional_triggers', [])
    questions_to_ask = card.get('questions_to_ask', card.get('concerns', []))
    info_to_withhold = card.get('information_to_withhold', [])
    instructions = card.get('instructions_for_ai', card.get('persona', ''))

    system_prompt = f"""You are playing a patient in an OET nursing roleplay exam. Follow this card EXACTLY.

PATIENT PROFILE:
- Name: {card.get('patient_name', 'Patient')}
- Age: {card.get('age', 'adult')} years old
- Condition: {card.get('condition', 'Not specified')}
- Mood: {card.get('mood', 'Cooperative')}
- Background: {card.get('background', '')}

PERSONA & BEHAVIOUR:
{instructions}

EMOTIONAL TRIGGERS (show these emotions when these topics come up):
{chr(10).join(f'- {t}' for t in emotional_triggers) if emotional_triggers else '- Show general anxiety about your condition'}

QUESTIONS YOU MUST ASK (spread these across the conversation naturally):
{chr(10).join(f'- {q}' for q in questions_to_ask) if questions_to_ask else '- Ask about your treatment plan'}

INFORMATION TO WITHHOLD (only reveal if nurse asks directly):
{chr(10).join(f'- {i}' for i in info_to_withhold) if info_to_withhold else '- Do not volunteer extra information'}

STRICT RULES:
1. Stay fully in character at all times
2. Show emotions — the nurse must acknowledge them
3. Ask your questions naturally throughout the conversation
4. Do NOT reveal withheld information unless the nurse specifically asks
5. Keep responses 2-4 sentences — realistic patient length
6. Occasionally misunderstand or ask for clarification to test the nurse
7. Never give medical advice or diagnose yourself"""

    messages = [{"role": "system", "content": system_prompt}]
    for msg in conversation_history:
        role = "user" if msg["role"] == "nurse" else "assistant"
        messages.append({"role": role, "content": msg["content"]})
    messages.append({"role": "user", "content": nurse_message})

    result = await _call_ai(messages, max_tokens=200, user_id=user_id)
    return result.get("raw_feedback", "I'm not sure what to say...")


# ── SPEAKING SCORING ───────────────────────────────────────────────────

async def score_speaking(
    nurse_card: Dict[str, Any],
    conversation_history: List[Dict[str, str]],
    scenario_title: str = "",
    supabase=None,
    user_id: str = "",
) -> Dict[str, Any]:
    """
    Score a speaking session using the nurse card's tasks as criteria.
    Returns OET-style scores across 9 criteria with weighted overall band.
    """
    card = nurse_card
    tasks = card.get("tasks", [])
    tasks_text = "\n".join(f"- {t}" for t in tasks) if tasks else "No roleplay card provided"

    conversation_text = "\n".join([
        f"{'Nurse' if m['role'] == 'nurse' else 'Patient'}: {m['content']}"
        for m in conversation_history
    ])

    scoring_prompt = f"""You are an official OET Speaking examiner. Score the nurse's roleplay transcript strictly against the 9 official OET criteria.

SCENARIO: {scenario_title}
NURSE'S TASKS (what they needed to do):
{tasks_text}

FULL CONVERSATION:
{conversation_text}

CLINICAL COMMUNICATION -- score each 0 to 6:
1. relationship_building: Did nurse introduce themselves warmly? Use sympathetic tone? Make patient feel comfortable from the start?
2. patient_perspective: Did nurse actively listen and respond to patient cues, concerns and questions throughout? Did they acknowledge emotions?
3. providing_structure: Did conversation follow OET sequence -- introduce → enquire → explain → advise? Were all roleplay card prompts addressed in logical order?
4. information_gathering: Did nurse use open questions first then closed? Did they summarise and check understanding?
5. information_giving: Was advice clear, concise, jargon-free? Given as suggestions not orders? Checked patient understood?

LINGUISTIC -- score each 0 to 6:
6. intelligibility: Was speech clear? Correct word stress, intonation, rhythm? Easy to understand?
7. fluency: Smooth pace? Natural pauses? Minimal filler words like "um" and "ah"?
8. appropriateness_of_language: Suitable register for patient? Medical terms explained in plain language?
9. grammar: Range of grammar structures used accurately? Varied vocabulary and idioms?

BAND DESCRIPTORS:
6 = Exceptional, no errors
5 = Good, minor errors only
4 = Adequate, some errors but communicates effectively
3 = Limited, errors affect communication
2 = Weak, frequent errors impede communication
1 = Very weak, communication breaks down
0 = Not demonstrated at all

Return ONLY this JSON, no other text:
{{
  "scores": {{
    "relationship_building": {{"score": 0, "feedback": ""}},
    "patient_perspective": {{"score": 0, "feedback": ""}},
    "providing_structure": {{"score": 0, "feedback": ""}},
    "information_gathering": {{"score": 0, "feedback": ""}},
    "information_giving": {{"score": 0, "feedback": ""}},
    "intelligibility": {{"score": 0, "feedback": ""}},
    "fluency": {{"score": 0, "feedback": ""}},
    "appropriateness_of_language": {{"score": 0, "feedback": ""}},
    "grammar": {{"score": 0, "feedback": ""}}
  }},
  "clinical_average": 0.0,
  "linguistic_average": 0.0,
  "overall_band": 0.0,
  "top_strength": "",
  "top_improvement": "",
  "examiner_summary": ""
}}

RULES:
- clinical_average = mean of criteria 1 to 5
- linguistic_average = mean of criteria 6 to 9
- overall_band = (clinical_average × 0.6) + (linguistic_average × 0.4)
- feedback per criterion = 1 to 2 sentences, cite specific words or moments from the transcript
- top_strength = single most impressive thing the nurse did
- top_improvement = single most important thing to work on
- examiner_summary = exactly 3 sentences, written as an OET examiner would write it
- If no roleplay card was provided, deduct 0.5 from providing_structure and note this in examiner_summary"""

    result = await _call_ai(
        [{"role": "user", "content": scoring_prompt}],
        max_tokens=2000,
        json_mode=True,
    )

    if "scores" in result:
        # Enforce weighted band calculation server-side for reliability
        scores = result.get("scores", {})
        try:
            clinical_scores = [
                scores.get("relationship_building", {}).get("score", 0),
                scores.get("patient_perspective", {}).get("score", 0),
                scores.get("providing_structure", {}).get("score", 0),
                scores.get("information_gathering", {}).get("score", 0),
                scores.get("information_giving", {}).get("score", 0),
            ]
            linguistic_scores = [
                scores.get("intelligibility", {}).get("score", 0),
                scores.get("fluency", {}).get("score", 0),
                scores.get("appropriateness_of_language", {}).get("score", 0),
                scores.get("grammar", {}).get("score", 0),
            ]
            clinical_average = sum(clinical_scores) / len(clinical_scores) if clinical_scores else 0.0
            linguistic_average = sum(linguistic_scores) / len(linguistic_scores) if linguistic_scores else 0.0
            overall_band = round((clinical_average * 0.6) + (linguistic_average * 0.4), 2)

            result["clinical_average"] = round(clinical_average, 2)
            result["linguistic_average"] = round(linguistic_average, 2)
            result["overall_band"] = overall_band
        except Exception:
            pass
        return result

    # Fallback when AI fails to return valid JSON
    return {
        "scores": {c: {"score": 0, "feedback": "Unable to score"} for c in [
            "relationship_building", "patient_perspective", "providing_structure",
            "information_gathering", "information_giving", "intelligibility",
            "fluency", "appropriateness_of_language", "grammar"
        ]},
        "clinical_average": 0.0,
        "linguistic_average": 0.0,
        "overall_band": 0.0,
        "top_strength": "",
        "top_improvement": "",
        "examiner_summary": "Unable to generate summary due to scoring error.",
    }


# ── WRITING SCORING ──────────────────────────────────────────────────

async def score_writing(
    content: str,
    nurse_card: Dict[str, Any],
    scenario_title: str = "",
    supabase=None,
) -> Dict[str, Any]:
    """Score a writing submission using the nurse card's tasks."""
    card = nurse_card
    tasks = card.get("tasks", [])
    tasks_text = "\n".join(f"- {t}" for t in tasks)

    scoring_prompt = f"""You are an OET Writing examiner. Evaluate this nurse's letter.

SCENARIO: {scenario_title}
NURSE'S TASKS:
{tasks_text}

NURSE'S LETTER:
{content}

Score on OET Writing criteria (each 0-6):
1. PURPOSE — Is the purpose clear?
2. CONTENT — All relevant information included?
3. CONCISENESS & CLARITY — Concise, no unnecessary info?
4. GENRE & STYLE — Appropriate letter style?
5. ORGANIZATION — Logical structure and flow?
6. LANGUAGE — Grammar, vocabulary, spelling?

Return ONLY valid JSON:
{{
  "scores": {{
    "purpose": {{"score": 0, "feedback": ""}},
    "content": {{"score": 0, "feedback": ""}},
    "conciseness": {{"score": 0, "feedback": ""}},
    "genre_style": {{"score": 0, "feedback": ""}},
    "organization": {{"score": 0, "feedback": ""}},
    "language": {{"score": 0, "feedback": ""}}
  }},
  "overall_score": 0,
  "estimated_oet_grade": "B",
  "top_strengths": ["", "", ""],
  "top_improvements": ["", "", ""],
  "corrected_version": "<improved version of the letter>"
}}"""

    result = await _call_ai(
        [{"role": "user", "content": scoring_prompt}],
        max_tokens=2000,
        json_mode=True,
    )

    if "scores" in result:
        return result

    return {
        "scores": {c: {"score": 3, "feedback": "Unable to score"} for c in [
            "purpose", "content", "conciseness", "genre_style", "organization", "language"
        ]},
        "overall_score": 3.0,
        "estimated_oet_grade": "C",
        "top_strengths": [],
        "top_improvements": ["Please try again"],
        "corrected_version": content,
    }


# ── GRAMMAR TUTOR ────────────────────────────────────────────────────

async def get_grammar_feedback(
    mistakes: List[str],
    student_level: str = "intermediate",
    supabase=None,
) -> Dict[str, Any]:
    """
    Given a list of grammar mistakes, provide personalized teaching.
    Each mistake gets: what's wrong, the rule, correct version, 3 practice sentences.
    """
    mistakes_text = "\n".join(f"- {m}" for m in mistakes)

    prompt = f"""You are an English grammar tutor for Indian nursing students. The student made these mistakes:

{mistakes_text}

For EACH mistake, provide:
1. What's wrong (in simple terms)
2. The grammar rule (brief, clear)
3. The corrected sentence
4. 3 practice sentences the student can try

Student level: {student_level}

Return ONLY valid JSON:
{{
  "mistakes": [
    {{
      "original": "the mistake",
      "explanation": "what's wrong",
      "rule": "the grammar rule",
      "corrected": "correct version",
      "practice": ["sentence 1", "sentence 2", "sentence 3"]
    }}
  ],
  "general_tips": ["tip 1", "tip 2"]
}}"""

    result = await _call_ai(
        [{"role": "user", "content": prompt}],
        max_tokens=1500,
        json_mode=True,
    )

    if "mistakes" in result:
        return result

    return {
        "mistakes": [],
        "general_tips": ["Please try again — grammar tutor returned an unexpected format"],
    }


# ── PROGRESS COMPARISON ──────────────────────────────────────────────

async def compare_attempts(
    attempt1_feedback: Dict[str, Any],
    attempt2_feedback: Dict[str, Any],
    attempt1_transcript: str,
    attempt2_transcript: str,
    supabase=None,
) -> Dict[str, Any]:
    """Compare two attempts of the same scenario and explain what improved/declined."""
    prompt = f"""You are an OET coach. A student attempted the SAME role-play twice. Compare their performance.

ATTEMPT 1:
Transcript: {attempt1_transcript[:500]}
Scores: {json.dumps(attempt1_feedback.get('scores', {}), indent=2)}

ATTEMPT 2:
Transcript: {attempt2_transcript[:500]}
Scores: {json.dumps(attempt2_feedback.get('scores', {}), indent=2)}

Provide a comparison:
1. What improved and WHY (be specific)
2. What declined or was missed this time and WHY
3. Overall trajectory (improving, same, or worse)
4. Top 3 things to focus on next

Return ONLY valid JSON:
{{
  "improved": ["improvement 1", "improvement 2"],
  "improved_reasons": ["reason 1", "reason 2"],
  "declined": ["decline 1"],
  "declined_reasons": ["reason 1"],
  "overall_trajectory": "improving",
  "next_focus": ["focus 1", "focus 2", "focus 3"]
}}"""

    result = await _call_ai(
        [{"role": "user", "content": prompt}],
        max_tokens=1000,
        json_mode=True,
    )

    if "overall_trajectory" in result:
        return result

    return {
        "improved": ["Unable to compare"],
        "improved_reasons": [""],
        "declined": [],
        "declined_reasons": [],
        "overall_trajectory": "unknown",
        "next_focus": ["Try the session again"],
    }