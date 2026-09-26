"""Чтение публичной формы и горячий путь приёма голоса."""

import asyncio
import hashlib
import json
import logging
import math
import zlib
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.errors import AppError
from app.question.service import QuestionOutput, get_question
from app.store.schema import vote

JOURNAL_BATCH_SIZE = 1000
JOURNAL_FLUSH_INTERVAL_SECONDS = 0.05
JOURNAL_QUEUE_SIZE = 10_000
DEDUP_TTL_MARGIN_SECONDS = 86_400

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VoteEvent:
    question_id: int
    option_key: str
    dedup_key: str
    ip_hash: str
    voted_at: datetime

    def as_row(self) -> dict[str, object]:
        return {
            "question_id": self.question_id,
            "option_key": self.option_key,
            "dedup_key": self.dedup_key,
            "ip_hash": self.ip_hash,
            "voted_at": self.voted_at,
        }


@dataclass(frozen=True, slots=True)
class PublicQuestion:
    id: int
    name: str
    closes_at: datetime
    options: list[dict[str, str]]


class VoteJournal:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._queue: asyncio.Queue[VoteEvent] = asyncio.Queue(JOURNAL_QUEUE_SIZE)
        self._worker: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._run(), name="vote-journal")

    async def close(self) -> None:
        if self._worker is None:
            return
        await self._queue.join()
        self._worker.cancel()
        with suppress(asyncio.CancelledError):
            await self._worker
        self._worker = None

    def enqueue(self, event: VoteEvent) -> None:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.error("vote journal queue is full; event dropped")

    async def write(self, event: VoteEvent) -> None:
        await self._write_batch([event])

    async def _write_batch(self, events: list[VoteEvent]) -> None:
        statement = insert(vote).values([event.as_row() for event in events])
        statement = statement.on_conflict_do_nothing(
            index_elements=[vote.c.question_id, vote.c.dedup_key]
        )
        async with self._engine.begin() as connection:
            await connection.execute(statement)

    async def _run(self) -> None:
        while True:
            first = await self._queue.get()
            batch = [first]
            deadline = asyncio.get_running_loop().time() + JOURNAL_FLUSH_INTERVAL_SECONDS
            try:
                while len(batch) < JOURNAL_BATCH_SIZE:
                    timeout = deadline - asyncio.get_running_loop().time()
                    if timeout <= 0:
                        break
                    try:
                        batch.append(await asyncio.wait_for(self._queue.get(), timeout))
                    except TimeoutError:
                        break
                await self._write_batch(batch)
            except Exception:
                logger.exception("failed to write vote journal batch")
            finally:
                for _ in batch:
                    self._queue.task_done()


_journal: VoteJournal | None = None


def init_journal(engine: AsyncEngine, *, asynchronous: bool) -> VoteJournal:
    global _journal
    _journal = VoteJournal(engine)
    if asynchronous:
        _journal.start()
    return _journal


def get_journal() -> VoteJournal:
    if _journal is None:
        raise RuntimeError("vote journal is not initialized")
    return _journal


async def close_journal() -> None:
    global _journal
    if _journal is not None:
        await _journal.close()
        _journal = None


def dedup_hash(question_id: int, viewer_id: str) -> str:
    return hashlib.sha256(f"{question_id}|{viewer_id}".encode()).hexdigest()


def client_ip_hash(client_ip: str, salt: str) -> str:
    return hashlib.sha256(f"{client_ip}|{salt}".encode()).hexdigest()


async def _load_question(
    engine: AsyncEngine,
    redis: Redis,
    question_id: int,
) -> QuestionOutput:
    cache_key = f"question:{question_id}"
    try:
        cached = await redis.get(cache_key)
        if cached is not None:
            try:
                return QuestionOutput.model_validate_json(cached)
            except ValueError:
                await redis.delete(cache_key)

        loaded = await get_question(engine, question_id)
        await redis.set(
            cache_key,
            json.dumps(loaded.model_dump(mode="json"), ensure_ascii=False),
        )
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
    try:
        if await redis.exists(f"vote:{question_id}:{dedup_hash(question_id, viewer_id)}"):
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
    redis_dedup_key = f"vote:{question_id}:{dedup_key}"
    ttl = math.ceil((closes_at - current_time).total_seconds()) + DEDUP_TTL_MARGIN_SECONDS
    try:
        first_vote = await redis.set(redis_dedup_key, "1", ex=ttl, nx=True)
        if not first_vote:
            raise AppError(409, "already_voted", "Вы уже проголосовали")
        shard = zlib.crc32(dedup_key.encode()) % counter_shards
        await redis.hincrby(f"results:{question_id}:{shard}", option_key, 1)
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
