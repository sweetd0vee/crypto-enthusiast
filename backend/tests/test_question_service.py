from datetime import UTC, datetime, timedelta

import fakeredis.aioredis
import pytest
from pydantic import ValidationError

from app.errors import AppError
from app.question.models import QuestionCreate, QuestionOutput, effective_status
from app.question.service import _has_votes
from app.question.voting_window import require_open_voting_window


class EmptyVoteConnection:
    async def scalar(self, _statement: object) -> bool:
        return False


def published_question(start: datetime) -> QuestionOutput:
    return QuestionOutput(
        id=1,
        name="Question",
        status="published",
        effective_status="live",
        show_time=start,
        duration_seconds=60,
        options=[],
    )


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


def test_voting_window_uses_inclusive_start_and_exclusive_end() -> None:
    start = datetime(2026, 9, 26, 12, tzinfo=UTC)
    question = published_question(start)

    assert require_open_voting_window(question, start) == start + timedelta(seconds=60)

    with pytest.raises(AppError, match="Голосование ещё не началось") as before:
        require_open_voting_window(question, start - timedelta(microseconds=1))
    assert before.value.error == "window_not_started"

    with pytest.raises(AppError, match="Время голосования истекло") as after:
        require_open_voting_window(question, start + timedelta(seconds=60))
    assert after.value.error == "window_closed"


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
