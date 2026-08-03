"""Coach-agent study plan: weak-area detection + a personalized weekly
plan on top of it (Elite feature). The weak-area detection is plain rule-based
aggregation (deterministic, testable, cheap); only the narrative plan text
is AI-generated, and it degrades to a rule-based fallback if the AI call
fails, so a flaky provider never breaks the feature entirely."""
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.services.ai_scoring import _call_ai, GEMINI_SCORING_PREMIUM_MODEL

logger = logging.getLogger(__name__)

CRITERIA_KEYS = [
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

CRITERIA_LABELS = {
    "empathy": "Empathy",
    "patient_perspective": "Patient's Perspective",
    "providing_structure": "Providing Structure",
    "information_gathering": "Information Gathering",
    "information_giving": "Information Giving",
    "intelligibility": "Intelligibility",
    "fluency": "Fluency",
    "appropriateness_of_language": "Appropriateness of Language",
    "grammar": "Grammar & Expression",
}

# A criterion needs at least this many scored sessions before its average
# is considered meaningful enough to act on -- matches the same threshold
# already used by /scoring/criteria-averages for consistency.
MIN_SESSIONS_FOR_CRITERION = 3


def compute_criteria_averages(feedback_rows: List[Optional[str]]) -> Dict[str, Optional[float]]:
    """feedback_rows: the raw `feedback` JSON string (or None) from each
    submissions row. Order doesn't matter -- this is a plain average."""
    accumulators = {k: {"sum": 0.0, "count": 0} for k in CRITERIA_KEYS}

    for raw in feedback_rows:
        try:
            feedback = json.loads(raw or "{}")
        except json.JSONDecodeError:
            continue
        scores = feedback.get("scores", {}) or {}

        empathy_score = scores.get("empathy", {}).get("score")
        if empathy_score is None:
            empathy_score = scores.get("relationship_building", {}).get("score")
        if empathy_score is not None:
            accumulators["empathy"]["sum"] += empathy_score
            accumulators["empathy"]["count"] += 1

        for key in CRITERIA_KEYS[1:]:
            score = scores.get(key, {}).get("score")
            if score is not None:
                accumulators[key]["sum"] += score
                accumulators[key]["count"] += 1

    result: Dict[str, Optional[float]] = {}
    for key, acc in accumulators.items():
        if acc["count"] >= MIN_SESSIONS_FOR_CRITERION:
            result[key] = round(acc["sum"] / acc["count"], 2)
        else:
            result[key] = None
    return result


def identify_weak_criteria(criteria_averages: Dict[str, Optional[float]], top_n: int = 3) -> List[str]:
    """Lowest-scoring criteria with enough data to be meaningful, worst first."""
    scored = [(k, v) for k, v in criteria_averages.items() if v is not None]
    scored.sort(key=lambda kv: kv[1])
    return [k for k, _ in scored[:top_n]]


def weeks_until(now: datetime, exam_date: datetime) -> int:
    delta_days = (exam_date - now).days
    return max(0, delta_days // 7)


def compute_streaks(submission_dates: List[str]) -> Tuple[int, int]:
    """submission_dates: created_at values (or their date portion) from every
    submission a user has ever made -- duplicates and full timestamps are fine.
    Returns (current_streak, longest_streak) in days. current_streak is 0
    unless the streak includes today (UTC)."""
    unique_days = {d[:10] for d in submission_dates if d}
    if not unique_days:
        return 0, 0

    day_objs = sorted(date.fromisoformat(d) for d in unique_days)
    day_set = set(day_objs)

    today = datetime.now(timezone.utc).date()
    current_streak = 0
    cursor = today
    while cursor in day_set:
        current_streak += 1
        cursor -= timedelta(days=1)

    longest_streak = 0
    running = 0
    prev: Optional[date] = None
    for d in day_objs:
        running = running + 1 if prev is not None and (d - prev).days == 1 else 1
        longest_streak = max(longest_streak, running)
        prev = d

    return current_streak, longest_streak


def _fallback_plan(weak_labels: List[str], scenario_titles: List[str]) -> Dict[str, str]:
    return {
        "weekly_focus": (
            f"Focus on {weak_labels[0]}" if weak_labels else "Keep building your session history"
        ),
        "why_it_matters": (
            "This is currently your lowest-scoring criterion across recent sessions."
            if weak_labels
            else "Complete a few more sessions to unlock weak-area detection."
        ),
        "action_steps": (
            [f"Practice the recommended scenario: {scenario_titles[0]}"] if scenario_titles else []
        ),
        "pacing_note": "",
    }


async def build_study_plan(
    *,
    weak_criteria: List[str],
    total_sessions_scored: int,
    recommended_scenarios: List[Dict[str, Any]],
    target_band: Optional[str],
    days_per_week: Optional[int],
    weeks_to_exam: Optional[int],
) -> Dict[str, Any]:
    """AI-generated narrative plan layered on top of the rule-based weak-area
    detection above. Falls back to a plain rule-based plan if the AI call
    fails or returns an unexpected shape."""
    weak_labels = [CRITERIA_LABELS.get(k, k) for k in weak_criteria]
    scenario_titles = [s["title"] for s in recommended_scenarios]

    prompt = f"""You are an OET Speaking coach building a personalized weekly study plan for a nursing student.

STUDENT DATA:
- Sessions scored so far: {total_sessions_scored}
- Target band: {target_band or "not set"}
- Weeks until exam: {weeks_to_exam if weeks_to_exam is not None else "no exam date set"}
- Practice days per week goal: {days_per_week or "not set"}
- Weakest criteria (worst first): {", ".join(weak_labels) if weak_labels else "not enough data yet"}
- Recommended next scenarios: {", ".join(scenario_titles) if scenario_titles else "none available"}

Write a short, specific, motivating weekly study plan. Return ONLY this JSON:
{{
  "weekly_focus": "<1 sentence: this week's single biggest priority>",
  "why_it_matters": "<1-2 sentences explaining why this specific weak area matters for their target band>",
  "action_steps": ["<specific action 1>", "<specific action 2>", "<specific action 3>"],
  "pacing_note": "<1 sentence on whether they're on track for their exam date given sessions so far, or encouragement if no exam date is set>"
}}

Be concrete -- reference the actual weak criteria and scenario names above. Do NOT use generic filler like "keep practicing" or "you're doing great"."""

    try:
        result = await _call_ai(
            [{"role": "user", "content": prompt}],
            max_tokens=500,
            json_mode=True,
            model=GEMINI_SCORING_PREMIUM_MODEL,
        )
    except Exception as e:
        logger.warning("[STUDY_PLAN_AI_FAILURE] error=%s", str(e)[:300])
        return _fallback_plan(weak_labels, scenario_titles)

    if "weekly_focus" not in result:
        logger.warning("[STUDY_PLAN_AI_FAILURE] unexpected result=%s", str(result)[:300])
        return _fallback_plan(weak_labels, scenario_titles)

    return {
        "weekly_focus": result.get("weekly_focus", ""),
        "why_it_matters": result.get("why_it_matters", ""),
        "action_steps": result.get("action_steps") or [],
        "pacing_note": result.get("pacing_note", ""),
    }
