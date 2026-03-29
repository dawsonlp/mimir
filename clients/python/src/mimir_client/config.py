"""Configuration for MimirClient via environment variables."""

from pydantic_settings import BaseSettings


class MimirClientSettings(BaseSettings):
    """Settings loaded from environment variables or .env file."""

    api_url: str = "http://localhost:38000"
    tenant_id: int | None = None
    timeout: float = 30.0

    model_config = {"env_prefix": "MIMIR_", "env_file": ".env"}


def get_settings() -> MimirClientSettings:
    """Load settings from environment."""
    return MimirClientSettings()