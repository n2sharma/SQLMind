import asyncpg
import time
from backend.config import get_settings
from backend.utils.sql_safety import add_limit_if_missing, is_ddl
from backend.utils.logger import get_logger

logger = get_logger(__name__)


async def run_query(args: dict) -> dict:
    """
    Execute a validated SELECT query against the user's database.
    Enforces LIMIT and blocks DDL as a final safety check.
    """
    sql = args.get("sql", "").strip()
    if not sql:
        raise ValueError("No SQL provided")

    # Final safety check — never trust that validate_query ran
    ddl_found, reason = is_ddl(sql)
    if ddl_found:
        raise ValueError(f"Blocked: {reason}")

    # Ensure LIMIT exists
    sql = add_limit_if_missing(sql, limit=100)

    settings = get_settings()

    try:
        conn = await asyncpg.connect(dsn=settings.user_db_url)
    except Exception as e:
        raise RuntimeError(f"Cannot connect to database: {e}")

    try:
        start = time.monotonic()
        rows = await conn.fetch(sql)
        execution_time_ms = int((time.monotonic() - start) * 1000)
    except asyncpg.PostgresError as e:
        # Re-raise with the raw PG error — agent uses this for fix_query
        raise RuntimeError(str(e))
    finally:
        await conn.close()

    # Convert asyncpg Record objects to plain dicts
    from decimal import Decimal
    from datetime import date, datetime

    def _serialize(val):
        if isinstance(val, Decimal):
            return float(val)
        if isinstance(val, (datetime, date)):
            return val.isoformat()
        return val

    row_dicts = [{k: _serialize(v) for k, v in dict(r).items()} for r in rows]

    logger.info(
        "query_executed",
        row_count=len(row_dicts),
        execution_time_ms=execution_time_ms,
        sql=sql[:100],
    )

    return {
        "rows": row_dicts,
        "row_count": len(row_dicts),
        "execution_time_ms": execution_time_ms,
    }
