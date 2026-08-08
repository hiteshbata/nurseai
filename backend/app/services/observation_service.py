"""ObservationService: validates and normalizes raw per-criterion scores
before they reach the Skill Graph. Generic across modules -- Skill Graph
(skill_graph.py) owns aggregation only (EMA upsert into user_skill_stats);
this owns validation/normalization for whichever module calls it. Speaking
is the first caller (Sprint 1, ADR-008); the module-based interface exists
so Reading/Listening/Writing can call the same function later without a
redesign.
"""
from typing import Any, Dict

MIN_SCORE = 0
MAX_SCORE = 6


def validate_and_normalize(module: str, raw_scores: Dict[str, Any]) -> Dict[str, float]:
    """Keep only numeric, non-bool scores on the shared 0-6 OET band scale
    (see skill_graph.py's module docstring) whose tag actually belongs to
    `module` (e.g. "speaking:fluency" for module="speaking") -- guards
    against a wrong-module tag leaking in, not just a bad score."""
    if not module:
        return {}
    prefix = f"{module}:"
    return {
        tag: round(float(score), 2)
        for tag, score in raw_scores.items()
        if tag.startswith(prefix)
        and isinstance(score, (int, float))
        and not isinstance(score, bool)
        and MIN_SCORE <= score <= MAX_SCORE
    }
