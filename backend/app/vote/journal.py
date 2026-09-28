"""Копия принятых голосов в PostgreSQL (таблица `vote`).

Голос уже засчитан в Redis. Журнал нужен, чтобы потом пересчитать итоги
и чтобы остался след «кто (хеш) что нажал». Два режима:

- VOTE_ASYNC=false (по умолчанию, удобно локально): каждый голос сразу
  INSERT в базу. Проще отлаживать, медленнее на пике.
- VOTE_ASYNC=true: голос кладётся в очередь процесса, фоновый воркер
  пишет пачками до 1000 строк. Быстрее, но при переполнении очереди
  событие теряется — счётчик Redis при этом уже увеличен.
"""

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
    """Либо пишем строку сразу (`write`), либо копим в очереди (`enqueue`)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        # Ограниченная очередь: если воркер не успевает, новые события
        # не копятся бесконечно в памяти, а начинают отбрасываться.
        self._queue: asyncio.Queue[VoteEvent] = asyncio.Queue(JOURNAL_QUEUE_SIZE)
        self._worker: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Запустить фоновый цикл `_run`. Вызывается только при VOTE_ASYNC=true."""
        if self._worker is None:
            self._worker = asyncio.create_task(self._run(), name="vote-journal")

    async def close(self) -> None:
        """При остановке API: дождаться, пока очередь опустеет, затем убить воркер.

        `join()` ждёт, пока для каждого put вызовут `task_done`. Поэтому даже
        пачка, которая ещё пишется, должна завершиться (успех или лог ошибки).
        """
        if self._worker is None:
            return
        await self._queue.join()
        self._worker.cancel()
        with suppress(asyncio.CancelledError):
            await self._worker
        self._worker = None

    def enqueue(self, event: VoteEvent) -> None:
        """Положить событие в очередь и сразу вернуть управление зрителю.

        Не ждём, пока строка окажется в PostgreSQL. Если очередь забита
        (воркер отстал на 10 000 событий), голос в журнале не появится.
        В Redis он уже есть — для live-цифр это не страшно, для rebuild
        этот один голос пропадёт.
        """
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.error("vote journal queue is full; event dropped")

    async def write(self, event: VoteEvent) -> None:
        """Записать одно событие сразу. Режим без очереди."""
        await self._write_batch([event])

    async def _write_batch(self, events: list[VoteEvent]) -> None:
        """INSERT пачки строк в `vote`.

        `ON CONFLICT DO NOTHING` по (question_id, dedup_key): уникальность
        зрителя уже обеспечил Redis. Повтор в журнале — либо гонка двух
        записей, либо воркер повторно доставил пачку. Второй голос это не
        создаёт, строка просто игнорируется.
        """
        statement = insert(vote).values([event.as_row() for event in events])
        statement = statement.on_conflict_do_nothing(
            index_elements=[vote.c.question_id, vote.c.dedup_key]
        )
        async with self._engine.begin() as connection:
            await connection.execute(statement)

    async def _run(self) -> None:
        """Бесконечный цикл воркера: взять пачку → записать → отметить очередь.

        `task_done` вызываем даже если INSERT упал. Иначе `close()` навсегда
        зависнет в `join()`, а события всё равно уже не спасти.
        """
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
        """Собрать пачку: минимум 1 событие, максимум 1000, либо 50 мс ожидания.

        Ждём первое событие сколько угодно (очередь пустая — воркер спит).
        Дальше либо быстро добираем до 1000, либо через 50 мс отправляем
        сколько успели. Так и пик не копится по одному INSERT, и маленькая
        нагрузка не ждёт полную тысячу.
        """
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
    """Создать один журнал на процесс. Воркер стартует только в async-режиме."""
    global _journal
    _journal = VoteJournal(engine)
    if asynchronous:
        _journal.start()
    return _journal


def get_journal() -> VoteJournal:
    """Отдать журнал обработчикам FastAPI. Если lifespan ещё не отработал — это баг."""
    if _journal is None:
        raise RuntimeError("vote journal is not initialized")
    return _journal


async def close_journal() -> None:
    """Остановить воркер и забыть синглтон при выключении приложения."""
    global _journal
    if _journal is not None:
        await _journal.close()
        _journal = None
