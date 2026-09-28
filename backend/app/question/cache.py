"""Кэш карточки вопроса в Redis. Ключ: `question:{id}`.

Зачем: на пике эфира миллионы людей открывают один и тот же QR. Если каждый
раз читать PostgreSQL, база не выдержит. Карточка почти не меняется во время
эфира, поэтому храним её JSON в Redis.

Когда обновляем: после create/update вопроса. Когда удаляем ключ: после
delete, иначе форма ещё какое-то время показывала бы удалённый опрос.
"""

from redis.asyncio import Redis

from app.question.models import QuestionOutput
from app.store.keys import question_cache_key


async def get_cached_question(redis: Redis, question_id: int) -> QuestionOutput | None:
    """Попытаться взять карточку из Redis.

    None значит «кэша нет, иди в базу»:
    - ключа никогда не было;
    - или JSON битый (старая версия схемы, ручная правка).
      Битый ключ удаляем, иначе зритель навсегда получал бы ошибку разбора.
    """
    key = question_cache_key(question_id)
    cached = await redis.get(key)
    if cached is None:
        return None
    try:
        return QuestionOutput.model_validate_json(cached)
    except ValueError:
        await redis.delete(key)
        return None


async def cache_question(redis: Redis, question: QuestionOutput) -> None:
    """Сохранить актуальную карточку. Вызывается после создания и правки."""
    await redis.set(
        question_cache_key(question.id),
        question.model_dump_json(),
    )


async def evict_question(redis: Redis, question_id: int) -> None:
    """Удалить кэш. Вызывается после delete_question."""
    await redis.delete(question_cache_key(question_id))
