"""CRUD вопроса, эффективный статус и кэш карточки в Redis."""

import json
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from redis.asyncio import Redis
from sqlalchemy import delete, exists, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.api.errors import AppError
from app.store.schema import question, question_option, vote

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


class QuestionCreate(QuestionInput):
    status: Literal["draft", "published"] = "draft"

    @model_validator(mode="after")
    def published_question_needs_show_time(self) -> "QuestionCreate":
        if self.status == "published" and self.show_time is None:
            raise ValueError("show_time is required for a published question")
        return self


class QuestionUpdate(QuestionInput):
    status: QuestionStatus

    @model_validator(mode="after")
    def published_question_needs_show_time(self) -> "QuestionUpdate":
        if self.status == "published" and self.show_time is None:
            raise ValueError("show_time is required for a published question")
        return self


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


def _to_output(row: dict, options: list[dict], now: datetime) -> QuestionOutput:
    status: QuestionStatus = row["status"]
    return QuestionOutput(
        id=row["id"],
        name=row["name"],
        status=status,
        effective_status=effective_status(
            status,
            row["show_time"],
            row["duration_seconds"],
            now,
        ),
        show_time=row["show_time"],
        duration_seconds=row["duration_seconds"],
        options=[
            OptionOutput(
                key=option["key"],
                label=option["label"],
                position=option["position"],
            )
            for option in options
        ],
    )


async def _load_one(
    connection: AsyncConnection,
    question_id: int,
    *,
    for_update: bool = False,
) -> QuestionOutput | None:
    statement = select(question).where(question.c.id == question_id)
    if for_update:
        statement = statement.with_for_update()
    row = (await connection.execute(statement)).mappings().one_or_none()
    if row is None:
        return None

    option_rows = (
        await connection.execute(
            select(question_option)
            .where(question_option.c.question_id == question_id)
            .order_by(question_option.c.position)
        )
    ).mappings()
    return _to_output(dict(row), [dict(item) for item in option_rows], datetime.now(UTC))


async def get_question(engine: AsyncEngine, question_id: int) -> QuestionOutput:
    async with engine.connect() as connection:
        result = await _load_one(connection, question_id)
    if result is None:
        raise AppError(404, "not_found", "Вопрос не найден")
    return result


async def list_questions(engine: AsyncEngine) -> list[QuestionOutput]:
    async with engine.connect() as connection:
        ids = (
            await connection.execute(select(question.c.id).order_by(question.c.id))
        ).scalars()
        return [
            loaded
            for question_id in ids
            if (loaded := await _load_one(connection, question_id)) is not None
        ]


async def _write_options(
    connection: AsyncConnection,
    question_id: int,
    options: list[OptionInput],
) -> None:
    await connection.execute(
        insert(question_option),
        [
            {
                "question_id": question_id,
                "key": option.key,
                "label": option.label,
                "position": position,
            }
            for position, option in enumerate(options)
        ],
    )


async def _cache(redis: Redis, value: QuestionOutput) -> None:
    await redis.set(
        f"question:{value.id}",
        json.dumps(value.model_dump(mode="json"), ensure_ascii=False),
    )


async def create_question(
    engine: AsyncEngine,
    redis: Redis,
    data: QuestionCreate,
) -> QuestionOutput:
    async with engine.begin() as connection:
        question_id = (
            await connection.execute(
                insert(question)
                .values(
                    name=data.name,
                    status=data.status,
                    show_time=data.show_time,
                    duration_seconds=data.duration_seconds,
                )
                .returning(question.c.id)
            )
        ).scalar_one()
        await _write_options(connection, question_id, data.options)
        created = await _load_one(connection, question_id)

    assert created is not None
    await _cache(redis, created)
    return created


def _same_options(current: list[OptionOutput], incoming: list[OptionInput]) -> bool:
    return [(item.key, item.label) for item in current] == [
        (item.key, item.label) for item in incoming
    ]


async def _has_votes(
    connection: AsyncConnection,
    redis: Redis,
    question_id: int,
    counter_shards: int,
) -> bool:
    in_database = await connection.scalar(
        select(exists().where(vote.c.question_id == question_id))
    )
    if in_database:
        return True
    keys = [f"results:{question_id}:{shard}" for shard in range(counter_shards)]
    return bool(await redis.exists(*keys))


async def update_question(
    engine: AsyncEngine,
    redis: Redis,
    question_id: int,
    data: QuestionUpdate,
    counter_shards: int,
) -> QuestionOutput:
    async with engine.begin() as connection:
        current = await _load_one(connection, question_id, for_update=True)
        if current is None:
            raise AppError(404, "not_found", "Вопрос не найден")

        options_changed = not _same_options(current.options, data.options)
        if options_changed and await _has_votes(
            connection,
            redis,
            question_id,
            counter_shards,
        ):
            raise AppError(
                409,
                "options_locked",
                "Нельзя менять варианты после появления голосов",
            )

        await connection.execute(
            update(question)
            .where(question.c.id == question_id)
            .values(
                name=data.name,
                status=data.status,
                show_time=data.show_time,
                duration_seconds=data.duration_seconds,
                updated_at=datetime.now(UTC),
            )
        )
        if options_changed:
            await connection.execute(
                delete(question_option).where(question_option.c.question_id == question_id)
            )
            await _write_options(connection, question_id, data.options)
        updated = await _load_one(connection, question_id)

    assert updated is not None
    await _cache(redis, updated)
    return updated


async def delete_question(
    engine: AsyncEngine,
    redis: Redis,
    question_id: int,
    counter_shards: int,
) -> None:
    async with engine.begin() as connection:
        current = await _load_one(connection, question_id, for_update=True)
        if current is None:
            raise AppError(404, "not_found", "Вопрос не найден")
        if current.status != "draft" or await _has_votes(
            connection,
            redis,
            question_id,
            counter_shards,
        ):
            raise AppError(
                409,
                "delete_forbidden",
                "Можно удалить только черновик без голосов",
            )
        await connection.execute(delete(question).where(question.c.id == question_id))

    await redis.delete(f"question:{question_id}")
