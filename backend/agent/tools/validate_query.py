import sqlglot
from backend.utils.sql_safety import is_ddl, is_unsafe_dml, add_limit_if_missing
from backend.utils.logger import get_logger

logger = get_logger(__name__)


async def validate_query(args: dict) -> dict:
    """
    Parse SQL with sqlglot and check for safety violations.
    Returns validation result with issues list and safe SQL.
    """
    sql = args.get("sql", "").strip()

    if not sql:
        return {
            "valid": False,
            "is_safe": False,
            "issues": ["Empty query"],
            "sql_with_limit": "",
        }

    issues = []

    # Step 1: try parsing (catches syntax errors)
    try:
        statements = sqlglot.parse(sql, dialect="postgres")
        if not statements or all(s is None for s in statements):
            return {
                "valid": False,
                "is_safe": False,
                "issues": ["Could not parse SQL"],
                "sql_with_limit": "",
            }
    except Exception as e:
        return {
            "valid": False,
            "is_safe": False,
            "issues": [f"Parse error: {e}"],
            "sql_with_limit": "",
        }

    # Step 2: check for DDL
    ddl_found, ddl_reason = is_ddl(sql)
    if ddl_found:
        issues.append(ddl_reason)

    # Step 3: check for unsafe DML
    dml_found, dml_reason = is_unsafe_dml(sql)
    if dml_found:
        issues.append(dml_reason)

    if issues:
        logger.warning("query_blocked", issues=issues, sql=sql[:100])
        return {
            "valid": False,
            "is_safe": False,
            "issues": issues,
            "sql_with_limit": "",
        }

    # Step 4: add LIMIT if missing
    sql_with_limit = add_limit_if_missing(sql)

    logger.info("query_validated", sql=sql_with_limit[:100])
    return {
        "valid": True,
        "is_safe": True,
        "issues": [],
        "sql_with_limit": sql_with_limit,
    }
