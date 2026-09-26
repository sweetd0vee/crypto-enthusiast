"""Чтение публичной формы и горячий путь приёма голоса."""

import hashlib
import logging
import math
import zlib
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.errors import AppError, unavailable_on_redis_error
from app.question.cache import cache_question, get_cached_question
from app.question.models import OptionInput, QuestionOutput
from app.question.service import get_question
from app.store.keys import result_counter_key, vote_dedup_key
from app.vote.journal import VoteJournal
from app.vote.models import PublicQuestion, VoteEvent

DEDUP_TTL_MARGIN_SECONDS = 86_400
VOTE_UNAVAILABLE = "Сервис голосования временно недоступен"

logger = logging.getLogger(__name__)

ACCEPT_VOTE_SCRIPT = """
if redis.call("EXISTS", KEYS[1]) == 1 then
    return 0
end

local counter_type = redis.call("TYPE", KEYS[2])
if counter_type["ok"] ~= "none" and counter_type["ok"] ~= "hash" then
    return redis.error_reply("vote counter key has an unexpected type")
end

redis.call("SET", KEYS[1], "1", "EX", ARGV[1])
redis.call("HINCRBY", KEYS[2], ARGV[2], 1)
return 1
"""


def dedup_hash(question_id: int, viewer_id: str) -> str:
    return hashlib.sha256(f"{question_id}|{viewer_id}".encode()).hexdigest()


def client_ip_hash(client_ip: str, salt: str) -> str:
    return hashlib.sha256(f"{client_ip}|{salt}".encode()).hexdigest()


async def _reserve_and_increment(
    redis: Redis,
    *,
    dedup_key: str,
    counter_key: str,
    ttl: int,
    option_key: str,
) -> bool:
    result = await redis.eval(
        ACCEPT_VOTE_SCRIPT,
        2,
        dedup_key,
        counter_key,
        ttl,
        option_key,
    )
    return result == 1


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


def _check_window(question: QuestionOutput, now: datetime) -> datetime:
    show_time = question.show_time
    if question.status != "published" or show_time is None:
        raise AppError(403, "not_published", "Вопрос не опубликован")
    if now < show_time:
        raise AppError(403, "window_not_started", "Голосование ещё не началось")

    closes_at = show_time + timedelta(seconds=question.duration_seconds)
    if now >= closes_at:
        raise AppError(410, "window_closed", "Время голосования истекло")
    return closes_at


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
    with unavailable_on_redis_error(VOTE_UNAVAILABLE):
        if await redis.exists(dedup_key):
            raise AppError(409, "already_voted", "Вы уже проголосовали")

    return _public_question(question, closes_at)


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
    with unavailable_on_redis_error(VOTE_UNAVAILABLE):
        shard = _counter_shard(dedup_key, counter_shards)
        first_vote = await _reserve_and_increment(
            redis,
            dedup_key=redis_dedup_key,
            counter_key=result_counter_key(question_id, shard),
            ttl=_dedup_ttl(closes_at, current_time),
            option_key=option_key,
        )
        if not first_vote:
            raise AppError(409, "already_voted", "Вы уже проголосовали")

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
