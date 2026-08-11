from functools import lru_cache
from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Browser Monitor"
    environment: str = "development"
    database_url: str = Field(
        default="mysql+aiomysql://monitor:monitor@mysql:3306/browser_monitor"
    )
    redis_url: str | None = "redis://redis:6379/0"
    jwt_secret: str = "change-me-in-production"
    public_base_url: AnyHttpUrl | str = "http://localhost:8000"
    session_cookie_name: str = "bm_admin"
    trusted_proxy_cidrs: str = ""
    ip_anonymization: bool = True
    max_payload_bytes: int = 16_384
    heartbeat_timeout_seconds: int = 45
    action_resend_grace_seconds: int = 10
    cors_dashboard_origins: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
