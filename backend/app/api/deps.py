import hmac
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.errors import AppError
from app.config import Settings, get_settings
from app.store.db import get_engine
from app.store.redis import get_redis
from app.vote.journal import VoteJournal, get_journal

DatabaseDep = Annotated[AsyncEngine, Depends(get_engine)]
RedisDep = Annotated[Redis, Depends(get_redis)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
VoteJournalDep = Annotated[VoteJournal, Depends(get_journal)]

_bearer = HTTPBearer(auto_error=False)


async def require_admin(
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> None:
    token = credentials.credentials if credentials is not None else ""
    if not hmac.compare_digest(token.encode(), settings.admin_token.encode()):
        raise AppError(401, "unauthorized", "Нужен токен администратора")
