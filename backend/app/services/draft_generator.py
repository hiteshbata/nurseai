"""AI Draft Generator (RC3.2): builds a prompt, calls the shared
content_draft_generation purpose, validates the response, and returns an
unpersisted draft. Never writes to production content tables and never
publishes -- app/services/draft_store.py is the only thing this sprint is
allowed to persist to.
"""
import logging
from typing import Any, Dict, List, Optional

from app.core.supabase import get_supabase
from app.services import ai_registry
from app.services import prompt_builder
from app.services.ai_scoring import _call_ai

logger = logging.getLogger(__name__)

PURPOSE = "content_draft_generation"

# Required top-level keys per module, checked after JSON parsing succeeds.
_REQUIRED_FIELDS: Dict[str, List[str]] = {
    "speaking": ["title", "setting", "nurse_card", "interlocutor_card"],
    "reading": ["title", "body", "questions"],
    "listening": ["title", "transcript", "questions"],
    "writing": ["title", "case_notes", "task"],
    "vocab": ["topic", "items"],
    "grammar": ["topic", "explanation"],
}

# Fields that must be a non-empty list, on top of the presence check above.
_REQUIRED_NONEMPTY_LISTS: Dict[str, List[str]] = {
    "reading": ["questions"],
    "listening": ["transcript", "questions"],
    "vocab": ["items"],
}

# module -> (production table, extra eq filters) for the best-effort
# duplicate-title check. Grammar/vocab have no production content table
# (see content_studio.py) so duplicate checking is skipped for them --
# this only affects the warning, never blocks generation or saving.
_DUPLICATE_CHECK_TABLE = {
    "speaking": ("scenarios", {"module": "speaking"}),
    "writing": ("scenarios", {"module": "writing"}),
    "reading": ("reading_passages", {}),
    "listening": ("listening_sections", {}),
}

_TITLE_FIELD = {
    "speaking": "title", "reading": "title", "listening": "title", "writing": "title",
    "vocab": "topic", "grammar": "topic",
}

# Reading (full passage + questions), Listening (full transcript + questions),
# and Grammar (explanation + practice questions) routinely exceed the default
# budget and got cut off mid-JSON -- confirmed via finish_reason=MAX_TOKENS on
# the raw AI response. Speaking/Writing/Vocab's schemas fit comfortably under
# the default and are left untouched.
_MAX_TOKENS_OVERRIDE = {"reading": 6000, "listening": 6000, "grammar": 6000}
_DEFAULT_MAX_TOKENS = 3000


class DraftGenerationError(Exception):
    """A friendly, user-facing generation failure (AI outage, malformed
    response, empty response). Caught by the router and returned as a
    per-item error instead of a 500."""


def _validate(module: str, content: Dict[str, Any]) -> List[str]:
    required = _REQUIRED_FIELDS.get(module, [])
    missing = [f for f in required if not content.get(f)]
    if missing:
        raise DraftGenerationError(f"AI response is missing required field(s): {', '.join(missing)}")

    for field in _REQUIRED_NONEMPTY_LISTS.get(module, []):
        value = content.get(field)
        if not isinstance(value, list) or not value:
            raise DraftGenerationError(f"AI response has an empty '{field}' list")

    return []


def _check_duplicate_title(module: str, title: str) -> Optional[str]:
    mapping = _DUPLICATE_CHECK_TABLE.get(module)
    if not mapping or not title:
        return None
    table, filters = mapping
    supabase = get_supabase()
    query = supabase.table(table).select("id").ilike("title", title.strip())
    for col, val in filters.items():
        query = query.eq(col, val)
    existing = query.limit(1).execute().data
    if existing:
        return f'A {module} item titled "{title}" already exists in production content -- consider a different topic or angle.'
    return None


async def generate_draft(
    module: str,
    difficulty: str,
    specialty: str,
    topic: str,
    objectives: Optional[str] = None,
    instructions: Optional[str] = None,
    admin_user_id: str = "",
) -> Dict[str, Any]:
    """Generate one draft. Returns a dict ready for the Preview UI / Save
    Draft call. Raises DraftGenerationError on any AI or validation failure
    -- callers should catch it and surface result.error rather than a 500,
    so one bad draft in a batch doesn't fail the whole request."""
    system_prompt, user_prompt = prompt_builder.build_prompt(module, difficulty, specialty, topic, objectives, instructions)

    try:
        cfg = await ai_registry.get_model_config(PURPOSE)
        model_used = f"{cfg.provider}/{cfg.model_name}"
    except ai_registry.PurposeNotConfigured:
        model_used = None

    result = await _call_ai(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        purpose=PURPOSE,
        max_tokens=_MAX_TOKENS_OVERRIDE.get(module, _DEFAULT_MAX_TOKENS),
        json_mode=True,
        temperature=0.4,
        user_id=admin_user_id,
        timeout=90.0,
    )
    if result.get("provider_failure"):
        raise DraftGenerationError("The AI service is temporarily unavailable. Please try again.")
    if "raw_feedback" in result:
        logger.warning("[draft_generator] JSON parse failed | module=%s raw_head=%s", module, str(result["raw_feedback"])[:500])
        raise DraftGenerationError("The AI response could not be read as valid content. Please try again.")

    content = {k: v for k, v in result.items() if k != "finish_reason"}
    if not content:
        raise DraftGenerationError("The AI returned an empty response.")

    warnings = _validate(module, content)

    title = str(content.get(_TITLE_FIELD.get(module, "title"), "")).strip()
    dup_warning = _check_duplicate_title(module, title)
    if dup_warning:
        warnings.append(dup_warning)

    return {
        "generated_content": content,
        "metadata": {
            "difficulty": difficulty,
            "specialty": specialty,
            "topic": topic,
            "objectives": objectives,
            "instructions": instructions,
        },
        "prompt": {"system_prompt": system_prompt, "user_prompt": user_prompt},
        "validation_warnings": warnings,
        "ai_title": title or None,
        "model_used": model_used,
    }
