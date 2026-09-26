import asyncio
import logging
from contextlib import suppress

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.store.schema import vote
from app.vote.models import VoteEvent

JOURNAL_BATCH_SIZE = 1000
JOURNAL_FLUSH_INTERVAL_SECONDS = 0.05
JOURNAL_QUEUE_SIZE = 10_000

logger = logging.getLogger(__name__)


class VoteJournal:
    """Writes accepted votes immediately or through one bounded batch worker."""

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
            batch = await self._next_batch()
            try:
                await self._write_batch(batch)
            except Exception:
                logger.exception("failed to write vote journal batch")
            finally:
                for _ in batch:
                    self._queue.task_done()

    async def _next_batch(self) -> list[VoteEvent]:
        batch = [await self._queue.get()]
        deadline = asyncio.get_running_loop().time() + JOURNAL_FLUSH_INTERVAL_SECONDS
        while len(batch) < JOURNAL_BATCH_SIZE:
            timeout = deadline - asyncio.get_running_loop().time()
            if timeout <= 0:
                break
            try:
                batch.append(await asyncio.wait_for(self._queue.get(), timeout))
            except TimeoutError:
                break
        return batch


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
