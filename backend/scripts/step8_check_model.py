"""Step 8.0 -- verify which model backs the speaking_semantic_evidence purpose.
Reads QA Supabase (ENVIRONMENT=qa, same convention as validate_patient_state_timing.py).
Read-only: no writes, no code changes.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "qa")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.supabase import get_supabase  # noqa: E402

PURPOSE = "speaking_semantic_evidence"


def main():
    supabase = get_supabase()
    mapping = supabase.table("ai_model_purposes").select("*").eq("purpose", PURPOSE).execute().data
    print(f"ai_model_purposes rows for purpose={PURPOSE!r}: {mapping}")
    if not mapping:
        print("NOT CONFIGURED -- no row in ai_model_purposes for this purpose.")
        return
    model_id = mapping[0]["model_id"]
    model_rows = supabase.table("ai_models").select("*").eq("id", model_id).execute().data
    print(f"\nai_models row id={model_id}:")
    for row in model_rows:
        print(row)

    if model_rows and model_rows[0].get("fallback_model_id"):
        fb_id = model_rows[0]["fallback_model_id"]
        fb_rows = supabase.table("ai_models").select("*").eq("id", fb_id).execute().data
        print(f"\nfallback ai_models row id={fb_id}:")
        for row in fb_rows:
            print(row)
    else:
        print("\nNo fallback model configured.")


if __name__ == "__main__":
    main()
