import hmac
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.errors import AppError
from app.config import get_settings

_bearer = HTTPBearer(auto_error=False)


async def require_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> None:
    settings = get_settings()
    token = credentials.credentials if credentials is not None else ""
    if not hmac.compare_digest(token.encode(), settings.admin_token.encode()):
        raise AppError(401, "unauthorized", "Нужен токен администратора")
