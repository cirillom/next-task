from functools import lru_cache
from pathlib import Path
from typing import Literal

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
    public_app_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_security: Literal["starttls", "ssl"] = "starttls"
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from_email: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
