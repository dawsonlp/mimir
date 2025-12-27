"""Unit tests for configuration module."""

import os
from unittest.mock import patch

import pytest
from pydantic import SecretStr, ValidationError


class TestPasswordValidation:
    """Test password strength validation."""

    def test_password_too_short_raises_error(self):
        """Password under 16 characters should fail."""
        with patch.dict(
            os.environ,
            {
                "POSTGRES_PASSWORD": "short",
                "DATABASE_URL": "postgresql+psycopg://x:y@localhost/db",
            },
            clear=False,
        ):
            # Clear the cached settings
            from mimir.config import Settings, get_settings

            get_settings.cache_clear()

            with pytest.raises(ValidationError) as exc_info:
                Settings()

            assert "at least 16 characters" in str(exc_info.value)

    def test_placeholder_password_raises_error(self):
        """Placeholder passwords should fail."""
        with patch.dict(
            os.environ,
            {
                "POSTGRES_PASSWORD": "your-secure-password-here",
                "DATABASE_URL": "postgresql+psycopg://x:y@localhost/db",
            },
            clear=False,
        ):
            from mimir.config import Settings, get_settings

            get_settings.cache_clear()

            with pytest.raises(ValidationError) as exc_info:
                Settings()

            assert "placeholder" in str(exc_info.value).lower()

    def test_valid_password_accepted(self):
        """Valid password should be accepted."""
        with patch.dict(
            os.environ,
            {
                "POSTGRES_PASSWORD": "this_is_a_secure_password_123!",
                "DATABASE_URL": "postgresql+psycopg://x:y@localhost/db",
            },
            clear=False,
        ):
            from mimir.config import Settings, get_settings

            get_settings.cache_clear()

            settings = Settings()
            assert isinstance(settings.postgres_password, SecretStr)
            assert len(settings.postgres_password.get_secret_value()) >= 16


class TestLogLevelValidation:
    """Test log level validation."""

    def test_invalid_log_level_raises_error(self):
        """Invalid log level should fail."""
        with patch.dict(
            os.environ,
            {
                "POSTGRES_PASSWORD": "this_is_a_secure_password_123!",
                "DATABASE_URL": "postgresql+psycopg://x:y@localhost/db",
                "LOG_LEVEL": "INVALID",
            },
            clear=False,
        ):
            from mimir.config import Settings, get_settings

            get_settings.cache_clear()

            with pytest.raises(ValidationError) as exc_info:
                Settings()

            assert "LOG_LEVEL" in str(exc_info.value)

    def test_valid_log_levels_accepted(self):
        """Valid log levels should be accepted."""
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            with patch.dict(
                os.environ,
                {
                    "POSTGRES_PASSWORD": "this_is_a_secure_password_123!",
                    "DATABASE_URL": "postgresql+psycopg://x:y@localhost/db",
                    "LOG_LEVEL": level,
                },
                clear=False,
            ):
                from mimir.config import Settings, get_settings

                get_settings.cache_clear()

                settings = Settings()
                assert settings.log_level == level
