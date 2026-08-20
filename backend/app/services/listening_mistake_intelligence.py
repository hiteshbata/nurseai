"""E2.2 -- Mistake Intelligence (read-only classifier), Listening only.

Pure functions over plain event-row dicts pulled from listening_mistake_events
(E2.1). This is a read-only lens on top of that evidence log -- it writes
nothing back to listening_mistake_events, skill_graph, or user_skill_stats,
and it introduces no new score/EMA (skill_graph.py already owns that).

Row `id` is the authoritative ordering key throughout. `created_at` can tie
(same-millisecond writes) and `attempt_number` is informational-only (see
listening_mistake_engine.py), so neither is safe for determining sequence --
only the monotonic `id` is.
"""
from typing import Any, Dict, List

from supabase import Client

from app.core.threading import run_sync

PERSISTENT_MISTAKE_MIN_WRONG = 3
REPEATED_MISTAKE_MIN_WRONG = 2
PART_PATTERN_MIN_EVENTS = 2
PARTS = ("A", "B", "C")


def classify_mistakes(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = sorted(rows, key=lambda r: r["id"])

    by_question: Dict[Any, List[Dict[str, Any]]] = {}
    for row in rows:
        by_question.setdefault(row["question_id"], []).append(row)

    recent_mistakes = []
    corrected_mistakes = []
    repeated_mistakes = []
    persistent_mistakes = []

    for question_id, events in by_question.items():
        latest = events[-1]
        wrong_events = [e for e in events if not e["is_correct"]]
        wrong_count = len(wrong_events)
        part = latest["part"]

        if not latest["is_correct"]:
            recent_mistakes.append({
                "question_id": question_id,
                "part": part,
                "wrong_at": latest.get("created_at"),
                "selected_option": latest.get("selected_option"),
                "correct_answer": latest.get("correct_answer"),
            })
        elif wrong_count >= 1:
            corrected_mistakes.append({
                "question_id": question_id,
                "part": part,
                "wrong_count": wrong_count,
                "corrected_at": latest.get("created_at"),
            })

        if wrong_count >= REPEATED_MISTAKE_MIN_WRONG:
            repeated_mistakes.append({
                "question_id": question_id,
                "part": part,
                "wrong_count": wrong_count,
            })

        if wrong_count >= PERSISTENT_MISTAKE_MIN_WRONG and not latest["is_correct"]:
            persistent_mistakes.append({
                "question_id": question_id,
                "part": part,
                "wrong_count": wrong_count,
                "last_wrong_at": wrong_events[-1].get("created_at"),
            })

    part_patterns: Dict[str, Dict[str, Any]] = {}
    for part in PARTS:
        part_events = [r for r in rows if r["part"] == part]
        total = len(part_events)
        if total < PART_PATTERN_MIN_EVENTS:
            continue
        wrong = sum(1 for r in part_events if not r["is_correct"])
        part_patterns[part] = {"wrong": wrong, "total": total, "rate": wrong / total}

    total_events = len(rows)
    total_wrong = sum(1 for r in rows if not r["is_correct"])
    distinct_questions_wrong = len({r["question_id"] for r in rows if not r["is_correct"]})

    return {
        "recent_mistakes": recent_mistakes,
        "corrected_mistakes": corrected_mistakes,
        "persistent_mistakes": persistent_mistakes,
        "repeated_mistakes": repeated_mistakes,
        "part_patterns": part_patterns,
        "frequency": {
            "total_events": total_events,
            "total_wrong": total_wrong,
            "distinct_questions_wrong": distinct_questions_wrong,
        },
    }


async def get_mistake_profile(user_db: Client, user_id: str) -> Dict[str, Any]:
    """Single user-scoped read of listening_mistake_events, ordered by id.
    No cross-user aggregation, no writes -- see module docstring."""
    result = await run_sync(
        user_db.table("listening_mistake_events")
        .select("id, question_id, part, is_correct, selected_option, correct_answer, created_at")
        .eq("user_id", user_id)
        .order("id")
        .execute
    )
    return classify_mistakes(result.data)
