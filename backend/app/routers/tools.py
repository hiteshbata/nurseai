"""Public, unauthenticated marketing tools (no login required) -- the
counterpart to the free client-side OET score calculator. This one calls the
AI, so unlike the calculator it needs IP rate-limiting to bound cost/abuse."""
import asyncio
import logging
from typing import Dict, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.routers.auth import _client_ip
from app.core.captcha import verify_captcha
from app.core.rate_limit import SlidingWindowRateLimiter
from app.services.ai_scoring import _call_ai, GEMINI_SCORING_FREE_MODEL

logger = logging.getLogger(__name__)

_AI_CALL_TIMEOUT_SECONDS = 15

router = APIRouter(prefix="/tools", tags=["tools"])

_study_plan_rate_limiter = SlidingWindowRateLimiter(5, 3600, name="tools:study-plan")

MODULES = ["listening", "reading", "writing", "speaking"]
MODULE_LABELS = {
    "listening": "Listening",
    "reading": "Reading",
    "writing": "Writing",
    "speaking": "Speaking",
}


class ModuleScores(BaseModel):
    listening: int = Field(ge=0, le=500)
    reading: int = Field(ge=0, le=500)
    writing: int = Field(ge=0, le=500)
    speaking: int = Field(ge=0, le=500)

    def as_dict(self) -> Dict[str, int]:
        return {m: getattr(self, m) for m in MODULES}


class StudyPlanRequest(BaseModel):
    scores: ModuleScores
    target_requirements: ModuleScores
    target_regulator_name: str = Field(min_length=1, max_length=120)
    weeks_until_exam: Optional[int] = Field(default=None, ge=0, le=104)
    hours_per_week: Optional[int] = Field(default=None, ge=1, le=100)
    captcha_token: Optional[str] = None


def _weakest_module(scores: Dict[str, int], target: Dict[str, int]) -> Optional[Tuple[str, int]]:
    gaps = {m: target[m] - scores[m] for m in MODULES if target[m] > scores[m]}
    if not gaps:
        return None
    module = max(gaps, key=gaps.get)
    return module, gaps[module]


# Deterministic fallback if the AI call fails -- generic per-module advice,
# same spirit as frontend/src/lib/oetScoring.ts FOUR_WEEK_PLANS but this is
# the backend/no-JS path so it's written directly rather than shared.
_FALLBACK_ACTION_STEPS = {
    "listening": ["Drill Part A note-taking speed on consultation extracts", "Time-box Part B and C under real exam pressure"],
    "reading": ["Practise skimming Part A for numbers, dosages, and key terms fast", "Build vocabulary from the specific texts you get wrong"],
    "writing": ["Study 2-3 sample Grade A/B letters against the mark scheme", "Practise case-note selection -- irrelevant info is the biggest score-killer"],
    "speaking": ["Practise role-plays out loud daily -- it's a performance skill", "Record yourself and compare against empathy, structure, and information-gathering"],
}


def _fallback_plan(weakest: Optional[Tuple[str, int]], num_weeks: int) -> Dict:
    module = weakest[0] if weakest else "speaking"
    label = MODULE_LABELS[module]
    steps = _FALLBACK_ACTION_STEPS[module]
    return {
        "summary": f"Focus your next {num_weeks} weeks on {label} -- it's the sub-test furthest from your target.",
        "weeks": [
            {
                "title": f"Week {i + 1}",
                "focus": f"{label} fundamentals" if i == 0 else f"{label} timed practice",
                "action_steps": steps,
            }
            for i in range(num_weeks)
        ],
        "pacing_note": "",
    }


@router.post("/study-plan")
async def generate_study_plan(body: StudyPlanRequest, request: Request):
    client_ip = _client_ip(request)
    if _study_plan_rate_limiter.is_rate_limited(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests -- please try again in a while.")
    if not await verify_captcha(body.captcha_token, client_ip):
        raise HTTPException(status_code=400, detail="Captcha verification failed.")

    scores = body.scores.as_dict()
    target = body.target_requirements.as_dict()
    weakest = _weakest_module(scores, target)

    num_weeks = min(max(body.weeks_until_exam, 2), 6) if body.weeks_until_exam else 4

    if weakest is None:
        return {
            "weakest_module": None,
            "gap": 0,
            "summary": f"Your scores already meet {body.target_regulator_name}'s requirement on every sub-test.",
            "weeks": [],
            "pacing_note": "",
        }

    module, gap = weakest
    weak_label = MODULE_LABELS[module]

    prompt = f"""You are an OET coach building a personalized {num_weeks}-week study plan for a nursing candidate.

CANDIDATE DATA:
- Current scores (0-500): Listening {scores['listening']}, Reading {scores['reading']}, Writing {scores['writing']}, Speaking {scores['speaking']}
- Target regulator: {body.target_regulator_name}
- Target requirement (0-500): Listening {target['listening']}, Reading {target['reading']}, Writing {target['writing']}, Speaking {target['speaking']}
- Weakest sub-test: {weak_label}, {gap} points below target
- Hours available per week: {body.hours_per_week or "not specified"}
- Weeks until exam: {body.weeks_until_exam if body.weeks_until_exam is not None else "not specified"}

Write a specific, motivating {num_weeks}-week plan prioritizing {weak_label} first, then the other sub-tests below target. Return ONLY this JSON:
{{
  "summary": "<1-2 sentences: the overall strategy>",
  "weeks": [
    {{"title": "Week 1", "focus": "<this week's single focus>", "action_steps": ["<specific action>", "<specific action>", "<specific action>"]}}
    ... exactly {num_weeks} week objects ...
  ],
  "pacing_note": "<1 sentence on whether {body.hours_per_week or 'their available'} hours/week is realistic to close a {gap}-point gap by the exam, or general encouragement if no exam date given>"
}}

Be concrete -- reference the actual sub-test names and point gaps above. Do NOT use generic filler like "keep practicing" or "you're doing great"."""

    try:
        result = await asyncio.wait_for(
            _call_ai(
                [{"role": "user", "content": prompt}],
                max_tokens=900,
                json_mode=True,
                model=GEMINI_SCORING_FREE_MODEL,
            ),
            timeout=_AI_CALL_TIMEOUT_SECONDS,
        )
        weeks = result.get("weeks")
        if not isinstance(weeks, list) or not weeks:
            raise ValueError("unexpected AI response shape")
        plan = {
            "summary": result.get("summary", ""),
            "weeks": weeks,
            "pacing_note": result.get("pacing_note", ""),
        }
    except Exception as e:
        logger.warning("[STUDY_PLAN_TOOL_AI_FAILURE] error=%s", str(e)[:300])
        plan = _fallback_plan(weakest, num_weeks)

    return {"weakest_module": module, "gap": gap, **plan}
