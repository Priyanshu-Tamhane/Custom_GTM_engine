"""Database engine configuration and session factories."""

from collections.abc import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# Initialize async engine if an async driver is configured
is_async_url = (
    "+asyncpg" in settings.DATABASE_URL
    or "+aiosqlite" in settings.DATABASE_URL
    or "+psycopg_async" in settings.DATABASE_URL
)

if is_async_url:
    async_engine: AsyncEngine | None = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        future=True,
        pool_pre_ping=True,
    )
    async_session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
else:
    async_engine = None
    async_session_factory = None

# Synchronous engine for migrations, worker tasks, and synchronous test fixtures
sync_engine = create_engine(
    settings.SYNC_DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
)

sync_session_factory = sessionmaker(
    bind=sync_engine,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI async dependency yielding an isolated database session."""
    if async_session_factory is None:
        raise RuntimeError("Async session factory is not configured for current DATABASE_URL")
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_sync_db_session() -> Generator[Session, None, None]:
    """Synchronous database session generator for CLI tools and workers."""
    with sync_session_factory() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
