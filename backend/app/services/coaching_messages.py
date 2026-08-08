"""Config-driven learner-facing coaching copy (Sprint 1, ADR-008). Templates
are picked by confidence tier ("history" vs "session") rather than branched
inline with if/else, so a new tier -- or a future module's own copy -- is a
dict entry, not new conditionals. `{label}` and `{attempts}` are the only
placeholders callers need to supply.

Wording is deliberately module-agnostic ("area", not "criterion" or
"scenario") -- Speaking (Sprint 1) and Reading (Sprint 2) share these dicts
unmodified; a module-specific noun would have forced a fork.
"""
from typing import Dict

RECOMMENDATION_REASON: Dict[str, str] = {
    "history": "{label} is your weakest area across recent sessions, not just today.",
    "session": "{label} was your lowest-scoring area today -- not enough history yet to confirm a pattern.",
}

ACTIONABLE_IMPROVEMENT: Dict[str, str] = {
    "history": "Spend your next practice session focused specifically on {label} -- it keeps coming up as your lowest-scoring area across recent sessions.",
    "session": "Spend your next practice session focused specifically on {label} -- it was your lowest-scoring area today.",
}

CONFIDENCE_MESSAGE: Dict[str, str] = {
    "history": "Based on your last {attempts} sessions -- a consistent pattern worth prioritizing.",
    "session": "Based on today's session alone -- a couple more will sharpen this picture.",
}
