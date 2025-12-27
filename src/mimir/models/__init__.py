"""SQLAlchemy Core table definitions for Mímir.

IMPORTANT: SQLAlchemy is used for schema definitions ONLY (for Alembic autogenerate).
All data access uses raw SQL via psycopg v3. NO ORM.

Table definitions are added here to export metadata for Alembic migrations.
"""

from sqlalchemy import MetaData

# Naming convention for constraints (recommended for Alembic)
# This ensures consistent naming across all auto-generated constraints
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Central metadata object - import this in all model modules
metadata = MetaData(naming_convention=convention)

# Table definitions will be imported here as they are created in Phase 2+
# Example (after Phase 2):
# from mimir.models.artifacts import artifacts_table, artifact_versions_table
# from mimir.models.intents import intents_table, intent_groups_table
# etc.

# All tables are registered with the metadata object above,
# which Alembic uses for autogenerate migrations.
