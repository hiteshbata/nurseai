"""E2.4.4: pure Learner Brain -> Knowledge Graph tag resolver.

resolve_skill_id(tag) turns a legacy colon-tag skill_graph.py already writes
(user_skill_stats.skill_tag) into the canonical skills.skill_id from the
E2.4.1 registry (app/services/skill_registry.py), via the exact
LEGACY_TAG_TO_CODE dict that registry already defines -- exact lookup only,
no string transform, no prefix/fuzzy matching, no new skill ever created
here. An unknown or unmapped tag logs a warning and returns None; callers
(the bridge backfill, reconciliation, content lookup) must never fail or
invent a registry row because of it.

technique.scanning and reading.skill.scanning are different SEED_SKILLS
codes for different legacy tags ("technique:scanning" vs
"reading:skill:scanning") -- the dict keeps them distinct automatically,
same as skill_registry.py itself.

Caches the ~44-row skills table in-process (code -> skill_id) since it never
changes at runtime after a migration; _reset_cache_for_tests() clears/seeds
it between tests.
"""
import logging
from typing import Dict, Optional
from uuid import UUID

from app.core.supabase import get_supabase
from app.services.skill_registry import LEGACY_TAG_TO_CODE

logger = logging.getLogger(__name__)

# code -> legacy_tag, reverse of LEGACY_TAG_TO_CODE. Well-defined because
# SEED_SKILLS codes are unique (see test_skill_registry.py::test_codes_are_unique).
CODE_TO_LEGACY_TAG: Dict[str, str] = {code: tag for tag, code in LEGACY_TAG_TO_CODE.items()}

_code_to_skill_id_cache: Optional[Dict[str, str]] = None


def _skills_cache() -> Dict[str, str]:
    global _code_to_skill_id_cache
    if _code_to_skill_id_cache is None:
        rows = get_supabase().table("skills").select("code, skill_id").execute().data or []
        _code_to_skill_id_cache = {row["code"]: row["skill_id"] for row in rows}
    return _code_to_skill_id_cache


def _reset_cache_for_tests(rows: Optional[Dict[str, str]] = None) -> None:
    """Test-only. rows=None clears the cache back to lazy-load-on-next-call;
    a dict force-seeds it (code -> skill_id) without touching Supabase."""
    global _code_to_skill_id_cache
    _code_to_skill_id_cache = rows


def resolve_skill_id(tag: str) -> Optional[UUID]:
    """Legacy skill_tag -> canonical skills.skill_id, or None. Exact dict
    match only -- deterministic, never guesses. `tag` not in
    LEGACY_TAG_TO_CODE at all is logged and treated identically to a tag
    whose code has no live skills row (taxonomy/data drift): both return
    None rather than fabricating a skill."""
    code = LEGACY_TAG_TO_CODE.get(tag)
    if code is None:
        logger.warning("[SKILL_BRIDGE] unknown legacy skill_tag, no registry entry: tag=%r", tag)
        return None

    skill_id = _skills_cache().get(code)
    if skill_id is None:
        logger.warning("[SKILL_BRIDGE] legacy tag mapped to a code with no skills row: tag=%r code=%r", tag, code)
        return None
    return UUID(skill_id)


def code_to_legacy_tag(code: str) -> Optional[str]:
    return CODE_TO_LEGACY_TAG.get(code)


if __name__ == "__main__":
    # ponytail: one runnable check -- known tag resolves, unknown tag doesn't, round-trip holds.
    _reset_cache_for_tests({"reading.part.a": "11111111-1111-1111-1111-111111111111"})
    assert resolve_skill_id("reading:A") == UUID("11111111-1111-1111-1111-111111111111")
    assert resolve_skill_id("not:a:real:tag") is None
    assert resolve_skill_id("listening:A") is None  # in the registry, but not in this seeded cache
    assert code_to_legacy_tag("reading.part.a") == "reading:A"
    assert code_to_legacy_tag("no.such.code") is None
    _reset_cache_for_tests(None)
    print("OK")
