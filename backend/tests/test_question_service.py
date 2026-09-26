from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.question.models import QuestionCreate, effective_status


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
