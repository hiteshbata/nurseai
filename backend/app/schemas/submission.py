from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class SubmissionBase(BaseModel):
    question_id: int
    module: str
    answer: str

class SubmissionCreate(SubmissionBase):
    pass

class SubmissionResponse(SubmissionBase):
    id: int
    user_id: int
    score: float
    feedback: str
    created_at: datetime

    class Config:
        from_attributes = True
