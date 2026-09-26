"""Правила CRUD вопросов поверх PostgreSQL и Redis-кэша."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from redis.asyncio import Redis
from sqlalchemy import delete, exists, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.api.errors import AppError
from app.question.cache import cache_question, evict_question
from app.question.models import (
    OptionInput,
    OptionOutput,
    QuestionCreate,
    QuestionOutput,
    QuestionStatus,
    QuestionUpdate,
    effective_status,
)
from app.store.keys import result_counter_keys
from app.store.schema import question, question_option, vote


def _to_output(
    row: Mapping[str, Any],
    options: list[Mapping[str, Any]],
    now: datetime,
) -> QuestionOutput:
    status = cast(QuestionStatus, row["status"])
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
    ).mappings().all()
    return _to_output(row, option_rows, datetime.now(UTC))


async def get_question(engine: AsyncEngine, question_id: int) -> QuestionOutput:
    async with engine.connect() as connection:
        result = await _load_one(connection, question_id)
    if result is None:
        raise AppError(404, "not_found", "Вопрос не найден")
    return result


async def list_questions(engine: AsyncEngine) -> list[QuestionOutput]:
    async with engine.connect() as connection:
        question_rows = (
            await connection.execute(select(question).order_by(question.c.id))
        ).mappings().all()
        if not question_rows:
            return []

        question_ids = [row["id"] for row in question_rows]
        option_rows = (
            await connection.execute(
                select(question_option)
                .where(question_option.c.question_id.in_(question_ids))
                .order_by(question_option.c.question_id, question_option.c.position)
            )
        ).mappings().all()

    options_by_question: dict[int, list[Mapping[str, Any]]] = {
        question_id: [] for question_id in question_ids
    }
    for option in option_rows:
        options_by_question[option["question_id"]].append(option)

    now = datetime.now(UTC)
    return [
        _to_output(row, options_by_question[row["id"]], now)
        for row in question_rows
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

    if created is None:
        raise RuntimeError("created question could not be loaded")
    await cache_question(redis, created)
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
    keys = result_counter_keys(question_id, counter_shards)
    pipeline = redis.pipeline(transaction=False)
    for key in keys:
        pipeline.hvals(key)
    shard_values = await pipeline.execute()
    return any(int(value) > 0 for values in shard_values for value in values)


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

    if updated is None:
        raise RuntimeError("updated question could not be loaded")
    await cache_question(redis, updated)
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

    await evict_question(redis, question_id)
