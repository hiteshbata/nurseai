import json
import sys
sys.path.insert(0, '.')
from app.core.supabase import get_supabase

s = get_supabase()
data = s.table("submissions").select("id, answer, question_id, module").eq("module","speaking").order("created_at", desc=True).limit(3).execute()
for sub in data.data:
    print(f"--- ID {sub['id']} (qid={sub['question_id']}) ---")
    print(repr(sub["answer"][:600]))
    print()
