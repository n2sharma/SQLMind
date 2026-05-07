from backend.config import get_settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class GeminiClient:
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.total_tokens = 0

    async def generate_text(self, prompt: str) -> str:
        """Simple text generation — used by explain_result and fix_query."""
        import asyncio

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            ),
        )
        # Track tokens if available
        if hasattr(response, "usage_metadata"):
            self.total_tokens += (
                response.usage_metadata.prompt_token_count
                + response.usage_metadata.candidates_token_count
            )
        return response.text

    async def generate_with_tools(self, messages: list, tools: list) -> dict:
        """
        Tool-calling generation — used by the agent loop.
        Returns: { "type": "tool_call"|"text", "tool_name": str, "tool_args": dict, "text": str, "tokens": int }
        """
        import asyncio
        from google.genai import types

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.models.generate_content(
                model=self.model,
                contents=messages,
                config=types.GenerateContentConfig(tools=tools),
            ),
        )

        tokens = 0
        if hasattr(response, "usage_metadata"):
            tokens = (
                response.usage_metadata.prompt_token_count
                + response.usage_metadata.candidates_token_count
            )
            self.total_tokens += tokens

        # Check if the model wants to call a tool
        part = response.candidates[0].content.parts[0]
        if hasattr(part, "function_call") and part.function_call:
            fc = part.function_call
            return {
                "type": "tool_call",
                "tool_name": fc.name,
                "tool_args": dict(fc.args),
                "text": "",
                "tokens": tokens,
            }
        else:
            return {
                "type": "text",
                "tool_name": "",
                "tool_args": {},
                "text": response.text,
                "tokens": tokens,
            }


class OpenAIClient:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.total_tokens = 0

    async def generate_text(self, prompt: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )
        self.total_tokens += response.usage.total_tokens
        return response.choices[0].message.content

    async def generate_with_tools(self, messages: list, tools: list) -> dict:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        self.total_tokens += response.usage.total_tokens
        choice = response.choices[0]

        if choice.message.tool_calls:
            tc = choice.message.tool_calls[0]
            import json

            return {
                "type": "tool_call",
                "tool_name": tc.function.name,
                "tool_args": json.loads(tc.function.arguments),
                "tool_call_id": tc.id,
                "text": "",
                "tokens": response.usage.total_tokens,
            }
        else:
            return {
                "type": "text",
                "tool_name": "",
                "tool_args": {},
                "text": choice.message.content,
                "tokens": response.usage.total_tokens,
            }


_client = None


def get_llm_client():
    global _client
    if _client is not None:
        return _client

    settings = get_settings()

    if settings.model_provider == "openai":
        logger.info(
            "llm_client_initialized", provider="openai", model=settings.openai_model
        )
        _client = OpenAIClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )
    else:
        logger.info(
            "llm_client_initialized", provider="gemini", model="gemini-2.0-flash"
        )
        _client = GeminiClient(api_key=settings.gemini_api_key)

    return _client
