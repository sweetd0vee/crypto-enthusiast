from app.config import Settings, get_settings


def test_plain_postgres_url_uses_asyncpg(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://poll:poll@db:5432/poll")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.database_url == "postgresql+asyncpg://poll:poll@db:5432/poll"
    finally:
        get_settings.cache_clear()


def test_counter_shards_default() -> None:
    settings = Settings(database_url="postgresql+asyncpg://poll:poll@localhost/poll")
    assert settings.counter_shards == 1
