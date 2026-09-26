from datetime import UTC, datetime, timedelta

import fakeredis.aioredis
import pytest
from pydantic import ValidationError

from app.question.models import QuestionCreate, effective_status
from app.question.service import _has_votes


class EmptyVoteConnection:
    async def scalar(self, _statement: object) -> bool:
        return False


def test_effective_status_at_window_boundaries() -> None:
    start = datetime(2026, 9, 26, 12, tzinfo=UTC)

    assert effective_status("draft", None, 60, start) == "draft"
    assert effective_status("cancelled", None, 60, start) == "cancelled"
    assert effective_status("published", start, 60, start - timedelta(microseconds=1)) == (
        "scheduled"
    )
    assert effective_status("published", start, 60, start) == "live"
    assert effective_status("published", start, 60, start + timedelta(seconds=59)) == "live"
    assert effective_status("published", start, 60, start + timedelta(seconds=60)) == "closed"


def test_published_question_requires_show_time() -> None:
    with pytest.raises(ValidationError):
        QuestionCreate(
            name="Question",
            status="published",
            options=[
                {"key": "a", "label": "A"},
                {"key": "b", "label": "B"},
            ],
        )


def test_option_keys_must_be_unique() -> None:
    with pytest.raises(ValidationError):
        QuestionCreate(
            name="Question",
            options=[
                {"key": "same", "label": "A"},
                {"key": "same", "label": "B"},
            ],
        )


async def test_zero_counter_hash_does_not_count_as_votes() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await redis.hset("results:7:0", mapping={"yes": 0, "no": 0})

    assert await _has_votes(EmptyVoteConnection(), redis, 7, 1) is False

    await redis.hset("results:7:0", "yes", 1)

    assert await _has_votes(EmptyVoteConnection(), redis, 7, 1) is True
