from backend.db.client import get_pool
from backend.utils.logger import get_logger

logger = get_logger(__name__)

CREATE_QUERY_HISTORY = """
CREATE TABLE IF NOT EXISTS query_history (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question         TEXT NOT NULL,
    generated_sql    TEXT,
    rows_returned    INTEGER,
    execution_time_ms INTEGER,
    tokens_used      INTEGER,
    status           TEXT CHECK (status IN ('success', 'error', 'retry_success')),
    error_message    TEXT,
    retry_count      INTEGER DEFAULT 0,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
"""


async def run_migrations():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(CREATE_QUERY_HISTORY)
    logger.info("migrations_complete", table="query_history")
