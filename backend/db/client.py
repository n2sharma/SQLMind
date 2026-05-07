import asyncpg
from backend.config import get_settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)
_pool = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_pool() first.")
    return _pool


async def init_pool():
    global _pool
    settings = get_settings()
    _pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=2,
        max_size=10,
    )
    logger.info("database_pool_initialized", dsn=settings.database_url)


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        logger.info("database_pool_closed")
