from datetime import UTC, datetime

import fakeredis.aioredis

from app.question.service import OptionOutput, QuestionOutput
from app.result.service import _read_counters, _response


async def test_counter_shards_are_summed() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await redis.hset("results:7:0", mapping={"a": 2, "b": 1})
    await redis.hset("results:7:1", mapping={"a": 3})

    found, counts = await _read_counters(redis, 7, 2)

    assert found is True
    assert counts == {"a": 5, "b": 1}


def test_result_contains_zero_options_and_correct_total() -> None:
    question = QuestionOutput(
        id=7,
        name="Question",
        status="published",
        effective_status="closed",
        show_time=datetime(2026, 9, 26, 12, tzinfo=UTC),
        duration_seconds=60,
        options=[
            OptionOutput(key="a", label="A", position=0),
            OptionOutput(key="b", label="B", position=1),
        ],
    )

    result = _response(question, {"a": 5})

    assert result.total == 5
    assert [item.count for item in result.counts] == [5, 0]
