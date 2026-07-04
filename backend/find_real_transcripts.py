import sys
sys.path.insert(0, '.')
from app.core.supabase import get_supabase

s = get_supabase()
data = s.table("submissions").select("id, answer, created_at, module").eq("module","speaking").order("created_at", desc=True).limit(20).execute()
for sub in data.data:
    answer = sub["answer"] or ""
    has_real_patient = "unavailable" not in answer.lower() and len(answer) > 100
    print(f"ID {sub['id']} | {sub['created_at'][:19]} | len={len(answer)} | real={has_real_patient} | preview: {answer[:100]}")
