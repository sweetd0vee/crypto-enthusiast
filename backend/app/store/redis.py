"""Синглтон Redis-клиента. `decode_responses=True` — ключи и значения приходят строками."""

from redis.asyncio import Redis

_client: Redis | None = None


def init_redis(url: str) -> Redis:
    """Подключить клиент один раз на процесс. Повторный вызов не создаёт второй сокет."""
    global _client
    if _client is None:
        _client = Redis.from_url(url, decode_responses=True)
    return _client


def get_redis() -> Redis:
    """Клиент для зависимостей FastAPI. Без init_redis — ошибка старта, не ответ зрителю."""
    if _client is None:
        raise RuntimeError("redis client is not initialized")
    return _client


async def close_redis() -> None:
    """Закрыть соединение при shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def ping() -> None:
    """PING Redis для /healthz."""
    client = get_redis()
    await client.ping()
