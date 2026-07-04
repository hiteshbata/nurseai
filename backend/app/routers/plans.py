from fastapi import APIRouter
from app.core.plans import PLANS

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("/")
async def get_plans():
    return {"plans": PLANS}
