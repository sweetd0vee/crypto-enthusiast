from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.errors import AppError, unavailable_on_redis_error

__all__ = ["AppError", "install_error_handlers", "unavailable_on_redis_error"]


def install_error_handlers(app: FastAPI) -> None:
    """Единый JSON для AppError и для невалидного тела: `{error, message}`."""
    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        """Доменные ошибки (409, 403, 410, 401…) в одном контракте `{error, message}`."""
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error, "message": exc.message},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request,
        _exc: RequestValidationError,
    ) -> JSONResponse:
        """Ошибку Pydantic не светим наружу: всегда invalid_body, без полей валидации."""
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_body", "message": "Некорректное тело запроса"},
        )
