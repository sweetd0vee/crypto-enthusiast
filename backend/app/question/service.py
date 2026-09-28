"""Работа с вопросами в админке: создать, прочитать, изменить, удалить.

Данные вопроса лежат в PostgreSQL (таблицы `question` и `question_option`).
После записи копия карточки кладётся в Redis, чтобы форма зрителя не ходила
в базу на каждый запрос. Правила:

- менять варианты ответа нельзя, если по вопросу уже есть голоса;
- удалить можно только черновик, и только если никто ещё не голосовал.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from redis.asyncio import Redis
from sqlalchemy import delete, exists, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.errors import AppError
from app.question.cache import cache_question, evict_question
from app.question.models import (
    OptionInput,
    OptionOutput,
    QuestionCreate,
    QuestionInput,
    QuestionOutput,
    QuestionStatus,
    QuestionUpdate,
    effective_status,
)
from app.store.counter_shards import counter_shards_have_votes, read_counter_shards
from app.store.schema import question, question_option, vote


def _to_output(
    row: Mapping[str, Any],
    options: list[Mapping[str, Any]],
    now: datetime,
) -> QuestionOutput:
    """Превратить сырую строку БД в объект, который отдаём API и кладём в кэш.

    В таблице хранится только «сохранённый» статус: draft / published / cancelled.
    Для экрана дополнительно считаем effective_status на момент `now`:
    published до эфира → scheduled, во время эфира → live, после → closed.
    """
    status = cast(QuestionStatus, row["status"])
    return QuestionOutput(
        id=row["id"],
        name=row["name"],
        status=status,
        effective_status=effective_status(
            status,
            row["show_time"],
            row["duration_seconds"],
            now,
        ),
        show_time=row["show_time"],
        duration_seconds=row["duration_seconds"],
        options=[
            OptionOutput(
                key=option["key"],
                label=option["label"],
                position=option["position"],
            )
            for option in options
        ],
    )


async def _load_one(
    connection: AsyncConnection,
    question_id: int,
    *,
    for_update: bool = False,
) -> QuestionOutput | None:
    """Прочитать один вопрос и все его варианты ответа.

    Возвращает None, если строки с таким id нет. Варианты сортируем по
    `position`, чтобы на форме они шли в том же порядке, что задал админ.

    `for_update=True` добавляет SELECT ... FOR UPDATE: строка блокируется
    до конца транзакции. Так два одновременных update не перезапишут
    друг друга (например, оба решат, что голосов ещё нет, и сменят варианты).
    """
    statement = select(question).where(question.c.id == question_id)
    if for_update:
        statement = statement.with_for_update()
    row = (await connection.execute(statement)).mappings().one_or_none()
    if row is None:
        return None

    option_rows = (
        await connection.execute(
            select(question_option)
            .where(question_option.c.question_id == question_id)
            .order_by(question_option.c.position)
        )
    ).mappings().all()
    return _to_output(row, option_rows, datetime.now(UTC))


def _not_found() -> AppError:
    """Ошибка для клиента: такого вопроса нет. Код `not_found`, HTTP 404."""
    return AppError(404, "not_found", "Вопрос не найден")


def _require_loaded(loaded: QuestionOutput | None, action: str) -> QuestionOutput:
    """Проверка после INSERT/UPDATE: только что записанная строка должна читаться.

    Если её нет — это баг сервера (транзакция, схема), а не «клиент указал
    несуществующий id». Поэтому здесь RuntimeError, а не 404.
    """
    if loaded is None:
        raise RuntimeError(f"{action} question could not be loaded")
    return loaded


async def _load_existing(
    connection: AsyncConnection,
    question_id: int,
    *,
    for_update: bool = False,
) -> QuestionOutput:
    """Прочитать вопрос, который обязан существовать. Нет строки → 404 клиенту."""
    loaded = await _load_one(connection, question_id, for_update=for_update)
    if loaded is None:
        raise _not_found()
    return loaded


def _columns(data: QuestionInput, *, touch: bool = False) -> dict[str, Any]:
    """Словарь колонок таблицы `question` из тела запроса.

    `touch=True` ставим только при update: тогда обновляем `updated_at`,
    чтобы в админке было видно, когда карточку последний раз меняли.
    При создании эти поля заполняет сама база (server_default).
    """
    values: dict[str, Any] = {
        "name": data.name,
        "status": data.status,
        "show_time": data.show_time,
        "duration_seconds": data.duration_seconds,
    }
    if touch:
        values["updated_at"] = datetime.now(UTC)
    return values


async def get_question(engine: AsyncEngine, question_id: int) -> QuestionOutput:
    """Вернуть один вопрос из PostgreSQL.

    Redis здесь намеренно не читаем: админке нужна свежая строка из базы,
    а не кэш, который мог отстать на долю секунды после правки.
    """
    async with engine.connect() as connection:
        return await _load_existing(connection, question_id)


async def list_questions(engine: AsyncEngine) -> list[QuestionOutput]:
    """Список всех вопросов для таблицы админки.

    Два запроса, не N+1: сначала все строки `question`, потом все варианты
    одним `WHERE question_id IN (...)`. Дальше в памяти раскладываем варианты
    по id вопроса и собираем карточки.
    """
    async with engine.connect() as connection:
        question_rows = (
            await connection.execute(select(question).order_by(question.c.id))
        ).mappings().all()
        if not question_rows:
            return []

        question_ids = [row["id"] for row in question_rows]
        option_rows = (
            await connection.execute(
                select(question_option)
                .where(question_option.c.question_id.in_(question_ids))
                .order_by(question_option.c.question_id, question_option.c.position)
            )
        ).mappings().all()

    # Пустые списки нужны заранее: у вопроса может не быть ещё не вставленных
    # вариантов только в теории, но ключ в словаре должен существовать всегда.
    options_by_question: dict[int, list[Mapping[str, Any]]] = {
        question_id: [] for question_id in question_ids
    }
    for option in option_rows:
        options_by_question[option["question_id"]].append(option)

    now = datetime.now(UTC)
    return [
        _to_output(row, options_by_question[row["id"]], now)
        for row in question_rows
    ]


async def _write_options(
    connection: AsyncConnection,
    question_id: int,
    options: list[OptionInput],
) -> None:
    """Вставить варианты ответа пачкой. Сама функция старые строки не трогает.

    При создании вопроса старых строк нет — просто INSERT.
    При update вызывающий сначала делает DELETE всех вариантов этого вопроса,
    и только потом вызывает эту функцию. `position` = индекс в списке
    (0, 1, 2…), чтобы порядок на форме совпадал с порядком в запросе.
    """
    await connection.execute(
        insert(question_option),
        [
            {
                "question_id": question_id,
                "key": option.key,
                "label": option.label,
                "position": position,
            }
            for position, option in enumerate(options)
        ],
    )


async def create_question(
    engine: AsyncEngine,
    redis: Redis,
    data: QuestionCreate,
) -> QuestionOutput:
    """Создать новый вопрос.

    Шаги:
    1. В одной транзакции пишем строку вопроса и все варианты.
       Если второй INSERT упадёт — откатится и первый, полувопроса не будет.
    2. Сразу читаем записанное обратно, чтобы вернуть клиенту id и
       посчитанный effective_status.
    3. После commit кладём карточку в Redis: форма зрителя сможет взять
       её из кэша, не ходя в PostgreSQL.
    """
    async with engine.begin() as connection:
        question_id = (
            await connection.execute(
                insert(question).values(**_columns(data)).returning(question.c.id)
            )
        ).scalar_one()
        await _write_options(connection, question_id, data.options)
        created = _require_loaded(await _load_one(connection, question_id), "created")

    await cache_question(redis, created)
    return created


def _same_options(current: list[OptionOutput], incoming: list[OptionInput]) -> bool:
    """True, если набор вариантов не изменился.

    Сравниваем только пары (ключ, подпись) в том же порядке. Ключ — то, что
    пишется в счётчик Redis (`yes`/`no`). Если его сменить при уже набранных
    голосах, цифры окажутся у «чужого» варианта. Порядок тоже часть сравнения:
    перестановка считается изменением и тоже блокируется, если голоса есть.
    """
    return [(item.key, item.label) for item in current] == [
        (item.key, item.label) for item in incoming
    ]


async def _has_votes(
    connection: AsyncConnection,
    redis: Redis,
    question_id: int,
    counter_shards: int,
) -> bool:
    """Проверить, голосовал ли уже хоть кто-то по этому вопросу.

    Смотрим в двух местах, потому что голос сначала попадает в Redis, а в
    таблицу `vote` может доехать чуть позже (или вообще потеряться из очереди):

    1. PostgreSQL: есть ли хотя бы одна строка в журнале `vote`.
    2. Redis: есть ли в шардах счётчика поле со значением больше нуля.

    Пустой hash (ключ есть, но все нули / полей нет) голосами не считаем.
    Иначе только что опубликованный опрос нельзя было бы поправить, пока
    счётчики ещё пустые.
    """
    in_database = await connection.scalar(
        select(exists().where(vote.c.question_id == question_id))
    )
    if in_database:
        return True
    shards = await read_counter_shards(redis, question_id, counter_shards)
    return counter_shards_have_votes(shards)


async def update_question(
    engine: AsyncEngine,
    redis: Redis,
    question_id: int,
    data: QuestionUpdate,
    counter_shards: int,
) -> QuestionOutput:
    """Изменить существующий вопрос: текст, время эфира, статус, варианты.

    Шаги внутри транзакции:
    1. Читаем текущую карточку с блокировкой строки (FOR UPDATE). Пока
       транзакция не закончится, второй админ будет ждать — так нельзя
       одновременно сменить варианты, пока первый ещё проверяет голоса.
    2. Сравниваем старые и новые варианты. Название и время эфира можно
       менять всегда. Варианты — только если никто ещё не голосовал.
    3. Если варианты другие и голоса уже есть → 409 options_locked.
       Иначе счётчики Redis (`yes=1200`) указывали бы на ключ, которого
       в вопросе больше нет.
    4. UPDATE полей вопроса. Если варианты изменились — DELETE старых
       строк и INSERT новых (проще, чем точечно править каждую).
    5. После commit перезаписываем кэш Redis свежей карточкой.
    """
    async with engine.begin() as connection:
        current = await _load_existing(connection, question_id, for_update=True)
        options_changed = not _same_options(current.options, data.options)
        if options_changed and await _has_votes(
            connection,
            redis,
            question_id,
            counter_shards,
        ):
            raise AppError(
                409,
                "options_locked",
                "Нельзя менять варианты после появления голосов",
            )

        await connection.execute(
            update(question)
            .where(question.c.id == question_id)
            .values(**_columns(data, touch=True))
        )
        if options_changed:
            await connection.execute(
                delete(question_option).where(question_option.c.question_id == question_id)
            )
            await _write_options(connection, question_id, data.options)
        updated = _require_loaded(await _load_one(connection, question_id), "updated")

    await cache_question(redis, updated)
    return updated


async def delete_question(
    engine: AsyncEngine,
    redis: Redis,
    question_id: int,
    counter_shards: int,
) -> None:
    """Удалить вопрос. Разрешено только для черновика, по которому ещё никто не голосовал.

    Опубликованный, отменённый или уже голосованный вопрос трогать нельзя:
    иначе исчезнут и журнал, и смысл счётчиков. Варианты удалятся сами
    (ON DELETE CASCADE). После успешного DELETE убираем карточку из Redis,
    чтобы форма зрителя не продолжала показывать удалённый опрос.
    """
    async with engine.begin() as connection:
        current = await _load_existing(connection, question_id, for_update=True)
        if current.status != "draft" or await _has_votes(
            connection,
            redis,
            question_id,
            counter_shards,
        ):
            raise AppError(
                409,
                "delete_forbidden",
                "Можно удалить только черновик без голосов",
            )
        await connection.execute(delete(question).where(question.c.id == question_id))

    await evict_question(redis, question_id)
