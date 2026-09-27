"""Application-level errors shared by domain and transport layers."""

from collections.abc import Iterator
from contextlib import contextmanager

from redis.exceptions import RedisError


class AppError(Exception):
    """A stable application error that can be rendered by any transport."""

    def __init__(self, status_code: int, error: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.message = message


@contextmanager
def unavailable_on_redis_error(message: str) -> Iterator[None]:
    """Translate Redis failures without hiding an existing application error."""
    try:
        yield
    except AppError:
        raise
    except RedisError as exc:
        raise AppError(503, "unavailable", message) from exc
