"""Step 12A Task 13 -- read-only inspection of existing QA session data.

Purely offline: reads real session_transcripts/scenarios rows from the QA
Supabase project and runs the UNMODIFIED deterministic layer
(build_speaking_evidence) over them. No model call (no semantic_evidence
functions touched), so this is safe under Task 18's "no paid model calls"
rule -- it only asks "does data exist that COULD represent these three
findings", not "does the semantic layer catch them" (that needs Sonnet,
still blocked -- see step8_live_experiment.py).

Usage:
    cd backend
    python scripts/step12a_qa_data_check.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "qa")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.supabase import get_supabase  # noqa: E402
from app.services.speaking_evidence import build_speaking_evidence  # noqa: E402


def main():
    supabase = get_supabase()
    rows = supabase.table("session_transcripts").select(
        "session_usage_id, user_id, scenario_id, transcript, created_at"
    ).order("session_usage_id").execute().data or []

    sessions: dict[int, list[dict]] = {}
    scenario_ids: dict[int, int] = {}
    for row in rows:
        sid = row["session_usage_id"]
        sessions.setdefault(sid, [])
        for turn in row.get("transcript") or []:
            sessions[sid].append({"role": turn.get("role", ""), "content": turn.get("text", "")})
        scenario_ids[sid] = row.get("scenario_id")

    print(f"Found {len(sessions)} realtime session_usage_id(s) in QA: {sorted(sessions.keys())}\n")

    for sid, history in sorted(sessions.items()):
        if not history:
            continue
        scenario_id = scenario_ids[sid]
        scenario_rows = supabase.table("scenarios").select("id, title, interlocutor_card").eq("id", scenario_id).execute().data
        card = scenario_rows[0]["interlocutor_card"] if scenario_rows else {}
        title = scenario_rows[0]["title"] if scenario_rows else "(scenario not found)"

        ev = build_speaking_evidence(card, history)
        hidden_items = card.get("information_to_withhold") or []
        concerns = card.get("questions_to_ask") or card.get("concerns") or []

        print(f"--- session_usage_id={sid} scenario={title!r} turns={len(history)} ---")
        print(f"  hidden-info items defined: {hidden_items}")
        for h in ev.hidden_info_outcomes:
            print(f"    candidate_detected={h.candidate_detected} final_status={h.final_status} "
                  f"turn={h.turn_index} evidence={h.evidence_text!r}")
        print(f"  concerns defined: {concerns}")
        for c in ev.concern_outcomes:
            print(f"    concern={c.concern!r} final_status={c.final_status} history_statuses={[e['status'] for e in c.history]}")
        candidate_summary = {}
        for e in ev.candidate_events:
            candidate_summary[e.event] = candidate_summary.get(e.event, 0) + 1
        print(f"  deterministic candidate_events: {candidate_summary}\n")


if __name__ == "__main__":
    main()
