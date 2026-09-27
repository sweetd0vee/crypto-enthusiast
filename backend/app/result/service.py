"""Итог админки: сумма шардов Redis и редкий пересчёт из журнала."""

from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.errors import unavailable_on_redis_error
from app.question.models import QuestionOutput
from app.question.service import get_question
from app.result.models import OptionCount, QuestionResult
from app.store.counter_shards import aggregate_counter_shards, read_counter_shards
from app.store.keys import result_counter_keys
from app.store.schema import question_result, vote

COUNTERS_UNAVAILABLE = "Счётчики временно недоступны"


async def _journal_counts(connection: AsyncConnection, question_id: int) -> dict[str, int]:
    rows = (
        await connection.execute(
            select(vote.c.option_key, func.count().label("count"))
            .where(vote.c.question_id == question_id)
            .group_by(vote.c.option_key)
        )
    ).all()
    return {option_key: count for option_key, count in rows}


async def _store_snapshot(
    connection: AsyncConnection,
    question: QuestionOutput,
    counts: dict[str, int],
    rebuilt_at: datetime,
) -> None:
    await connection.execute(
        delete(question_result).where(question_result.c.question_id == question.id)
    )
    await connection.execute(
        insert(question_result),
        [
            {
                "question_id": question.id,
                "option_key": option.key,
                "count": counts.get(option.key, 0),
                "rebuilt_at": rebuilt_at,
            }
            for option in question.options
        ],
    )


async def _replace_counters(
    redis: Redis,
    question: QuestionOutput,
    counts: dict[str, int],
    counter_shards: int,
) -> None:
    keys = result_counter_keys(question.id, counter_shards)
    with unavailable_on_redis_error(COUNTERS_UNAVAILABLE):
        pipeline = redis.pipeline(transaction=True)
        pipeline.delete(*keys)
        pipeline.hset(
            keys[0],
            mapping={option.key: counts.get(option.key, 0) for option in question.options},
        )
        await pipeline.execute()


async def _read_counters(
    redis: Redis,
    question_id: int,
    counter_shards: int,
) -> tuple[bool, dict[str, int]]:
    with unavailable_on_redis_error(COUNTERS_UNAVAILABLE):
        shards = await read_counter_shards(redis, question_id, counter_shards)
    return any(shards), aggregate_counter_shards(shards)


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
        counts = await _journal_counts(connection, question_id)
        await _store_snapshot(connection, question, counts, datetime.now(UTC))

    await _replace_counters(redis, question, counts, counter_shards)
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
