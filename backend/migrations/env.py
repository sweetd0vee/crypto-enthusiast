import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None
VERSION_SCHEMA = "alembic"


def _database_url() -> str:
    return get_settings().database_url


def _configure(**extra: object) -> None:
    context.configure(
        target_metadata=target_metadata,
        version_table_schema=VERSION_SCHEMA,
        **extra,
    )


def _ensure_version_schema(connection: Connection) -> None:
    connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {VERSION_SCHEMA}"))
    connection.execute(
        text(
            f"""
            DO $$
            BEGIN
                IF to_regclass('public.alembic_version') IS NOT NULL
                   AND to_regclass('{VERSION_SCHEMA}.alembic_version') IS NULL THEN
                    ALTER TABLE public.alembic_version SET SCHEMA {VERSION_SCHEMA};
                END IF;
            END
            $$;
            """
        )
    )
    connection.commit()


def run_migrations_offline() -> None:
    _configure(url=_database_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    _ensure_version_schema(connection)
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = async_engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
