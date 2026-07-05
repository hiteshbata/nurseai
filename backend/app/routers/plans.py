from fastapi import APIRouter
from app.core.plans import PLANS

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("/")
def get_plans():
    return {"plans": PLANS}
