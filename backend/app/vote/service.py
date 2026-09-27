"""Чтение публичной формы и горячий путь приёма голоса."""

import hashlib
import logging
import math
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.errors import AppError, unavailable_on_redis_error
from app.question.cache import cache_question, get_cached_question
from app.question.models import OptionInput, QuestionOutput
from app.question.service import get_question
from app.question.voting_window import require_open_voting_window
from app.store.keys import result_counter_key, vote_dedup_key
from app.vote.atomic_counter import reserve_viewer_and_increment_counter
from app.vote.journal import VoteJournal
from app.vote.models import PublicQuestion, VoteEvent

DEDUP_TTL_MARGIN_SECONDS = 86_400
VOTE_UNAVAILABLE = "Сервис голосования временно недоступен"

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _VoteContext:
    question: QuestionOutput
    closes_at: datetime
    dedup_key: str
    redis_dedup_key: str


def dedup_hash(question_id: int, viewer_id: str) -> str:
    return hashlib.sha256(f"{question_id}|{viewer_id}".encode()).hexdigest()


def client_ip_hash(client_ip: str, salt: str) -> str:
    return hashlib.sha256(f"{client_ip}|{salt}".encode()).hexdigest()


# Compatibility aliases for existing internal imports.
_reserve_and_increment = reserve_viewer_and_increment_counter


async def _load_question(
    engine: AsyncEngine,
    redis: Redis,
    question_id: int,
) -> QuestionOutput:
    with unavailable_on_redis_error(VOTE_UNAVAILABLE):
        cached = await get_cached_question(redis, question_id)
        if cached is not None:
            return cached

        loaded = await get_question(engine, question_id)
        await cache_question(redis, loaded)
        return loaded


_check_window = require_open_voting_window


def _public_question(question: QuestionOutput, closes_at: datetime) -> PublicQuestion:
    return PublicQuestion(
        id=question.id,
        name=question.name,
        closes_at=closes_at,
        options=[OptionInput(key=option.key, label=option.label) for option in question.options],
    )


def _dedup_ttl(closes_at: datetime, now: datetime) -> int:
    remaining = math.ceil((closes_at - now).total_seconds())
    return remaining + DEDUP_TTL_MARGIN_SECONDS


def _counter_shard(dedup_key: str, counter_shards: int) -> int:
    return zlib.crc32(dedup_key.encode()) % counter_shards


async def _vote_context(
    engine: AsyncEngine,
    redis: Redis,
    question_id: int,
    viewer_id: str,
    now: datetime,
) -> _VoteContext:
    question = await _load_question(engine, redis, question_id)
    closes_at = _check_window(question, now)
    key = dedup_hash(question_id, viewer_id)
    return _VoteContext(
        question=question,
        closes_at=closes_at,
        dedup_key=key,
        redis_dedup_key=vote_dedup_key(question_id, key),
    )


async def get_public_question(
    engine: AsyncEngine,
    redis: Redis,
    question_id: int,
    viewer_id: str,
    *,
    now: datetime | None = None,
) -> PublicQuestion:
    current_time = now or datetime.now(UTC)
    context = await _vote_context(engine, redis, question_id, viewer_id, current_time)
    with unavailable_on_redis_error(VOTE_UNAVAILABLE):
        if await redis.exists(context.redis_dedup_key):
            raise AppError(409, "already_voted", "Вы уже проголосовали")

    return _public_question(context.question, context.closes_at)


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
    context = await _vote_context(engine, redis, question_id, viewer_id, current_time)
    if option_key not in {option.key for option in context.question.options}:
        raise AppError(422, "invalid_option", "Такого варианта ответа нет")

    with unavailable_on_redis_error(VOTE_UNAVAILABLE):
        shard = _counter_shard(context.dedup_key, counter_shards)
        first_vote = await _reserve_and_increment(
            redis,
            dedup_key=context.redis_dedup_key,
            counter_key=result_counter_key(question_id, shard),
            ttl=_dedup_ttl(context.closes_at, current_time),
            option_key=option_key,
        )
        if not first_vote:
            raise AppError(409, "already_voted", "Вы уже проголосовали")

    event = VoteEvent(
        question_id=question_id,
        option_key=option_key,
        dedup_key=context.dedup_key,
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
