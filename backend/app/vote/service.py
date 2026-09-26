"""Чтение публичной формы и горячий путь приёма голоса."""

import hashlib
import logging
import math
import zlib
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.errors import AppError
from app.question.cache import cache_question, get_cached_question
from app.question.models import QuestionOutput
from app.question.service import get_question
from app.store.keys import result_counter_key, vote_dedup_key
from app.vote.journal import VoteJournal
from app.vote.models import PublicQuestion, VoteEvent

DEDUP_TTL_MARGIN_SECONDS = 86_400

logger = logging.getLogger(__name__)


def dedup_hash(question_id: int, viewer_id: str) -> str:
    return hashlib.sha256(f"{question_id}|{viewer_id}".encode()).hexdigest()


def client_ip_hash(client_ip: str, salt: str) -> str:
    return hashlib.sha256(f"{client_ip}|{salt}".encode()).hexdigest()


async def _load_question(
    engine: AsyncEngine,
    redis: Redis,
    question_id: int,
) -> QuestionOutput:
    try:
        cached = await get_cached_question(redis, question_id)
        if cached is not None:
            return cached

        loaded = await get_question(engine, question_id)
        await cache_question(redis, loaded)
        return loaded
    except AppError:
        raise
    except RedisError as exc:
        raise AppError(503, "unavailable", "Сервис голосования временно недоступен") from exc


def _check_window(question: QuestionOutput, now: datetime) -> datetime:
    if question.status != "published":
        raise AppError(403, "not_published", "Вопрос не опубликован")
    if question.show_time is None:
        raise AppError(403, "not_published", "Вопрос не опубликован")
    if now < question.show_time:
        raise AppError(403, "window_not_started", "Голосование ещё не началось")

    closes_at = question.show_time + timedelta(seconds=question.duration_seconds)
    if now >= closes_at:
        raise AppError(410, "window_closed", "Время голосования истекло")
    return closes_at


async def get_public_question(
    engine: AsyncEngine,
    redis: Redis,
    question_id: int,
    viewer_id: str,
    *,
    now: datetime | None = None,
) -> PublicQuestion:
    current_time = now or datetime.now(UTC)
    question = await _load_question(engine, redis, question_id)
    closes_at = _check_window(question, current_time)
    dedup_key = vote_dedup_key(question_id, dedup_hash(question_id, viewer_id))
    try:
        if await redis.exists(dedup_key):
            raise AppError(409, "already_voted", "Вы уже проголосовали")
    except RedisError as exc:
        raise AppError(503, "unavailable", "Сервис голосования временно недоступен") from exc

    return PublicQuestion(
        id=question.id,
        name=question.name,
        closes_at=closes_at,
        options=[{"key": option.key, "label": option.label} for option in question.options],
    )


async def accept_vote(
    engine: AsyncEngine,
    redis: Redis,
    journal: VoteJournal,
    *,
    question_id: int,
    option_key: str,
    viewer_id: str,
    client_ip: str,
    ip_hash_salt: str,
    counter_shards: int,
    asynchronous_journal: bool,
    now: datetime | None = None,
) -> None:
    current_time = now or datetime.now(UTC)
    question = await _load_question(engine, redis, question_id)
    closes_at = _check_window(question, current_time)
    if option_key not in {option.key for option in question.options}:
        raise AppError(422, "invalid_option", "Такого варианта ответа нет")

    dedup_key = dedup_hash(question_id, viewer_id)
    redis_dedup_key = vote_dedup_key(question_id, dedup_key)
    ttl = math.ceil((closes_at - current_time).total_seconds()) + DEDUP_TTL_MARGIN_SECONDS
    try:
        first_vote = await redis.set(redis_dedup_key, "1", ex=ttl, nx=True)
        if not first_vote:
            raise AppError(409, "already_voted", "Вы уже проголосовали")
        shard = zlib.crc32(dedup_key.encode()) % counter_shards
        await redis.hincrby(result_counter_key(question_id, shard), option_key, 1)
    except AppError:
        raise
    except RedisError as exc:
        with suppress(RedisError):
            await redis.delete(redis_dedup_key)
        raise AppError(503, "unavailable", "Сервис голосования временно недоступен") from exc

    event = VoteEvent(
        question_id=question_id,
        option_key=option_key,
        dedup_key=dedup_key,
        ip_hash=client_ip_hash(client_ip, ip_hash_salt),
        voted_at=current_time,
    )
    if asynchronous_journal:
        journal.enqueue(event)
    else:
        try:
            await journal.write(event)
        except Exception:
            logger.exception("failed to write accepted vote to journal")
