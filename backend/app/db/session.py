from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import settings

from urllib.parse import urlparse
from app.core.logging_config import logger

_engine = None
_AsyncSessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        db_backend = (settings.DB_BACKEND or "").lower()
        db_url = settings.DATABASE_URL

        if db_backend == "sqlite" or db_url.startswith("sqlite"):
            sqlite_url = "sqlite+aiosqlite:///roadsense_dev.db" if not db_url.startswith("sqlite") else db_url
            logger.info("Database backend selected: SQLITE (target: %s)", sqlite_url)
            _engine = create_async_engine(
                sqlite_url,
                echo=False,
                future=True,
            )
        else:
            # Mask credentials in logs
            try:
                parsed = urlparse(db_url)
                sanitized = f"{parsed.scheme}://{parsed.username}:***@{parsed.hostname}:{parsed.port}{parsed.path}"
            except Exception:
                sanitized = "configured DATABASE_URL"
            logger.info("Database backend selected: POSTGRESQL (target: %s)", sanitized)
            _engine = create_async_engine(
                db_url,
                echo=False,
                future=True,
                pool_pre_ping=True,
            )
    return _engine


def get_session_factory():
    global _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        _AsyncSessionLocal = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _AsyncSessionLocal


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for obtaining async database session."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
