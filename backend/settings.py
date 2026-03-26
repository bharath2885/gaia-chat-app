"""Configuration loaded from environment variables or .env file."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    gaia_base_url: str = Field(
        default="https://helios.cohesity.com/v2/mcm/gaia",
        validation_alias="GAIA_BASE_URL",
    )
    gaia_verify_ssl: bool = Field(default=True, validation_alias="GAIA_VERIFY_SSL")
    request_timeout_seconds: float = Field(
        default=60.0, validation_alias="REQUEST_TIMEOUT_SECONDS"
    )
    allow_cors_origin: str = Field(
        default="http://localhost:5173", validation_alias="ALLOW_CORS_ORIGIN"
    )
    session_ttl_minutes: int = Field(default=60, validation_alias="SESSION_TTL_MINUTES")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
