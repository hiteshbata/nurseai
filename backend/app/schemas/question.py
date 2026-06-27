from pydantic import BaseModel
from typing import Optional, List

class QuestionBase(BaseModel):
    module: str
    type: str
    content: str
    options: Optional[List[str]] = None
    correct_answer: Optional[str] = None

class QuestionCreate(QuestionBase):
    pass

class QuestionResponse(QuestionBase):
    id: int

    class Config:
        from_attributes = True
