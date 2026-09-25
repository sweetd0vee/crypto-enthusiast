from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Секреты и флаги только из окружения. Значения по умолчанию годятся для локального compose."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://poll:poll@localhost:5432/poll"
    redis_url: str = "redis://localhost:6379/0"
    admin_token: str = "dev-admin-token"
    ip_hash_salt: str = "dev-salt"
    counter_shards: int = Field(default=1, ge=1)
    vote_async: bool = False

    @model_validator(mode="after")
    def use_asyncpg_driver(self) -> "Settings":
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url.removeprefix("postgres://")
        if url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url.removeprefix("postgresql://")
        self.database_url = url
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
