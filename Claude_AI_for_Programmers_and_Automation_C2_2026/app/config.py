from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = Field(..., env="APP_NAME")
    
    anthropic_api_key: SecretStr | None = None
    claude_model: str | None = None

    claude_timeout_seconds: float = Field(
        default=30.0,
        gt= 0.0,
        le=120,
    )
    claude_max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()