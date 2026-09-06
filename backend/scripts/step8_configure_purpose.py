"""Step 8.0b -- wire speaking_semantic_evidence to a model in QA only.

Real Claude Sonnet 5 (ai_models id=6, openrouter) is unreachable: no
OPENROUTER_API_KEY available locally or in QA env, and that row's own last
health check failed for that exact reason. Per user decision, this points
the purpose at ai_models id=3 (Gemini 3.5 Flash, native google provider,
GEMINI_API_KEY present in QA) instead, purely to validate the semantic
evidence PIPELINE end-to-end. This is NOT a Sonnet 5 evaluation -- see
step 8 report for why.

QA only. Does not touch production ai_model_purposes.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "qa")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.supabase import get_supabase  # noqa: E402

PURPOSE = "speaking_semantic_evidence"
MODEL_ID = 3  # Gemini 3.5 Flash (premium scoring), native google provider


def main():
    supabase = get_supabase()
    existing = supabase.table("ai_model_purposes").select("*").eq("purpose", PURPOSE).execute().data
    if existing:
        print(f"Already configured: {existing}")
        return
    result = supabase.table("ai_model_purposes").insert({
        "purpose": PURPOSE, "model_id": MODEL_ID,
    }).execute()
    print(f"Inserted: {result.data}")


if __name__ == "__main__":
    main()
