"""
Async database engine + session factory.
Handles Render's postgres:// → postgresql+asyncpg:// URL conversion.
init_db() is called at application startup to auto-run migrations.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.models import Base
from app.utils.config import get_settings
from app.utils.logger import get_logger

logger = get_logger("db.session")

_engine: AsyncEngine | None = None
_AsyncSessionLocal: async_sessionmaker | None = None


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.async_database_url   # already fixed for asyncpg
        _engine = create_async_engine(
            url,
            echo=settings.debug,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=300,   # shorter on Render — connections can drop
        )
    return _engine


def _get_session_factory() -> async_sessionmaker:
    global _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        _AsyncSessionLocal = async_sessionmaker(
            _get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _AsyncSessionLocal


async def init_db() -> None:
    """
    Create all tables that don't exist yet.
    Called automatically on startup — safe to call multiple times.
    """
    engine = _get_engine()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables ready")
    except Exception as exc:
        logger.error(f"DB init error (non-fatal): {exc}")


async def close_db() -> None:
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
        logger.info("DB pool closed")


async def get_session() -> AsyncSession:   # type: ignore[return]
    """FastAPI dependency — yields one session per request."""
    factory = _get_session_factory()
    async with factory() as session:
        yield session
