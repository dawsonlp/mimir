"""Shared pytest fixtures for Mímir tests.

This module provides common fixtures for both unit and integration tests.
"""

import os

import pytest


@pytest.fixture(scope="session")
def anyio_backend():
    """Use asyncio as the async backend for pytest-asyncio."""
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
def set_test_environment():
    """Set environment variables for testing."""
    # Set a test password that meets requirements
    os.environ.setdefault("POSTGRES_PASSWORD", "test_password_minimum_16_chars")
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+psycopg://mimir:test_password_minimum_16_chars@localhost:35432/mimir",
    )
    os.environ.setdefault("ENVIRONMENT", "testing")
    os.environ.setdefault("LOG_LEVEL", "DEBUG")
