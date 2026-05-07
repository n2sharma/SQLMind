from backend.utils.logger import get_logger

logger = get_logger(__name__)


async def explain_result(args: dict, llm_client) -> dict:
    """
    Call the LLM to convert SQL rows into a plain English answer.
    Falls back to a simple row count message if LLM fails.
    """
    question = args.get("question", "")
    sql = args.get("sql", "")
    rows = args.get("rows", [])
    row_count = args.get("row_count", 0)

    # Truncate rows for the prompt — we don't need all 100 rows to explain
    sample_rows = rows[:10]

    prompt = f"""The user asked: "{question}"

You ran this SQL query:
{sql}

It returned {row_count} rows. Here are the first {len(sample_rows)}:
{sample_rows}

Write a clear, concise plain English answer to the user's question based on these results.
Be specific — mention actual numbers, names, or values from the data.
Keep it to 2-3 sentences maximum."""

    try:
        explanation = await llm_client.generate_text(prompt)
        logger.info("explanation_generated", question=question[:50])
        return {"explanation": explanation}
    except Exception as e:
        logger.warning("explanation_failed", error=str(e))
        return {"explanation": f"Query returned {row_count} rows."}
