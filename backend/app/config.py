from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEXT_TASK_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/next-task.sqlite3"
    frontend_dir: Path = Path("frontend/dist")
    session_cookie_name: str = "next_task_session"
    session_ttl_days: int = 30
    cookie_secure: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()

