"""Shared grading primitives for any module that reuses the `questions` table
(exact-match MCQ options, correct_answer text) -- Reading and Listening both
grade this way, so the logic lives here once instead of being copied per
module. Pure and testable; the AI call for open-ended items (Reading's
short-answer, Listening's gap-fill) stays in each module's own router since
its prompt is module-specific."""
from typing import Any, Dict, List, Optional


def grade_exact_match(questions_by_id: Dict[int, dict], answers: List[dict]) -> Dict[str, Any]:
    """Grade answers against server-side correct_answer. Never trusts the
    client for correctness. Returns band (0-6), counts, and per-question results."""
    graded = 0
    correct = 0
    results = []
    for a in answers:
        q = questions_by_id.get(a.get("questionId"))
        if not q or q.get("correct_answer") is None:
            continue
        graded += 1
        is_correct = a.get("selectedOption") == q["correct_answer"]
        if is_correct:
            correct += 1
        results.append({
            "questionId": q["id"],
            "selected": a.get("selectedOption"),
            "correct_answer": q["correct_answer"],
            "is_correct": is_correct,
        })
    band = round((correct / graded) * 6, 2) if graded else 0.0
    return {"band": band, "correct": correct, "graded": graded, "results": results}


def combine_graded_results(exact: Dict[str, Any], ai_graded: List[dict]) -> Dict[str, Any]:
    """Merge exact-match results with AI-graded (open-ended) results into one
    band score. Pure and testable -- the AI call itself isn't."""
    correct = exact["correct"] + sum(1 for r in ai_graded if r["is_correct"])
    graded = exact["graded"] + len(ai_graded)
    band = round((correct / graded) * 6, 2) if graded else 0.0
    return {"band": band, "correct": correct, "graded": graded, "results": exact["results"] + ai_graded}


def resolve_latest_wrong_answers(feedback_blobs: List[dict]) -> Dict[int, dict]:
    """Given submission feedback blobs newest-first, return the per-question
    result for questions whose MOST RECENT attempt was wrong. A question fixed
    in a later attempt must not resurface just because an older attempt got
    it wrong."""
    seen_qids: set = set()
    wrong_by_qid: Dict[int, dict] = {}
    for fb in feedback_blobs:
        for r in fb.get("results", []):
            qid = r.get("questionId")
            if qid is None or qid in seen_qids:
                continue  # a more recent attempt already settled this question
            seen_qids.add(qid)
            if not r.get("is_correct"):
                wrong_by_qid[qid] = r
    return wrong_by_qid
