from datetime import UTC, datetime

import fakeredis.aioredis

from app.question.cache import cache_question, get_cached_question
from app.question.models import OptionOutput, QuestionOutput
from app.store.keys import question_cache_key


def question() -> QuestionOutput:
    return QuestionOutput(
        id=7,
        name="Question",
        status="published",
        effective_status="live",
        show_time=datetime(2026, 9, 26, 12, tzinfo=UTC),
        duration_seconds=60,
        options=[
            OptionOutput(key="a", label="A", position=0),
            OptionOutput(key="b", label="B", position=1),
        ],
    )


async def test_question_cache_round_trip() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    expected = question()

    await cache_question(redis, expected)

    assert await get_cached_question(redis, expected.id) == expected


async def test_invalid_cache_entry_is_evicted() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    key = question_cache_key(7)
    await redis.set(key, "invalid json")

    assert await get_cached_question(redis, 7) is None
    assert await redis.exists(key) == 0
