from redis.asyncio import Redis

from app.question.models import QuestionOutput
from app.store.keys import question_cache_key


async def get_cached_question(redis: Redis, question_id: int) -> QuestionOutput | None:
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
    await redis.set(
        question_cache_key(question.id),
        question.model_dump_json(),
    )


async def evict_question(redis: Redis, question_id: int) -> None:
    await redis.delete(question_cache_key(question_id))
