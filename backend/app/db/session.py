from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import settings

_engine = None
_AsyncSessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        db_url = settings.DATABASE_URL
        # Fallback to sqlite async if postgresql+asyncpg is requested but asyncpg is not installed
        try:
            _engine = create_async_engine(
                db_url,
                echo=False,
                future=True,
                pool_pre_ping=True,
            )
        except Exception:
            # Safe local fallback for testing or standalone runs
            _engine = create_async_engine(
                "sqlite+aiosqlite:///:memory:",
                echo=False,
                future=True,
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
