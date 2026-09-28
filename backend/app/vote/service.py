"""Публичная форма опроса и приём голоса зрителя.

Зритель открывает ссылку / QR, видит вопрос и нажимает вариант. Регистрации нет.
Повторный голос того же браузера отсекаем по cookie `vid`: из неё считаем
хеш и кладём ключ в Redis. Это базовая защита, не криптостойкая — cookie
можно подменить, но обычный зритель так не сделает.

Почему Redis, а не сразу PostgreSQL: на пике эфира миллионы кликов за минуту.
Redis атомарно помечает «этот зритель уже голосовал» и увеличивает счётчик.
PostgreSQL получает копию события позже (журнал) — для аудита и пересчёта.
"""

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
    """Всё, что нужно и форме, и приёму голоса, собрано один раз.

    question         — карточка опроса (текст и варианты)
    closes_at        — момент, после которого голосовать нельзя (не включая его)
    dedup_key        — хеш «вопрос + зритель», без самого cookie
    redis_dedup_key  — имя ключа в Redis, например vote:42:abc123...
    """

    question: QuestionOutput
    closes_at: datetime
    dedup_key: str
    redis_dedup_key: str


def dedup_hash(question_id: int, viewer_id: str) -> str:
    """Сделать отпечаток зрителя внутри конкретного вопроса.

    В Redis и в журнал не кладём сырой cookie `vid`. Хешируем пару
    «id вопроса | id зрителя»: тот же браузер по тому же опросу всегда
    даст одну строку, другой опрос — другую. Повторный клик найдёт
    уже существующий ключ и получит «вы уже голосовали».
    """
    return hashlib.sha256(f"{question_id}|{viewer_id}".encode()).hexdigest()


def client_ip_hash(client_ip: str, salt: str) -> str:
    """Обезличить IP перед записью в журнал.

    IP не решает, первый это голос или повтор: уникальность только по cookie.
    Хеш с солью нужен на случай разбора инцидента, чтобы по журналу нельзя
    было восстановить исходный адрес.
    """
    return hashlib.sha256(f"{client_ip}|{salt}".encode()).hexdigest()


# Старое имя для внутренних импортов / тестов, логика та же.
_reserve_and_increment = reserve_viewer_and_increment_counter


async def _load_question(
    engine: AsyncEngine,
    redis: Redis,
    question_id: int,
) -> QuestionOutput:
    """Достать карточку вопроса как можно быстрее.

    Сначала Redis (кэш после создания/правки). Если ключа нет — идём в
    PostgreSQL и сразу кладём результат обратно в Redis, чтобы следующие
    зрители эфира уже не трогали базу.

    Если Redis лежит, не притворяемся, что вопроса нет: зритель должен
    получить 503 «сервис недоступен», а не пустую страницу.
    """
    with unavailable_on_redis_error(VOTE_UNAVAILABLE):
        cached = await get_cached_question(redis, question_id)
        if cached is not None:
            return cached

        loaded = await get_question(engine, question_id)
        await cache_question(redis, loaded)
        return loaded


_check_window = require_open_voting_window


def _public_question(question: QuestionOutput, closes_at: datetime) -> PublicQuestion:
    """То, что можно показать зрителю на телефоне.

    Убираем админские поля: сохранённый статус, cookie, IP, хеши.
    Оставляем текст, время закрытия и кнопки вариантов.
    """
    return PublicQuestion(
        id=question.id,
        name=question.name,
        closes_at=closes_at,
        options=[OptionInput(key=option.key, label=option.label) for option in question.options],
    )


def _dedup_ttl(closes_at: datetime, now: datetime) -> int:
    """Сколько секунд держать в Redis пометку «этот зритель уже голосовал».

    Берём оставшееся время окна и плюс сутки. Запас нужен, чтобы после
    закрытия эфира ключ не истёк сразу: иначе тот же человек обновит
    страницу и сможет проголосовать ещё раз, пока админка ещё читает счётчики.
    """
    remaining = math.ceil((closes_at - now).total_seconds())
    return remaining + DEDUP_TTL_MARGIN_SECONDS


def _counter_shard(dedup_key: str, counter_shards: int) -> int:
    """Выбрать, в какой кусок Redis-счётчика писать этот голос.

    Счётчик разбит на несколько hash-ключей (шардов), чтобы миллионы
    одновременных HINCRBY не бились в одну запись. Номер шарда считаем
    из хеша зрителя: один и тот же человек всегда попадает в один шард,
    разные люди равномерно размазываются по всем.
    """
    return zlib.crc32(dedup_key.encode()) % counter_shards


async def _vote_context(
    engine: AsyncEngine,
    redis: Redis,
    question_id: int,
    viewer_id: str,
    now: datetime,
) -> _VoteContext:
    """Общая подготовка и для показа формы, и для приёма голоса.

    1. Загрузить вопрос (кэш или база).
    2. Проверить, что эфир уже начался и ещё не закончился. Если нет —
       здесь же улетит 403/410, дальше код не пойдёт.
    3. Посчитать ключи дедупа, чтобы потом одним EXISTS или Lua проверить,
       голосовал ли уже этот браузер.
    """
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
    """Отдать форму голосования.

    Показываем вопрос только если:
    - он опубликован и сейчас внутри минуты эфира;
    - этот браузер ещё не голосовал (в Redis нет дедуп-ключа).

    Уже проголосовавший получает 409 и форму не видит: повторный заход
    по QR не должен предлагать второй клик.
    """
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
    """Принять один клик зрителя.

    Голос считается принятым в момент успешного Lua в Redis. Журнал в
    PostgreSQL — копия «на потом», не источник истины на пике.

    Шаги по порядку (менять нельзя):

    1. Загрузить вопрос и проверить окно эфира.
    2. Проверить, что нажатый вариант вообще есть в вопросе.
       Это делается ДО Redis. Если проверить после, злонамеренный запрос
       с ключом `asdf` поставил бы дедуп-ключ, и настоящий вариант
       («да»/«нет») этот зритель выбрать бы уже не смог.
    3. Одна команда Redis (Lua):
       - ключ дедупа уже есть → это повтор, вернём 409, счётчик не трогаем;
       - ключа нет → ставим его и увеличиваем счётчик выбранного варианта.
    4. Пишем событие в журнал. Если PostgreSQL в этот момент упал,
       Redis уже посчитал голос — откатывать его не будем, в лог пишем ошибку.
       При VOTE_ASYNC=true событие кладётся в очередь процесса и пишется пачкой.
    """
    current_time = now or datetime.now(UTC)
    context = await _vote_context(engine, redis, question_id, viewer_id, current_time)

    # Неизвестный вариант отклоняем до любой записи в Redis.
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
