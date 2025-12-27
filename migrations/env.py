"""Alembic migration environment configuration.

This module configures how Alembic connects to the database and
discovers SQLAlchemy models for autogenerate support.

IMPORTANT: SQLAlchemy Core is used for table definitions ONLY.
All data access uses raw SQL via psycopg v3.
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# Add src directory to path for model imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Import SQLAlchemy metadata from models (for autogenerate)
# This will be populated as models are added in Phase 2+
from mimir.models import metadata

# Alembic Config object
config = context.config

# Configure logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# SQLAlchemy MetaData for autogenerate support
target_metadata = metadata


def get_database_url() -> str:
    """Get database URL from environment.

    Priority:
    1. DATABASE_URL environment variable
    2. Construct from individual components

    SECURITY: Never hardcode credentials. Always use environment variables.
    """
    # Try DATABASE_URL first
    url = os.environ.get("DATABASE_URL")
    if url:
        # Alembic needs synchronous driver, convert if needed
        return url.replace("postgresql+psycopg://", "postgresql+psycopg2://")

    # Construct from components (fallback for local dev)
    user = os.environ.get("POSTGRES_USER", "mimir")
    password = os.environ.get("POSTGRES_PASSWORD")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "35432")
    database = os.environ.get("POSTGRES_DB", "mimir")

    if not password:
        raise ValueError(
            "Database password not set. Set DATABASE_URL or POSTGRES_PASSWORD."
        )

    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates SQL script without connecting to database.
    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an actual database connection for migration execution.
    """
    connectable = create_engine(
        get_database_url(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
