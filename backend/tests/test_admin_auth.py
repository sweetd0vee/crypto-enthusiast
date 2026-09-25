import pytest

from app.api.deps import require_admin
from app.api.errors import AppError
from app.config import get_settings


async def test_require_admin_rejects_missing_token() -> None:
    with pytest.raises(AppError) as exc:
        await require_admin(None)

    assert exc.value.status_code == 401
    assert exc.value.error == "unauthorized"


async def test_require_admin_accepts_configured_token() -> None:
    from fastapi.security import HTTPAuthorizationCredentials

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=get_settings().admin_token,
    )
    await require_admin(credentials)
