"""Test updated empathy scoring against real past submissions."""
import json
import sys
import os
import asyncio
sys.path.insert(0, '.')

# Override to use OpenRouter since Gemini key is invalid
os.environ["AI_PROVIDER"] = "openrouter"

from app.core.supabase import get_supabase
from app.services.ai_scoring import score_speaking


async def test():
    supabase = get_supabase()

    # Fetch latest speaking submissions with transcripts
    data = supabase.table("submissions").select(
        "id, answer, feedback, question_id, created_at"
    ).eq("module", "speaking").order("created_at", desc=True).limit(5).execute()

    if not data.data:
        print("No speaking submissions found.")
        return

    print(f"Found {len(data.data)} submissions. Testing up to 3...\n")

    tested = 0
    for sub in data.data:
        if tested >= 3:
            break

        answer = sub.get("answer", "").strip()
        if not answer:
            continue

        # Reconstruct conversation from transcript
        lines = answer.split("\n")
        conversation = []
        for line in lines:
            if line.startswith("Nurse:"):
                conversation.append({"role": "nurse", "content": line[6:].strip()})
            elif line.startswith("Patient:"):
                conversation.append({"role": "patient", "content": line[8:].strip()})

        if not conversation:
            continue

        # Try to get scenario title
        scenario_title = "Speaking Practice"
        qid = sub.get("question_id")
        if qid:
            sc = supabase.table("scenarios").select("title").eq("id", qid).execute()
            if sc.data:
                scenario_title = sc.data[0].get("title", scenario_title)

        nurse_card = {"tasks": [f"Respond in scenario: {scenario_title}"]}

        print(f"--- Submission #{tested+1} (ID: {sub['id']}) ---")
        print(f"Scenario: {scenario_title}")
        print(f"Date: {sub['created_at'][:19]}")
        print(f"Conversation: {len(conversation)} turns")
        print()

        result = await score_speaking(
            nurse_card=nurse_card,
            conversation_history=conversation,
            scenario_title=scenario_title,
            supabase=supabase,
        )

        scores = result.get("scores", {})

        print("NEW EMPATHY SCORES:")
        empathy = scores.get("empathy", {})
        print(f"  empathy: {empathy.get('score', 'N/A')}/6")
        print(f"  reasoning: {empathy.get('feedback', 'N/A')[:200]}")
        print()
        print("ALL CLINICAL SCORES (for context):")
        for k in ["empathy", "patient_perspective", "providing_structure",
                   "information_gathering", "information_giving"]:
            s = scores.get(k, {})
            print(f"  {k}: {s.get('score', 'N/A')}/6  -- {s.get('feedback', '')[:100]}")
        print()
        print(f"Clinical avg: {result.get('clinical_average', '?')}")
        print(f"Linguistic avg: {result.get('linguistic_average', '?')}")
        print(f"Overall band: {result.get('overall_band', '?')}")
        print(f"Examiner summary: {result.get('examiner_summary', '')[:200]}")
        print()
        tested += 1

    print("=== DONE ===")


if __name__ == "__main__":
    asyncio.run(test())
