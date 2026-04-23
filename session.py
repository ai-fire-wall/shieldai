"""
Async database engine + session factory.
init_db() is called at application startup.
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
settings = get_settings()

# Singleton engine — created once at module import
_engine: AsyncEngine | None = None
_AsyncSessionLocal: async_sessionmaker | None = None


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,       # detect stale connections
            pool_recycle=3600,        # recycle connections every hour
        )
    return _engine


def _get_session_factory() -> async_sessionmaker:
    global _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        _AsyncSessionLocal = async_sessionmaker(
            _get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _AsyncSessionLocal


async def init_db() -> None:
    """
    Create all tables that don't exist yet.
    In production: run `alembic upgrade head` instead.
    """
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified / created")


async def close_db() -> None:
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
        logger.info("Database connection pool closed")


async def get_session() -> AsyncSession:  # type: ignore[return]
    """FastAPI dependency — yields one session per request."""
    factory = _get_session_factory()
    async with factory() as session:
        yield session


async def get_session_ctx() -> AsyncSession:
    """Non-dependency context manager for background tasks."""
    factory = _get_session_factory()
    return factory()
