from backend.utils.logger import get_logger

logger = get_logger(__name__)


async def fix_query(args: dict, llm_client) -> dict:
    """
    Given a failing SQL and its error, ask the LLM to generate a corrected version.
    """
    original_question = args.get("original_question", "")
    failed_sql = args.get("failed_sql", "")
    error_message = args.get("error_message", "")
    schema = args.get("schema", "")

    prompt = f"""You are a PostgreSQL expert. A SQL query failed and needs to be fixed.

Original question: "{original_question}"

Failed SQL:
{failed_sql}

Error message:
{error_message}

Database schema:
{schema}

Write a corrected SQL query that fixes the error and answers the original question.
Return ONLY the SQL query, nothing else. No explanation, no markdown, just the SQL."""

    try:
        fixed_sql = await llm_client.generate_text(prompt)
        # Clean up in case model adds markdown
        fixed_sql = fixed_sql.strip().strip("```sql").strip("```").strip()
        logger.info("query_fixed", original_error=error_message[:100])
        return {"fixed_sql": fixed_sql, "explanation": f"Fixed: {error_message[:100]}"}
    except Exception as e:
        logger.error("fix_query_failed", error=str(e))
        return {"fixed_sql": "", "explanation": "Could not fix query"}
