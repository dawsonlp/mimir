"""Configuration management for Mímir Semantic Layer.

Handles loading configuration from environment variables and .env files.
"""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment.
    
    Environment Variables
    ---------------------
    MIMIR_API_URL : str
        Base URL for Mímir Storage API (default: http://localhost:38000)
    MIMIR_DOCS_URL : str, optional
        Base URL for API documentation (default: {MIMIR_API_URL}/docs)
    MIMIR_TENANT_ID : int, optional
        Default tenant ID for operations
    
    Example
    -------
    >>> settings = Settings()
    >>> print(settings.api_url)
    http://localhost:38000
    
    >>> # Or load from specific .env file
    >>> settings = Settings(_env_file=".env.production")
    """
    
    api_url: str = "http://localhost:38000"
    docs_url: str | None = None
    tenant_id: int | None = None
    
    class Config:
        env_prefix = "MIMIR_"
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    @property
    def resolved_docs_url(self) -> str:
        """Get documentation URL, defaulting to {api_url}/docs."""
        if self.docs_url:
            return self.docs_url.rstrip("/")
        return f"{self.api_url.rstrip('/')}/docs"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.
    
    Returns
    -------
    Settings
        Cached settings loaded from environment
    
    Note
    ----
    Settings are cached for the lifetime of the process.
    Call get_settings.cache_clear() to reload.
    """
    return Settings()