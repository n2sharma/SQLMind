from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # LLM
    model_provider: str = "gemini"
    gemini_api_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Database
    database_url: str
    user_db_url: str

    # Server
    port: int = 8000
    log_level: str = "debug"

    # Agent limits
    agent_max_iterations: int = 8
    agent_max_retries: int = 2
    agent_timeout_seconds: int = 30

    class Config:
        env_file = ".env"  # .env is one level up (in SQLMind/ root)
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
