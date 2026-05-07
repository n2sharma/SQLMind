import json
import time
from enum import Enum
from typing import AsyncGenerator

from backend.config import get_settings
from backend.utils.logger import get_logger
from backend.agent.llm_client import get_llm_client
from backend.agent.tools.get_schema import get_schema
from backend.agent.tools.validate_query import validate_query
from backend.agent.tools.run_query import run_query
from backend.agent.tools.explain_result import explain_result
from backend.agent.tools import TOOL_DEFINITIONS_GEMINI, TOOL_DEFINITIONS_OPENAI
from backend.db.history import save_query

logger = get_logger(__name__)


class AgentState(Enum):
    IDLE = "idle"
    SCHEMA_FETCH = "schema_fetch"
    SQL_GENERATE = "sql_generate"
    VALIDATE = "validate"
    EXECUTE = "execute"
    RETRY = "retry"
    EXPLAIN = "explain"
    DONE = "done"
    ERROR = "error"


class SQLMindAgent:
    def __init__(self, question: str):
        self.question = question
        self.settings = get_settings()
        self.llm = get_llm_client()
        self.is_openai = self.settings.model_provider == "openai"

        self.state = AgentState.IDLE
        self.iteration = 0
        self.retry_count = 0

        self.schema: dict = {}
        self.schema_str: str = ""
        self.generated_sql: str = ""
        self.validated_sql: str = ""
        self.rows: list = []
        self.row_count: int = 0
        self.execution_time_ms: int = 0
        self.explanation: str = ""
        self.total_tokens: int = 0
        self.error_message: str = ""
        self.start_time: float = time.monotonic()

    def _check_limits(self):
        if self.iteration >= self.settings.agent_max_iterations:
            raise RuntimeError(
                f"Agent exceeded max iterations ({self.settings.agent_max_iterations})."
            )
        elapsed = time.monotonic() - self.start_time
        if elapsed > self.settings.agent_timeout_seconds:
            raise RuntimeError(f"Agent timeout after {elapsed:.1f}s.")

    def _schema_to_string(self) -> str:
        lines = []
        for table in self.schema.get("tables", []):
            col_parts = []
            for col in table["columns"]:
                flags = []
                if col["is_pk"]:
                    flags.append("PK")
                if col["is_fk"] and col["references"]:
                    flags.append(
                        f"FK→{col['references']['ref_table']}.{col['references']['ref_column']}"
                    )
                flag_str = f" [{', '.join(flags)}]" if flags else ""
                nullable = "" if col["nullable"] else " NOT NULL"
                col_parts.append(f"  {col['name']} {col['type']}{nullable}{flag_str}")
            lines.append(f"TABLE {table['name']}:")
            lines.extend(col_parts)
        return "\n".join(lines)

    def _system_prompt(self) -> str:
        return f"""You are SQLMind, an expert PostgreSQL analyst.

You help users query their database using natural language.
You have access to tools to fetch schema, run queries, and explain results.

## Rules
1. ALWAYS call get_schema first to understand the database
2. Generate only SELECT queries — never INSERT, UPDATE, DELETE, DROP, or CREATE
3. Always call run_query with the SQL you want to execute
4. After getting results, always call explain_result to give the user a plain English answer
5. If run_query fails, analyze the error and try a corrected query (max {self.settings.agent_max_retries} retries)
6. Never output raw SQL as text — always use tool calls

## Database Schema
{self.schema_str if self.schema_str else "Call get_schema to fetch the schema first."}
"""

    def _init_messages(self) -> list:
        """
        Build initial message list.
        OpenAI: uses 'system' + 'user' roles
        Gemini: uses 'user' + 'model' roles
        This is the key format difference between providers.
        """
        if self.is_openai:
            return [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": self.question},
            ]
        else:
            return [
                {"role": "user", "parts": [{"text": self._system_prompt()}]},
                {
                    "role": "model",
                    "parts": [{"text": "Understood. I will help query the database."}],
                },
                {"role": "user", "parts": [{"text": self.question}]},
            ]

    def _append_tool_call(
        self, messages: list, tool_name: str, tool_args: dict, tool_call_id: str = None
    ):
        """Add assistant tool call + tool result to message history."""
        if self.is_openai:
            messages.append(
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": tool_call_id or f"call_{tool_name}_{self.iteration}",
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(tool_args),
                            },
                        }
                    ],
                }
            )
        else:
            messages.append(
                {
                    "role": "model",
                    "parts": [
                        {"function_call": {"name": tool_name, "args": tool_args}}
                    ],
                }
            )

    def _append_tool_result(
        self, messages: list, tool_name: str, result: str, tool_call_id: str = None
    ):
        if self.is_openai:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id
                    or f"call_{tool_name}_{self.iteration}",
                    "content": result,
                }
            )
        else:
            messages.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "function_response": {
                                "name": tool_name,
                                "response": {"result": result},
                            }
                        }
                    ],
                }
            )

    def _update_system_prompt(self, messages: list):
        """Refresh system prompt in messages after schema is fetched."""
        if self.is_openai:
            messages[0]["content"] = self._system_prompt()
        else:
            messages[0]["parts"][0]["text"] = self._system_prompt()

    async def _dispatch_tool(self, tool_name: str, tool_args: dict) -> str:
        self.iteration += 1
        self._check_limits()
        logger.info("tool_dispatched", tool=tool_name, iteration=self.iteration)

        if tool_name == "get_schema":
            self.state = AgentState.SCHEMA_FETCH
            result = await get_schema(tool_args)
            self.schema = result
            self.schema_str = self._schema_to_string()
            return json.dumps(result)

        elif tool_name == "run_query":
            sql = tool_args.get("sql", "")
            self.generated_sql = sql
            self.state = AgentState.VALIDATE

            validation = await validate_query({"sql": sql})
            if not validation["valid"]:
                issues = "; ".join(validation["issues"])
                raise ValueError(f"Query blocked by safety check: {issues}")

            safe_sql = validation["sql_with_limit"]
            self.validated_sql = safe_sql
            self.state = AgentState.EXECUTE

            try:
                exec_result = await run_query({"sql": safe_sql})
                self.rows = exec_result["rows"]
                self.row_count = exec_result["row_count"]
                self.execution_time_ms = exec_result["execution_time_ms"]
                return json.dumps(
                    {
                        "rows": self.rows[:5],
                        "row_count": self.row_count,
                        "execution_time_ms": self.execution_time_ms,
                    }
                )
            except RuntimeError as e:
                self.retry_count += 1
                if self.retry_count > self.settings.agent_max_retries:
                    raise RuntimeError(f"Max retries exceeded. Last error: {e}")
                self.state = AgentState.RETRY
                logger.warning(
                    "query_failed_will_retry",
                    attempt=self.retry_count,
                    error=str(e)[:100],
                )
                return json.dumps({"error": str(e), "retry_attempt": self.retry_count})

        elif tool_name == "explain_result":
            self.state = AgentState.EXPLAIN
            tool_args["rows"] = self.rows
            tool_args["row_count"] = self.row_count
            result = await explain_result(tool_args, self.llm)
            self.explanation = result["explanation"]
            self.state = AgentState.DONE
            return json.dumps(result)

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    async def run(self) -> dict:
        self.state = AgentState.SQL_GENERATE
        messages = self._init_messages()
        tools = TOOL_DEFINITIONS_OPENAI if self.is_openai else TOOL_DEFINITIONS_GEMINI

        while self.iteration < self.settings.agent_max_iterations:
            # Refresh system prompt (schema gets added after get_schema call)
            self._update_system_prompt(messages)

            response = await self.llm.generate_with_tools(messages, tools)
            self.total_tokens += response.get("tokens", 0)

            if response["type"] == "text":
                if not self.explanation:
                    self.explanation = response["text"]
                self.state = AgentState.DONE
                break

            if response["type"] == "tool_call":
                tool_name = response["tool_name"]
                tool_args = response["tool_args"]
                tool_call_id = response.get("tool_call_id")

                try:
                    tool_result = await self._dispatch_tool(tool_name, tool_args)
                except ValueError as e:
                    self.error_message = str(e)
                    self.state = AgentState.ERROR
                    break
                except RuntimeError as e:
                    self.error_message = str(e)
                    self.state = AgentState.ERROR
                    break

                self._append_tool_call(messages, tool_name, tool_args, tool_call_id)
                self._append_tool_result(messages, tool_name, tool_result, tool_call_id)

                if self.state == AgentState.DONE:
                    break

        elapsed_ms = int((time.monotonic() - self.start_time) * 1000)
        status = "success" if self.state == AgentState.DONE else "error"
        if self.retry_count > 0 and self.state == AgentState.DONE:
            status = "retry_success"

        await save_query(
            question=self.question,
            generated_sql=self.validated_sql or self.generated_sql,
            rows_returned=self.row_count,
            execution_time_ms=elapsed_ms,
            tokens_used=self.total_tokens,
            status=status,
            error_message=self.error_message or None,
            retry_count=self.retry_count,
        )

        if self.state == AgentState.ERROR:
            raise RuntimeError(self.error_message)

        return {
            "sql": self.validated_sql or self.generated_sql,
            "rows": self.rows,
            "row_count": self.row_count,
            "explanation": self.explanation,
            "tokens_used": self.total_tokens,
            "execution_time_ms": elapsed_ms,
            "retry_count": self.retry_count,
        }

    async def run_streaming(self) -> AsyncGenerator[dict, None]:
        self.state = AgentState.SQL_GENERATE
        messages = self._init_messages()
        tools = TOOL_DEFINITIONS_OPENAI if self.is_openai else TOOL_DEFINITIONS_GEMINI

        while self.iteration < self.settings.agent_max_iterations:
            self._update_system_prompt(messages)

            response = await self.llm.generate_with_tools(messages, tools)
            self.total_tokens += response.get("tokens", 0)

            if response["type"] == "text":
                if not self.explanation:
                    self.explanation = response["text"]
                self.state = AgentState.DONE
                break

            if response["type"] == "tool_call":
                tool_name = response["tool_name"]
                tool_args = response["tool_args"]
                tool_call_id = response.get("tool_call_id")

                if tool_name == "get_schema":
                    yield {"type": "status", "message": "Fetching database schema..."}
                elif tool_name == "run_query":
                    yield {"type": "sql_generated", "sql": tool_args.get("sql", "")}
                    yield {
                        "type": "status",
                        "message": "Validating and executing query...",
                    }
                elif tool_name == "explain_result":
                    yield {"type": "status", "message": "Generating explanation..."}

                try:
                    tool_result = await self._dispatch_tool(tool_name, tool_args)
                except ValueError as e:
                    yield {"type": "error", "message": str(e)}
                    self.state = AgentState.ERROR
                    return
                except RuntimeError as e:
                    yield {"type": "error", "message": str(e)}
                    self.state = AgentState.ERROR
                    return

                if tool_name == "get_schema":
                    yield {
                        "type": "schema_fetched",
                        "table_count": len(self.schema.get("tables", [])),
                    }
                elif tool_name == "run_query" and self.state == AgentState.RETRY:
                    yield {"type": "retry", "attempt": self.retry_count}
                elif tool_name == "run_query" and self.state == AgentState.EXECUTE:
                    yield {"type": "executing", "row_count": self.row_count}

                self._append_tool_call(messages, tool_name, tool_args, tool_call_id)
                self._append_tool_result(messages, tool_name, tool_result, tool_call_id)

                if self.state == AgentState.DONE:
                    break

        elapsed_ms = int((time.monotonic() - self.start_time) * 1000)
        status = "success" if self.state == AgentState.DONE else "error"
        if self.retry_count > 0 and self.state == AgentState.DONE:
            status = "retry_success"

        await save_query(
            question=self.question,
            generated_sql=self.validated_sql or self.generated_sql,
            rows_returned=self.row_count,
            execution_time_ms=elapsed_ms,
            tokens_used=self.total_tokens,
            status=status,
            error_message=self.error_message or None,
            retry_count=self.retry_count,
        )

        if self.state == AgentState.DONE:
            yield {
                "type": "complete",
                "sql": self.validated_sql or self.generated_sql,
                "rows": self.rows,
                "row_count": self.row_count,
                "explanation": self.explanation,
                "tokens_used": self.total_tokens,
                "execution_time_ms": elapsed_ms,
                "retry_count": self.retry_count,
            }
        else:
            yield {"type": "error", "message": self.error_message or "Agent failed"}
