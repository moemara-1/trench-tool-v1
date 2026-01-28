"""
Trench Tool V1 - Database Connection Module
Handles PostgreSQL and Redis connections with async support.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.pool import NullPool
import redis.asyncio as redis

from config import settings
from models import Base

logger = logging.getLogger(__name__)


# PostgreSQL Engine
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

# Redis Client
_redis_client: redis.Redis | None = None


async def init_database() -> None:
    """Initialize database connection and create tables."""
    global _engine, _session_factory
    
    logger.info(f"Connecting to database: {settings.database_url.split('@')[-1]}")
    
    _engine = create_async_engine(
        settings.database_url,
        echo=False,  # Set to True for SQL debugging
        poolclass=NullPool,  # Use NullPool for better async handling
    )
    
    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    
    # Create tables if they don't exist
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("Database initialized successfully")


async def close_database() -> None:
    """Close database connection."""
    global _engine
    
    if _engine:
        await _engine.dispose()
        _engine = None
        logger.info("Database connection closed")


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session for use in async with block."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    
    session = _session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI routes."""
    async with get_db_session() as session:
        yield session


# Redis Functions
async def init_redis() -> None:
    """Initialize Redis connection."""
    global _redis_client
    
    logger.info(f"Connecting to Redis: {settings.redis_url}")
    
    _redis_client = redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    
    # Test connection
    await _redis_client.ping()
    logger.info("Redis connected successfully")


async def close_redis() -> None:
    """Close Redis connection."""
    global _redis_client
    
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis connection closed")


def get_redis() -> redis.Redis:
    """Get Redis client instance."""
    if _redis_client is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis_client


# Cache helpers
async def cache_set(key: str, value: str, expire_seconds: int = 300) -> None:
    """Set a value in Redis cache with expiration."""
    r = get_redis()
    await r.setex(key, expire_seconds, value)


async def cache_get(key: str) -> str | None:
    """Get a value from Redis cache."""
    r = get_redis()
    return await r.get(key)


async def cache_delete(key: str) -> None:
    """Delete a key from Redis cache."""
    r = get_redis()
    await r.delete(key)


async def is_rate_limited(key: str, limit: int = 1, window_seconds: int = 60) -> bool:
    """Check if an action is rate limited using Redis."""
    r = get_redis()
    current = await r.incr(key)
    
    if current == 1:
        await r.expire(key, window_seconds)
    
    return current > limit


# Convenience function to get both connections
@asynccontextmanager
async def lifespan_db():
    """Context manager for application lifespan."""
    await init_database()
    await init_redis()
    try:
        yield
    finally:
        await close_database()
        await close_redis()
