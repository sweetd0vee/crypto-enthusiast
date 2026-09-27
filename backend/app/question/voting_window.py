"""Single source of truth for voting-window boundaries."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from app.errors import AppError

if TYPE_CHECKING:
    from app.question.models import QuestionOutput


def calculate_closing_time(show_time: datetime, duration_seconds: int) -> datetime:
    """Return the exclusive upper boundary of a voting window."""
    return show_time + timedelta(seconds=duration_seconds)


def require_open_voting_window(question: QuestionOutput, now: datetime) -> datetime:
    """Validate that voting is open and return its exclusive closing time."""
    show_time = question.show_time
    if question.status != "published" or show_time is None:
        raise AppError(403, "not_published", "Вопрос не опубликован")
    if now < show_time:
        raise AppError(403, "window_not_started", "Голосование ещё не началось")

    closes_at = calculate_closing_time(show_time, question.duration_seconds)
    if now >= closes_at:
        raise AppError(410, "window_closed", "Время голосования истекло")
    return closes_at
