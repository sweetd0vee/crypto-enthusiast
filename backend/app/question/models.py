"""Схемы вопроса: вход админки, выход API и расчёт effective_status."""

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.question.voting_window import calculate_closing_time

QuestionStatus = Literal["draft", "published", "cancelled"]
EffectiveStatus = Literal["draft", "cancelled", "scheduled", "live", "closed"]


class OptionInput(BaseModel):
    """Вариант ответа, который задаёт админ: стабильный `key` и подпись для экрана."""

    model_config = ConfigDict(str_strip_whitespace=True)

    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1)


class OptionOutput(OptionInput):
    """Вариант из БД: к key/label добавляется порядок на форме."""

    position: int


class QuestionInput(BaseModel):
    """Общие поля создания и правки. Валидаторы не пускают published без show_time."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1)
    status: QuestionStatus
    show_time: datetime | None = None
    duration_seconds: int = Field(default=60, ge=10, le=3600)
    options: list[OptionInput] = Field(min_length=2, max_length=10)

    @field_validator("show_time")
    @classmethod
    def show_time_must_have_timezone(cls, value: datetime | None) -> datetime | None:
        """Время эфира только с таймзоной; наивное значение отвергаем, остальное нормализуем в UTC."""
        if value is not None and value.tzinfo is None:
            raise ValueError("show_time must include a timezone")
        return value.astimezone(UTC) if value is not None else None

    @field_validator("options")
    @classmethod
    def option_keys_must_be_unique(cls, value: list[OptionInput]) -> list[OptionInput]:
        """Ключи вариантов внутри одного вопроса не должны повторяться."""
        keys = [option.key for option in value]
        if len(keys) != len(set(keys)):
            raise ValueError("option keys must be unique")
        return value

    @model_validator(mode="after")
    def published_question_needs_show_time(self) -> Self:
        """Опубликованный вопрос без времени эфира нельзя сохранить: окно тогда не определено."""
        if self.status == "published" and self.show_time is None:
            raise ValueError("show_time is required for a published question")
        return self


class QuestionCreate(QuestionInput):
    status: Literal["draft", "published"] = "draft"


class QuestionUpdate(QuestionInput):
    pass


class QuestionOutput(BaseModel):
    """Карточка для админки и кэша Redis: status из БД + effective_status на текущий момент."""

    id: int
    name: str
    status: QuestionStatus
    effective_status: EffectiveStatus
    show_time: datetime | None
    duration_seconds: int
    options: list[OptionOutput]


def effective_status(
    status: QuestionStatus,
    show_time: datetime | None,
    duration_seconds: int,
    now: datetime | None = None,
) -> EffectiveStatus:
    """Статус, который видит админ на экране. В базу его не пишем — считаем каждый раз.

    В таблице лежит только то, что сохранил человек:
    draft (черновик), published (опубликован), cancelled (отменён).

    Для published дополнительно смотрим часы:
    - сейчас раньше show_time → scheduled (ещё не эфир);
    - внутри окна [show_time, closes_at) → live (можно голосовать);
    - closes_at уже наступил → closed (минута прошла).

    Считаем на серверном времени в момент запроса. Если бы хранили
    «live» колонкой, в 21:01 карточка всё ещё показывала бы эфир,
    пока кто-то не сделает UPDATE.
    """
    if status != "published":
        return status
    if show_time is None:
        raise ValueError("published question has no show_time")

    current_time = now or datetime.now(UTC)
    if current_time < show_time:
        return "scheduled"
    if current_time < calculate_closing_time(show_time, duration_seconds):
        return "live"
    return "closed"
