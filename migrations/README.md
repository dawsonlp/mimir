# SQL Migrations

Plain SQL migration system for Mímir. No ORM abstraction layer.

## Structure

```
migrations/
├── versions/
│   ├── 001_create_schema_migrations.up.sql
│   ├── 001_create_schema_migrations.down.sql
│   ├── 002_create_tenants.up.sql
│   ├── 002_create_tenants.down.sql
│   └── ...
├── migrate.py          # Migration runner
└── README.md
```

## Naming Convention

- `{version}_{description}.up.sql` - Apply migration
- `{version}_{description}.down.sql` - Rollback migration

Version is a 3-digit number (001, 002, etc.).

## Commands

```bash
# Apply all pending migrations
poetry run python -m migrations.migrate up

# Rollback last migration
poetry run python -m migrations.migrate down

# Show current status
poetry run python -m migrations.migrate status
```

## Tracking

Migrations are tracked in `mimirdata.schema_migrations` table.
