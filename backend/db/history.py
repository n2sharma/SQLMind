from backend.db.client import get_pool
from backend.utils.logger import get_logger

logger = get_logger(__name__)


async def save_query(
    question: str,
    generated_sql: str | None,
    rows_returned: int | None,
    execution_time_ms: int | None,
    tokens_used: int | None,
    status: str,
    error_message: str | None,
    retry_count: int,
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO query_history
                (question, generated_sql, rows_returned, execution_time_ms,
                 tokens_used, status, error_message, retry_count)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            question,
            generated_sql,
            rows_returned,
            execution_time_ms,
            tokens_used,
            status,
            error_message,
            retry_count,
        )
        logger.info("query_saved", query_id=str(row["id"]), status=status)
        return str(row["id"])
