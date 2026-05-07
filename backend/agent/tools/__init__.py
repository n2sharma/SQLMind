TOOL_DEFINITIONS_GEMINI = [
    {
        "function_declarations": [
            {
                "name": "get_schema",
                "description": "Fetch the database schema including all tables, columns, data types, primary keys, and foreign keys",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tables": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of specific table names. If omitted, fetches all tables.",
                        }
                    },
                },
            },
            {
                "name": "run_query",
                "description": "Execute a SELECT SQL query against the PostgreSQL database and return the results",
                "parameters": {
                    "type": "object",
                    "required": ["sql"],
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "The SQL SELECT query to execute",
                        }
                    },
                },
            },
            {
                "name": "explain_result",
                "description": "Convert SQL query results into a clear plain English answer for the user",
                "parameters": {
                    "type": "object",
                    "required": ["question", "sql", "rows", "row_count"],
                    "properties": {
                        "question": {"type": "string"},
                        "sql": {"type": "string"},
                        "rows": {"type": "array"},
                        "row_count": {"type": "integer"},
                    },
                },
            },
        ]
    }
]
