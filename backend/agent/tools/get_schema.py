import asyncpg
from backend.config import get_settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)


async def get_schema(args: dict) -> dict:
    """
    Fetch schema from the user's database via information_schema.
    Returns tables with columns, types, PKs, and FKs.
    """
    settings = get_settings()
    filter_tables = args.get("tables", [])

    try:
        conn = await asyncpg.connect(dsn=settings.user_db_url)
    except Exception as e:
        raise RuntimeError(f"Cannot connect to database: {e}")

    try:
        # Get all columns with type info
        column_query = """
            SELECT
                c.table_name,
                c.column_name,
                c.data_type,
                c.is_nullable,
                c.column_default
            FROM information_schema.columns c
            WHERE c.table_schema = 'public'
            ORDER BY c.table_name, c.ordinal_position
        """
        columns = await conn.fetch(column_query)

        # Get primary key columns
        pk_query = """
            SELECT
                kcu.table_name,
                kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = 'public'
        """
        pks = await conn.fetch(pk_query)
        pk_set = {(r["table_name"], r["column_name"]) for r in pks}

        # Get foreign key columns
        fk_query = """
            SELECT
                kcu.table_name,
                kcu.column_name,
                ccu.table_name  AS ref_table,
                ccu.column_name AS ref_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
                ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
        """
        fks = await conn.fetch(fk_query)
        fk_map = {
            (r["table_name"], r["column_name"]): {
                "ref_table": r["ref_table"],
                "ref_column": r["ref_column"],
            }
            for r in fks
        }

    finally:
        await conn.close()

    # Build structured schema
    tables: dict[str, dict] = {}
    for row in columns:
        tname = row["table_name"]
        if filter_tables and tname not in filter_tables:
            continue
        if tname not in tables:
            tables[tname] = {"name": tname, "columns": []}

        col = {
            "name": row["column_name"],
            "type": row["data_type"],
            "nullable": row["is_nullable"] == "YES",
            "is_pk": (tname, row["column_name"]) in pk_set,
            "is_fk": (tname, row["column_name"]) in fk_map,
            "references": fk_map.get((tname, row["column_name"])),
        }
        tables[tname]["columns"].append(col)

    result = {"tables": list(tables.values())}
    logger.info("schema_fetched", table_count=len(tables))
    return result
