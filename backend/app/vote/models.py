from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel

from app.question.models import OptionInput


@dataclass(frozen=True, slots=True)
class VoteEvent:
    question_id: int
    option_key: str
    dedup_key: str
    ip_hash: str
    voted_at: datetime

    def as_row(self) -> dict[str, object]:
        return {
            "question_id": self.question_id,
            "option_key": self.option_key,
            "dedup_key": self.dedup_key,
            "ip_hash": self.ip_hash,
            "voted_at": self.voted_at,
        }


class PublicQuestion(BaseModel):
    id: int
    name: str
    closes_at: datetime
    options: list[OptionInput]
