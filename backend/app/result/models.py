from pydantic import BaseModel

from app.question.models import EffectiveStatus


class OptionCount(BaseModel):
    key: str
    label: str
    count: int


class QuestionResult(BaseModel):
    question_id: int
    name: str
    effective_status: EffectiveStatus
    total: int
    counts: list[OptionCount]
