from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_engine: AsyncEngine | None = None


def init_engine(url: str) -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(url, pool_pre_ping=True)
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("database engine is not initialized")
    return _engine


async def close_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def ping() -> None:
    engine = get_engine()
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
