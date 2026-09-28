"""Зависимости FastAPI: синглтоны хранилищ и проверка админского Bearer."""

import hmac
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings, get_settings
from app.errors import AppError
from app.store.db import get_engine
from app.store.redis import get_redis
from app.vote.journal import VoteJournal, get_journal

DatabaseDep = Annotated[AsyncEngine, Depends(get_engine)]
RedisDep = Annotated[Redis, Depends(get_redis)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
VoteJournalDep = Annotated[VoteJournal, Depends(get_journal)]


def get_counter_shards(settings: SettingsDep) -> int:
    """Число шардов счётчика из настроек — прокидывается в result/question сервисы."""
    return settings.counter_shards


CounterShardsDep = Annotated[int, Depends(get_counter_shards)]

_bearer = HTTPBearer(auto_error=False)


async def require_admin(
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> None:
    """Сравнить Bearer с ADMIN_TOKEN за константное время. Неверный или пустой токен — 401.

    `hmac.compare_digest` нужен, чтобы по времени ответа нельзя было подобрать токен.
    `auto_error=False` у HTTPBearer: отсутствие заголовка тоже даёт наш AppError, а не 403 FastAPI.
    """
    token = credentials.credentials if credentials is not None else ""
    if not hmac.compare_digest(token.encode(), settings.admin_token.encode()):
        raise AppError(401, "unauthorized", "Нужен токен администратора")
