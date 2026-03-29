"""Configuration for MimirClient via environment variables."""

from __future__ import annotations

import warnings
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings


class MimirClientSettings(BaseSettings):
    """Settings loaded from environment variables or .env file.

    Supports both the new ``MIMIR_TENANT`` (shortname string) and the
    deprecated ``MIMIR_TENANT_ID`` (integer). Setting both raises
    ``ValueError``.
    """

    api_url: str = "http://localhost:38000"
    tenant: str | None = None
    tenant_id: int | None = None
    timeout: float = 30.0

    model_config = {"env_prefix": "MIMIR_", "env_file": ".env"}

    @model_validator(mode="after")
    def _check_tenant_mutual_exclusion(self) -> Self:
        if self.tenant is not None and self.tenant_id is not None:
            raise ValueError(
                "Cannot set both MIMIR_TENANT and MIMIR_TENANT_ID. "
                "Use MIMIR_TENANT (shortname string). "
                "MIMIR_TENANT_ID is deprecated."
            )
        if self.tenant_id is not None:
            warnings.warn(
                "MIMIR_TENANT_ID is deprecated and will be removed in v6.0.0. "
                "Use MIMIR_TENANT (shortname string) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        return self


def get_settings() -> MimirClientSettings:
    """Load settings from environment."""
    return MimirClientSettings()
