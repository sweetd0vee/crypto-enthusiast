from datetime import UTC, datetime, timedelta
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

QuestionStatus = Literal["draft", "published", "cancelled"]
EffectiveStatus = Literal["draft", "cancelled", "scheduled", "live", "closed"]


class OptionInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1)


class OptionOutput(OptionInput):
    position: int


class QuestionInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1)
    status: QuestionStatus
    show_time: datetime | None = None
    duration_seconds: int = Field(default=60, ge=10, le=3600)
    options: list[OptionInput] = Field(min_length=2, max_length=10)

    @field_validator("show_time")
    @classmethod
    def show_time_must_have_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("show_time must include a timezone")
        return value.astimezone(UTC) if value is not None else None

    @field_validator("options")
    @classmethod
    def option_keys_must_be_unique(cls, value: list[OptionInput]) -> list[OptionInput]:
        keys = [option.key for option in value]
        if len(keys) != len(set(keys)):
            raise ValueError("option keys must be unique")
        return value

    @model_validator(mode="after")
    def published_question_needs_show_time(self) -> Self:
        if self.status == "published" and self.show_time is None:
            raise ValueError("show_time is required for a published question")
        return self


class QuestionCreate(QuestionInput):
    status: Literal["draft", "published"] = "draft"


class QuestionUpdate(QuestionInput):
    pass


class QuestionOutput(BaseModel):
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
    if status != "published":
        return status
    if show_time is None:
        raise ValueError("published question has no show_time")

    current_time = now or datetime.now(UTC)
    if current_time < show_time:
        return "scheduled"
    if current_time < show_time + timedelta(seconds=duration_seconds):
        return "live"
    return "closed"
