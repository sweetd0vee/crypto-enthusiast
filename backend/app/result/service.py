"""Итог админки: сумма шардов Redis и редкий пересчёт из журнала."""

from datetime import UTC, datetime

from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.errors import AppError
from app.question.service import QuestionOutput, get_question
from app.store.schema import question_result, vote


class OptionCount(BaseModel):
    key: str
    label: str
    count: int


class QuestionResult(BaseModel):
    question_id: int
    name: str
    effective_status: str
    total: int
    counts: list[OptionCount]


def _counter_keys(question_id: int, counter_shards: int) -> list[str]:
    return [f"results:{question_id}:{shard}" for shard in range(counter_shards)]


async def _read_counters(
    redis: Redis,
    question_id: int,
    counter_shards: int,
) -> tuple[bool, dict[str, int]]:
    keys = _counter_keys(question_id, counter_shards)
    try:
        pipeline = redis.pipeline(transaction=False)
        for key in keys:
            pipeline.hgetall(key)
        shards = await pipeline.execute()
    except RedisError as exc:
        raise AppError(503, "unavailable", "Счётчики временно недоступны") from exc

    totals: dict[str, int] = {}
    found = False
    for shard in shards:
        if shard:
            found = True
        for option_key, count in shard.items():
            totals[option_key] = totals.get(option_key, 0) + int(count)
    return found, totals


def _response(question: QuestionOutput, counts: dict[str, int]) -> QuestionResult:
    options = [
        OptionCount(
            key=option.key,
            label=option.label,
            count=counts.get(option.key, 0),
        )
        for option in question.options
    ]
    return QuestionResult(
        question_id=question.id,
        name=question.name,
        effective_status=question.effective_status,
        total=sum(option.count for option in options),
        counts=options,
    )


async def rebuild_results(
    engine: AsyncEngine,
    redis: Redis,
    question_id: int,
    counter_shards: int,
) -> QuestionResult:
    question = await get_question(engine, question_id)
    async with engine.begin() as connection:
        rows = (
            await connection.execute(
                select(vote.c.option_key, func.count().label("count"))
                .where(vote.c.question_id == question_id)
                .group_by(vote.c.option_key)
            )
        ).all()
        counts = {option_key: count for option_key, count in rows}

        await connection.execute(
            delete(question_result).where(question_result.c.question_id == question_id)
        )
        await connection.execute(
            insert(question_result),
            [
                {
                    "question_id": question_id,
                    "option_key": option.key,
                    "count": counts.get(option.key, 0),
                    "rebuilt_at": datetime.now(UTC),
                }
                for option in question.options
            ],
        )

    keys = _counter_keys(question_id, counter_shards)
    try:
        pipeline = redis.pipeline(transaction=True)
        pipeline.delete(*keys)
        pipeline.hset(
            keys[0],
            mapping={option.key: counts.get(option.key, 0) for option in question.options},
        )
        await pipeline.execute()
    except RedisError as exc:
        raise AppError(503, "unavailable", "Счётчики временно недоступны") from exc
    return _response(question, counts)


async def get_results(
    engine: AsyncEngine,
    redis: Redis,
    question_id: int,
    counter_shards: int,
) -> QuestionResult:
    question = await get_question(engine, question_id)
    found, counts = await _read_counters(redis, question_id, counter_shards)
    if not found and question.effective_status != "live":
        return await rebuild_results(engine, redis, question_id, counter_shards)
    return _response(question, counts)
