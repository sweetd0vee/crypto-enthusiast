from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel

from app.question.models import OptionInput


@dataclass(frozen=True, slots=True)
class VoteEvent:
    """Один принятый голос, который уйдёт в таблицу `vote`.

    question_id  — какой опрос
    option_key   — что нажали (yes/no/…)
    dedup_key    — хеш зрителя; в базе уникален вместе с question_id
    ip_hash      — обезличенный IP, на повторный голос не влияет
    voted_at     — серверное время клика
    """

    question_id: int
    option_key: str
    dedup_key: str
    ip_hash: str
    voted_at: datetime

    def as_row(self) -> dict[str, object]:
        """Колонки для INSERT. Имена совпадают с таблицей `vote`."""
        return {
            "question_id": self.question_id,
            "option_key": self.option_key,
            "dedup_key": self.dedup_key,
            "ip_hash": self.ip_hash,
            "voted_at": self.voted_at,
        }


class PublicQuestion(BaseModel):
    """То, что рисует телефон зрителя: текст, когда закроется, кнопки.

    Нет статуса, cookie, IP и хешей — это внутренняя кухня сервера.
    """
    id: int
    name: str
    closes_at: datetime
    options: list[OptionInput]
