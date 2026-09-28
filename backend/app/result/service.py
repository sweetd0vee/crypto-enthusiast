"""Итоги опроса для админки.

На пике эфира цифры живут в Redis: каждый голос делает HINCRBY в один из
шардов (кусков) счётчика. Админка просто складывает шарды — без тяжёлого
GROUP BY по миллионам строк.

Таблица `vote` — журнал «кто что нажал». Из него можно заново собрать
итог (rebuild), если Redis потерял ключи или эфир уже закончился.
Таблица `question_result` — снимок последнего rebuild, не live-цифры.
"""

from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.errors import unavailable_on_redis_error
from app.question.models import QuestionOutput
from app.question.service import get_question
from app.result.models import OptionCount, QuestionResult
from app.store.counter_shards import aggregate_counter_shards, read_counter_shards
from app.store.keys import result_counter_keys
from app.store.schema import question_result, vote

COUNTERS_UNAVAILABLE = "Счётчики временно недоступны"


async def _journal_counts(connection: AsyncConnection, question_id: int) -> dict[str, int]:
    """Посчитать голоса из журнала: сколько строк на каждый вариант.

    Это медленный путь (GROUP BY по таблице vote). На live-эфире его не
    вызываем. Вариант, за который никто не голосовал, в словаре не появится —
    нули подставим позже, когда соберём ответ.
    """
    rows = (
        await connection.execute(
            select(vote.c.option_key, func.count().label("count"))
            .where(vote.c.question_id == question_id)
            .group_by(vote.c.option_key)
        )
    ).all()
    return {option_key: count for option_key, count in rows}


async def _store_snapshot(
    connection: AsyncConnection,
    question: QuestionOutput,
    counts: dict[str, int],
    rebuilt_at: datetime,
) -> None:
    """Записать снимок итогов в PostgreSQL.

    Сначала удаляем старый снимок этого вопроса, потом вставляем по строке
    на каждый вариант. Даже если за вариант 0 голосов — строка всё равно
    будет, чтобы в админке не пропадали кнопки.
    """
    await connection.execute(
        delete(question_result).where(question_result.c.question_id == question.id)
    )
    await connection.execute(
        insert(question_result),
        [
            {
                "question_id": question.id,
                "option_key": option.key,
                "count": counts.get(option.key, 0),
                "rebuilt_at": rebuilt_at,
            }
            for option in question.options
        ],
    )


async def _replace_counters(
    redis: Redis,
    question: QuestionOutput,
    counts: dict[str, int],
    counter_shards: int,
) -> None:
    """Подменить live-счётчики Redis результатом пересчёта из журнала.

    Удаляем все шарды и пишем суммы в шард 0. На пике эфира так делать
    нельзя (параллельный HINCRBY потеряется), но rebuild — редкая операция
    после эфира, поэтому одного атомарного pipeline достаточно.
    """
    keys = result_counter_keys(question.id, counter_shards)
    with unavailable_on_redis_error(COUNTERS_UNAVAILABLE):
        pipeline = redis.pipeline(transaction=True)
        pipeline.delete(*keys)
        pipeline.hset(
            keys[0],
            mapping={option.key: counts.get(option.key, 0) for option in question.options},
        )
        await pipeline.execute()


async def _read_counters(
    redis: Redis,
    question_id: int,
    counter_shards: int,
) -> tuple[bool, dict[str, int]]:
    """Прочитать все шарды и сложить одинаковые варианты.

    Возвращает пару:
    - нашлись ли ключи вообще (пустой словарь {} значит «ключа не было»);
    - суммы по вариантам.

    `any(shards)` ложно, если Redis вернул только пустые hash. Тогда
    get_results может решить пересобрать итог из журнала.
    """
    with unavailable_on_redis_error(COUNTERS_UNAVAILABLE):
        shards = await read_counter_shards(redis, question_id, counter_shards)
    return any(shards), aggregate_counter_shards(shards)


def _response(question: QuestionOutput, counts: dict[str, int]) -> QuestionResult:
    """Собрать JSON для админки: у каждого варианта цифра, total — их сумма.

    Если варианта не было в Redis/журнале, показываем 0, а не прячем кнопку.
    """
    options = [
        OptionCount(
            key=option.key,
            label=option.label,
            count=counts.get(option.key, 0),
        )
        for option in question.options
    ]
    return QuestionResult(
        question_id=question.id,
        name=question.name,
        effective_status=question.effective_status,
        total=sum(option.count for option in options),
        counts=options,
    )


async def rebuild_results(
    engine: AsyncEngine,
    redis: Redis,
    question_id: int,
    counter_shards: int,
) -> QuestionResult:
    """Полный пересчёт итогов из журнала vote.

    Когда это нужно: Redis потерял ключи, эфир закончился, админ нажал
    «пересчитать». Шаги:
    1. Взять карточку вопроса (какие вообще есть варианты).
    2. GROUP BY по журналу — сколько строк на каждый ключ.
    3. Записать снимок в `question_result`.
    4. Заменить шарды Redis этим снимком.
    5. Вернуть те же цифры админке.
    """
    question = await get_question(engine, question_id)
    async with engine.begin() as connection:
        counts = await _journal_counts(connection, question_id)
        await _store_snapshot(connection, question, counts, datetime.now(UTC))

    await _replace_counters(redis, question, counts, counter_shards)
    return _response(question, counts)


async def get_results(
    engine: AsyncEngine,
    redis: Redis,
    question_id: int,
    counter_shards: int,
) -> QuestionResult:
    """Показать текущие итоги.

    Если эфир идёт (live) — только Redis, без GROUP BY: иначе админка
    положила бы базу на пике.

    Если ключей в Redis нет и эфир уже не live (ещё не начался / закончился) —
    один раз пересобираем из журнала. Иначе закрытый опрос с истёкшим TTL
    счётчиков выглядел бы как нули, хотя голоса в журнале есть.

    Live без ключей не пересобираем: на старте эфира счётчики ещё пустые,
    это нормально, не повод гонять GROUP BY.
    """
    question = await get_question(engine, question_id)
    found, counts = await _read_counters(redis, question_id, counter_shards)
    if not found and question.effective_status != "live":
        return await rebuild_results(engine, redis, question_id, counter_shards)
    return _response(question, counts)
