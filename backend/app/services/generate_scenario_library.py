"""Batch-generate additional OET speaking scenarios via AI to grow the
scenario library toward 100+, with automated validation as a quality gate.

Not run automatically -- see scripts/generate_scenarios.py for the CLI
entrypoint you run yourself. This writes real rows to Supabase and makes
real (cheap) AI calls, so it's a deliberate, manual step, not something
that runs on app startup like seed_scenarios().

A human should still spot-check a sample of the output before fully
trusting it in production -- automated validation catches structural
problems (missing fields, too few tasks) but not subtle clinical or
tone issues, same as any AI-generated content shipped to real users.
"""
import logging
from typing import Any, Dict, List, Optional

from app.core.supabase import get_supabase
from app.services.ai_scoring import _call_ai

logger = logging.getLogger(__name__)

SPECIALTIES = [
    "general",
    "surgical",
    "paediatric",
    "aged_care",
    "mental_health",
    "ICU",
    "emergency",
    "community",
    "oncology",
    "maternity",
]

DIFFICULTIES = ["easy", "medium", "hard"]

SCORING_CRITERIA = {
    "criteria": [
        "empathy",
        "patient_perspective",
        "providing_structure",
        "information_gathering",
        "information_giving",
        "intelligibility",
        "fluency",
        "appropriateness_of_language",
        "grammar",
    ]
}


def _speaking_prompt(specialty: str, difficulty: str, avoid_titles: List[str]) -> str:
    avoid_text = ""
    if avoid_titles:
        # Cap the list so the prompt doesn't grow unbounded as the library
        # fills up -- recent titles are the most useful ones to avoid
        # repeating anyway (this run's own output so far).
        recent = avoid_titles[-30:]
        avoid_text = "\nDo NOT reuse any of these existing titles or very similar premises:\n" + "\n".join(
            f"- {t}" for t in recent
        )

    return f"""You are an OET exam content creator. Generate a realistic OET Speaking roleplay card for a nursing student.

REQUIREMENTS:
- Specialty: {specialty}
- Difficulty: {difficulty}
- Must be clinically realistic and specific (real conditions, real ward context, real details)
- Tasks must follow real OET format (5-6 specific, actionable tasks)
- Patient must have a clear emotional state and believable background
- Vary patient names, ages, and specific conditions across scenarios{avoid_text}

Return ONLY this JSON, no other text:
{{
  "title": "short scenario title",
  "setting": "ward/clinic description and patient context paragraph (2-3 sentences)",
  "difficulty": "{difficulty}",
  "nurse_card": {{
    "role": "You are speaking to a [age]-year-old [gender] who [condition/situation]. [1 sentence on emotional state].",
    "tasks": ["Task 1", "Task 2", "Task 3", "Task 4", "Task 5"]
  }},
  "interlocutor_card": {{
    "patient_name": "First name only",
    "age": 35,
    "condition": "presenting condition",
    "mood": "anxious|worried|confused|resistant|cooperative|frustrated|relieved",
    "background": "2 sentence patient background",
    "emotional_triggers": ["trigger 1", "trigger 2", "trigger 3"],
    "questions_to_ask": ["question 1", "question 2", "question 3"],
    "information_to_withhold": ["info to withhold 1", "info to withhold 2"],
    "instructions_for_ai": "detailed persona description for how the AI should play this patient"
  }}
}}"""


def validate_scenario(data: Any) -> List[str]:
    """Returns a list of validation problems; an empty list means it passes.
    Structural checks only (matches ai_scoring.get_patient_response's actual
    field reads) -- this can't judge clinical accuracy or writing quality."""
    errors: List[str] = []
    if not isinstance(data, dict):
        return ["not a JSON object"]

    if not data.get("title") or len(data["title"]) < 5:
        errors.append("missing or too-short title")
    if not data.get("setting") or len(data["setting"]) < 40:
        errors.append("missing or too-short setting")

    nurse_card = data.get("nurse_card")
    if not isinstance(nurse_card, dict):
        return errors + ["missing nurse_card"]
    if not nurse_card.get("role"):
        errors.append("missing nurse_card.role")
    tasks = nurse_card.get("tasks") or []
    if not (4 <= len(tasks) <= 6):
        errors.append(f"nurse_card.tasks has {len(tasks)} items, expected 4-6")

    inter = data.get("interlocutor_card")
    if not isinstance(inter, dict):
        return errors + ["missing interlocutor_card"]
    for field in ("patient_name", "condition", "mood", "background", "instructions_for_ai"):
        if not inter.get(field):
            errors.append(f"missing interlocutor_card.{field}")
    if len(inter.get("emotional_triggers") or []) < 2:
        errors.append("interlocutor_card.emotional_triggers needs at least 2 items")
    if len(inter.get("questions_to_ask") or []) < 2:
        errors.append("interlocutor_card.questions_to_ask needs at least 2 items")
    if len(inter.get("information_to_withhold") or []) < 1:
        errors.append("interlocutor_card.information_to_withhold needs at least 1 item")

    return errors


async def generate_one_scenario(
    specialty: str, difficulty: str, avoid_titles: List[str], max_attempts: int = 2
) -> Optional[Dict[str, Any]]:
    for attempt in range(max_attempts):
        prompt = _speaking_prompt(specialty, difficulty, avoid_titles)
        result = await _call_ai(
            [{"role": "user", "content": prompt}],
            purpose="scenario_library_generation",
            max_tokens=1200,
            json_mode=True,
        )
        errors = validate_scenario(result)
        if not errors:
            return result
        logger.warning(
            "[SCENARIO_GEN] attempt %d failed validation for %s/%s: %s",
            attempt + 1, specialty, difficulty, errors,
        )
    return None


async def generate_speaking_library(
    specialties: List[str] = SPECIALTIES,
    difficulties: List[str] = DIFFICULTIES,
    per_cell: int = 3,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Generates per_cell scenarios for every (specialty, difficulty) pair.
    Idempotent by title, like seed_scenarios() -- safe to re-run; it will
    just skip anything whose title collides with existing content."""
    supabase = get_supabase()
    existing = supabase.table("scenarios").select("title").eq("module", "speaking").execute()
    existing_titles = [r["title"] for r in (existing.data or [])]

    created_titles: List[str] = []
    failed = 0

    for specialty in specialties:
        for difficulty in difficulties:
            for _ in range(per_cell):
                scenario = await generate_one_scenario(specialty, difficulty, existing_titles)
                if not scenario or scenario["title"] in existing_titles:
                    failed += 1
                    continue

                existing_titles.append(scenario["title"])
                created_titles.append(scenario["title"])

                if not dry_run:
                    supabase.table("scenarios").insert({
                        "module": "speaking",
                        "title": scenario["title"],
                        "setting": scenario["setting"],
                        "difficulty": scenario["difficulty"],
                        "nurse_card": scenario["nurse_card"],
                        "interlocutor_card": scenario["interlocutor_card"],
                        "scoring_criteria": SCORING_CRITERIA,
                        "specialty": specialty,
                        "is_active": True,
                    }).execute()

                logger.info("[SCENARIO_GEN] created: %s (%s/%s)", scenario["title"], specialty, difficulty)

    return {"created": len(created_titles), "failed": failed, "titles": created_titles}
