from pydantic import BaseModel

from app.question.models import EffectiveStatus


class OptionCount(BaseModel):
    """Один столбец итогов: ключ варианта, подпись и сумма голосов."""

    key: str
    label: str
    count: int


class QuestionResult(BaseModel):
    """Ответ админки по итогам: total — сумма counts, effective_status считается на now."""

    question_id: int
    name: str
    effective_status: EffectiveStatus
    total: int
    counts: list[OptionCount]
