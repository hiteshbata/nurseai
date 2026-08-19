"""E2.1 Mistake Engine -- Listening only.

An evidence store, not a second Learner Brain: it writes one row per graded
question to listening_mistake_events, strictly AFTER grading, submissions
persistence, and skill_graph.record_skill_observations have already
succeeded (see listening.py submit_test). Nothing reads from this table yet.

Best-effort like record_skill_observations (skill_graph.py): a failure here
must never turn an already-successful submission into a 500, so every
failure is caught and logged, never raised to the caller.
"""
import logging
from typing import Any, Dict, List, Optional

from app.core.supabase import get_supabase
from app.core.threading import run_sync

logger = logging.getLogger(__name__)


def _record_sync(
    user_id: str,
    submission_id: Optional[int],
    test_id: int,
    test_version_id: Optional[int],
    results: List[Dict[str, Any]],
    section_id_by_qid: Dict[int, Optional[int]],
    part_by_qid: Dict[int, Optional[str]],
    difficulty_by_section: Dict[int, Optional[str]],
    question_type_by_qid: Dict[int, str],
) -> None:
    supabase = get_supabase()
    qids = [r["questionId"] for r in results]

    # Prior-event count per question, for informational attempt numbering
    # (item 12) -- one batched query rather than N.
    prior = supabase.table("listening_mistake_events").select("question_id") \
        .eq("user_id", user_id).in_("question_id", qids).execute()
    prior_counts: Dict[int, int] = {}
    for row in prior.data:
        prior_counts[row["question_id"]] = prior_counts.get(row["question_id"], 0) + 1

    rows = []
    for r in results:
        qid = r["questionId"]
        part = part_by_qid.get(qid)
        if part not in ("A", "B", "C"):
            # Shouldn't happen (every graded question belongs to a part), but
            # this is an evidence log, not the grading path -- skip rather
            # than fail the whole batch over one malformed lookup.
            logger.warning("[LISTENING_MISTAKE_ENGINE_SKIP] user_id=%s question_id=%s reason=missing_part", user_id, qid)
            continue
        section_id = section_id_by_qid.get(qid)
        rows.append({
            "user_id": user_id,
            "submission_id": submission_id,
            "question_id": qid,
            "test_id": test_id,
            "test_version_id": test_version_id,
            "section_id": section_id,
            "part": part,
            "question_type": question_type_by_qid.get(qid) or "mcq",
            # Existing skill-graph tags only (listening:A/B/C) -- no new
            # question-level skill taxonomy (item 11).
            "skill_tag": f"listening:{part}",
            "difficulty": difficulty_by_section.get(section_id),
            "selected_option": r.get("selected"),
            "correct_answer": r.get("correct_answer"),
            "is_correct": bool(r.get("is_correct")),
            "attempt_number": prior_counts.get(qid, 0) + 1,
        })

    if rows:
        supabase.table("listening_mistake_events").insert(rows).execute()


async def record_listening_mistake_events(
    user_id: str,
    submission_id: Optional[int],
    test_id: int,
    test_version_id: Optional[int],
    results: List[Dict[str, Any]],
    section_id_by_qid: Dict[int, Optional[int]],
    part_by_qid: Dict[int, Optional[str]],
    difficulty_by_section: Dict[int, Optional[str]],
    question_type_by_qid: Dict[int, str],
) -> None:
    if not results:
        return
    try:
        await run_sync(
            _record_sync, user_id, submission_id, test_id, test_version_id,
            results, section_id_by_qid, part_by_qid, difficulty_by_section, question_type_by_qid,
        )
    except Exception as e:
        logger.warning(
            "[LISTENING_MISTAKE_ENGINE_FAILED] user_id=%s submission_id=%s error=%s",
            user_id, submission_id, str(e)[:300],
        )
