"""Когда зрителю можно голосовать.

Окно эфира — промежуток [show_time, closes_at). Квадратная скобка слева
значит «в момент старта уже можно», круглая справа — «ровно в момент
closes_at уже нельзя». Все проверки времени идут по часам сервера, не телефона.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from app.errors import AppError

if TYPE_CHECKING:
    from app.question.models import QuestionOutput


def calculate_closing_time(show_time: datetime, duration_seconds: int) -> datetime:
    """Момент закрытия окна: время выхода ролика плюс длительность в секундах.

    Пример: эфир в 21:00, длительность 60 → closes_at = 21:01.
    Голосовать можно с 21:00:00 до 21:00:59.999, в 21:01:00 уже 410.
    """
    return show_time + timedelta(seconds=duration_seconds)


def require_open_voting_window(question: QuestionOutput, now: datetime) -> datetime:
    """Пустить к голосованию только если опрос опубликован и сейчас внутри окна.

    Проверки идут сверху вниз, первая сработавшая побеждает:
    1. Не published или нет времени эфира → 403 not_published
       (черновик / отменённый / забыли указать show_time).
    2. Сейчас раньше старта → 403 window_not_started
       (ролик ещё не вышел, QR уже кто-то открыл).
    3. Сейчас уже closes_at или позже → 410 window_closed
       (минута прошла). 410, а не 403: «этого ресурса больше нет».

    Если всё хорошо — возвращаем closes_at. Его покажем зрителю на форме
    и используем как базу для TTL ключа дедупа.
    """
    show_time = question.show_time
    if question.status != "published" or show_time is None:
        raise AppError(403, "not_published", "Вопрос не опубликован")
    if now < show_time:
        raise AppError(403, "window_not_started", "Голосование ещё не началось")

    closes_at = calculate_closing_time(show_time, question.duration_seconds)
    if now >= closes_at:
        raise AppError(410, "window_closed", "Время голосования истекло")
    return closes_at
