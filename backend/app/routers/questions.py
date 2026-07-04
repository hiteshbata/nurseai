from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.supabase import get_supabase
from app.routers.auth import get_current_user, UserInfo
from typing import Optional

router = APIRouter(prefix="/questions", tags=["questions"])

@router.get("/")
def get_questions(
    module: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=100),
    current_user: UserInfo = Depends(get_current_user),
):
    supabase = get_supabase()
    query = supabase.table("questions").select("*").limit(limit)
    if module:
        query = query.eq("module", module)
    data = query.execute()
    result = []
    for q in data.data:
        import json
        result.append({
            "id": q["id"],
            "module": q["module"],
            "type": q["type"],
            "content": q["content"],
            "options": json.loads(q["options"]) if q.get("options") else None,
        })
    return result

@router.get("/{question_id}")
def get_question(
    question_id: int,
    current_user: UserInfo = Depends(get_current_user),
):
    supabase = get_supabase()
    data = supabase.table("questions").select("*").eq("id", question_id).execute()
    if not data.data:
        raise HTTPException(status_code=404, detail="Question not found")
    q = data.data[0]
    import json
    return {
        "id": q["id"],
        "module": q["module"],
        "type": q["type"],
        "content": q["content"],
        "options": json.loads(q["options"]) if q.get("options") else None,
    }
