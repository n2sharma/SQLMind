import sqlglot
import sqlglot.expressions as exp
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Statement types that are never allowed
DDL_TYPES = (
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.TruncateTable,
)

# DML types that require a WHERE clause
DML_REQUIRES_WHERE = (exp.Update, exp.Delete)


def is_ddl(sql: str) -> tuple[bool, str]:
    """Returns (is_ddl, reason). True means the query is dangerous."""
    try:
        statements = sqlglot.parse(sql, dialect="postgres")
        for stmt in statements:
            if stmt is None:
                continue
            if isinstance(stmt, DDL_TYPES):
                return True, f"DDL statement not allowed: {type(stmt).__name__}"
        return False, ""
    except Exception as e:
        return False, ""  # parse error handled separately


def is_unsafe_dml(sql: str) -> tuple[bool, str]:
    """Detect UPDATE/DELETE without WHERE clause."""
    try:
        statements = sqlglot.parse(sql, dialect="postgres")
        for stmt in statements:
            if stmt is None:
                continue
            if isinstance(stmt, DML_REQUIRES_WHERE):
                where = stmt.find(exp.Where)
                if where is None:
                    return (
                        True,
                        f"{type(stmt).__name__} without WHERE clause is not allowed",
                    )
        return False, ""
    except Exception:
        return False, ""


def add_limit_if_missing(sql: str, limit: int = 100) -> str:
    """Add LIMIT clause to SELECT if not already present."""
    try:
        statements = sqlglot.parse(sql, dialect="postgres")
        if not statements or statements[0] is None:
            return sql
        stmt = statements[0]
        # Only add LIMIT to SELECT statements
        if not isinstance(stmt, exp.Select):
            return sql
        # Already has a limit
        if stmt.find(exp.Limit):
            return sql
        # Add LIMIT
        limited = stmt.limit(limit)
        return limited.sql(dialect="postgres")
    except Exception:
        return sql  # if parsing fails, return original
