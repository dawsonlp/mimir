"""Configuration management for Mímir.

Uses pydantic-settings for environment variable loading with validation.
All secrets are validated at startup to fail fast on misconfiguration.
"""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
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

    # Embedding settings
    openai_api_key: SecretStr | None = Field(
        default=None,
        description="OpenAI API key for embeddings (required for OpenAI models)",
    )
    default_embedding_model: str = Field(
        default="openai-text-embedding-3-small",
        description="Default embedding model to use",
    )
    embedding_batch_size: int = Field(
        default=100,
        ge=1,
        le=2048,
        description="Maximum batch size for embedding generation",
    )
    embedding_max_tokens: int = Field(
        default=8191,
        ge=1,
        description="Maximum tokens per text for embedding (model-specific)",
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

    @field_validator("default_embedding_model")
    @classmethod
    def validate_embedding_model(cls, v: str) -> str:
        """Validate embedding model is supported."""
        valid_models = {
            "openai-text-embedding-3-small",
            "openai-text-embedding-3-large",
            "openai-text-embedding-ada-002",
            "sentence-transformers-all-mpnet",
            "sentence-transformers-all-minilm",
        }
        if v not in valid_models:
            raise ValueError(f"DEFAULT_EMBEDDING_MODEL must be one of: {', '.join(valid_models)}")
        return v

    @model_validator(mode="after")
    def validate_openai_key_if_needed(self) -> "Settings":
        """Validate OpenAI API key is present if using OpenAI models."""
        if self.default_embedding_model.startswith("openai-") and not self.openai_api_key:
            # Only warn, don't fail - allows app to start without embeddings
            import warnings

            warnings.warn(
                "OPENAI_API_KEY not set but default embedding model is OpenAI. "
                "Embedding generation will fail without a valid API key.",
                stacklevel=2,
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings.

    Settings are loaded once and cached for performance.
    The application will fail to start if validation fails.
    """
    return Settings()
