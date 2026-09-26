import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.admin import router as admin_router
from app.api.errors import install_error_handlers
from app.api.public import router as public_router
from app.config import get_settings
from app.store.db import close_engine, init_engine
from app.store.db import ping as ping_db
from app.store.redis import close_redis, init_redis
from app.store.redis import ping as ping_redis
from app.vote.service import close_journal, init_journal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engine = init_engine(settings.database_url)
    init_redis(settings.redis_url)
    init_journal(engine, asynchronous=settings.vote_async)
    logger.info("api started")
    yield
    await close_journal()
    await close_redis()
    await close_engine()
    logger.info("api stopped")


app = FastAPI(title="TV poll", lifespan=lifespan)
install_error_handlers(app)
app.include_router(public_router)
app.include_router(admin_router)


@app.get("/healthz")
async def healthz() -> JSONResponse:
    try:
        await ping_db()
        await ping_redis()
    except Exception as exc:
        logger.warning("health check failed: %s", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={"error": "unavailable", "message": "Хранилище недоступно"},
        )
    return JSONResponse(status_code=200, content={"status": "ok"})
