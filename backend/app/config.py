from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEXT_TASK_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/next-task.sqlite3"
    frontend_dir: Path = Path("frontend/dist")
    session_cookie_name: str = "next_task_session"
    session_ttl_days: int = 30
    cookie_secure: bool = False
    credential_secret: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.8-flash"
    mcp_public_url: str = "http://localhost:8001"
    mcp_access_token_minutes: int = 60
    mcp_refresh_token_days: int = 90


@lru_cache
def get_settings() -> Settings:
    return Settings()
