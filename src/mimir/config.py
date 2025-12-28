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
    voyageai_mimir_embeddings: SecretStr | None = Field(
        default=None,
        description="Voyage AI API key for embeddings (Anthropic recommended)",
    )

    @property
    def voyage_api_key(self) -> SecretStr | None:
        """Alias for voyageai_mimir_embeddings for compatibility."""
        return self.voyageai_mimir_embeddings
    openai_api_key: SecretStr | None = Field(
        default=None,
        description="OpenAI API key for embeddings (optional, for OpenAI models)",
    )
    default_embedding_model: str | None = Field(
        default=None,
        description="Default embedding model to use (auto-detected from configured providers if not set)",
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

    # Ollama settings (local embeddings)
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama server URL for local embeddings",
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

    @model_validator(mode="after")
    def validate_embedding_configuration(self) -> "Settings":
        """Validate embedding configuration.

        At least one embedding provider should be configured for embeddings to work.
        If default_embedding_model is set, verify the corresponding provider is configured.
        """
        import warnings

        # Check if any embedding provider is configured
        has_voyage = self.voyage_api_key is not None
        has_openai = self.openai_api_key is not None

        if not has_voyage and not has_openai:
            warnings.warn(
                "No embedding API keys configured. Set VOYAGE_API_KEY or OPENAI_API_KEY "
                "for embedding functionality.",
                stacklevel=2,
            )

        # Validate default model if explicitly set
        if self.default_embedding_model:
            # Voyage models
            voyage_models = {
                "voyage-3-large", "voyage-3", "voyage-3-lite",
                "voyage-code-3", "voyage-finance-2", "voyage-law-2",
                "voyage-multilingual-2",
            }
            # OpenAI models
            openai_models = {
                "text-embedding-3-small", "text-embedding-3-large",
                "text-embedding-ada-002",
            }

            if self.default_embedding_model in voyage_models and not has_voyage:
                warnings.warn(
                    f"DEFAULT_EMBEDDING_MODEL is {self.default_embedding_model} but "
                    "VOYAGE_API_KEY is not set. Embedding generation will fail.",
                    stacklevel=2,
                )
            elif self.default_embedding_model in openai_models and not has_openai:
                warnings.warn(
                    f"DEFAULT_EMBEDDING_MODEL is {self.default_embedding_model} but "
                    "OPENAI_API_KEY is not set. Embedding generation will fail.",
                    stacklevel=2,
                )
            elif self.default_embedding_model not in voyage_models | openai_models:
                warnings.warn(
                    f"DEFAULT_EMBEDDING_MODEL '{self.default_embedding_model}' is not a "
                    "recognized model. Available: Voyage AI models or OpenAI models.",
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
