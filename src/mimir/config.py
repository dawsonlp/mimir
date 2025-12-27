"""Configuration management for Mímir.

Uses pydantic-settings for environment variable loading with validation.
All secrets are validated at startup to fail fast on misconfiguration.
"""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All secrets are validated at startup. The application will fail to start
    if required secrets are missing or invalid.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database configuration
    database_url: str = Field(
        ...,
        description="PostgreSQL connection URL (postgresql+psycopg://...)",
    )
    postgres_password: SecretStr = Field(
        ...,
        description="PostgreSQL password (min 16 characters)",
    )

    # Application settings
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    environment: str = Field(
        default="development",
        description="Environment name (development, staging, production)",
    )

    # API settings
    api_title: str = Field(
        default="Mímir API",
        description="API title for OpenAPI documentation",
    )
    api_version: str = Field(
        default="0.1.0",
        description="API version",
    )

    @field_validator("postgres_password")
    @classmethod
    def validate_password_strength(cls, v: SecretStr) -> SecretStr:
        """Validate password meets security requirements.

        Requirements:
        - Minimum 16 characters
        - Not the example placeholder value
        - Not empty
        """
        password = v.get_secret_value()

        if not password:
            raise ValueError("POSTGRES_PASSWORD is required")

        if len(password) < 16:
            raise ValueError("POSTGRES_PASSWORD must be at least 16 characters")

        # Reject common placeholder values
        placeholder_values = {
            "your-secure-password-here",
            "changeme",
            "password",
            "postgres",
        }
        if password.lower() in placeholder_values:
            raise ValueError("POSTGRES_PASSWORD cannot be a placeholder value")

        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is a valid Python logging level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of: {', '.join(valid_levels)}")
        return v.upper()


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings.

    Settings are loaded once and cached for performance.
    The application will fail to start if validation fails.
    """
    return Settings()
