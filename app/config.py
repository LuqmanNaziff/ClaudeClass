from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# All application settings in one place. Values are read from environment
# variables (or the .env file) and validated by Pydantic at startup, so a
# bad or missing setting fails early instead of in the middle of a request.
class Settings(BaseSettings):
    # Required (no default): the app will not start without APP_NAME.
    app_name: str = Field(..., env="APP_NAME")

    # Optional here so the app can start without them; ClaudeService checks
    # that they are set before it calls the API. SecretStr hides the key
    # in logs and reprs.
    anthropic_api_key: SecretStr | None = None
    claude_model: str | None = None

    # How long to wait for Claude (seconds). Must be > 0 and at most 120.
    claude_timeout_seconds: float = Field(
        default=30.0,
        gt= 0.0,
        le=120,
    )
    # How many times the SDK retries a failed request (0-5). More retries
    # mean better resilience but also more latency and possible cost.
    claude_max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
    )

    # Where to load settings from: a .env file in the working directory.
    # extra="ignore" skips unknown variables instead of raising an error.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # MongoDB connection string. SecretStr hides it in logs and reprs;
    # database.py reveals it only when opening the connection.
    mongodb_uri: SecretStr

    # Name of the database inside the MongoDB server.
    mongodb_database: str = "supportops"

# lru_cache makes this build Settings only once; every later call returns
# the same object, so .env is read a single time.
@lru_cache
def get_settings() -> Settings:
    return Settings()