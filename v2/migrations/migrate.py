"""
Plain SQL migration runner for Mímir V2.

Usage:
    python -m migrations.migrate up      # Apply all pending migrations
    python -m migrations.migrate down    # Rollback last migration
    python -m migrations.migrate status  # Show migration status
"""

import asyncio
import os
import re
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SCHEMA = "mimirdata"
MIGRATIONS_DIR = Path(__file__).parent / "versions"


def get_database_url() -> str:
    """Get database URL from environment."""
    url = os.getenv("DATABASE_URL")
    if not url:
        # Build from components
        password = os.getenv("POSTGRES_PASSWORD")
        if not password:
            raise ValueError("POSTGRES_PASSWORD environment variable required")
        url = f"postgresql://mimir:{password}@localhost:35432/mimir"
    # Ensure we use psycopg v3 URL format (postgresql://, not postgresql+psycopg://)
    return url.replace("postgresql+psycopg://", "postgresql://")


def get_migration_files() -> list[tuple[int, str, Path, Path]]:
    """Get all migration files sorted by version.

    Returns list of (version, name, up_file, down_file) tuples.
    """
    if not MIGRATIONS_DIR.exists():
        return []

    up_files = sorted(MIGRATIONS_DIR.glob("*.up.sql"))
    migrations = []

    for up_file in up_files:
        match = re.match(r"(\d+)_(.+)\.up\.sql", up_file.name)
        if match:
            version = int(match.group(1))
            name = match.group(2)
            down_file = up_file.with_suffix("").with_suffix(".down.sql")
            migrations.append((version, name, up_file, down_file))

    return migrations


async def ensure_migrations_table(conn: psycopg.AsyncConnection) -> None:
    """Create schema_migrations table if it doesn't exist."""
    await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.schema_migrations (
            version INT PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMPTZ DEFAULT now()
        )
    """)


async def get_applied_versions(conn: psycopg.AsyncConnection) -> set[int]:
    """Get set of applied migration versions."""
    result = await conn.execute(
        f"SELECT version FROM {SCHEMA}.schema_migrations ORDER BY version"
    )
    rows = await result.fetchall()
    return {row[0] for row in rows}


async def apply_migration(
    conn: psycopg.AsyncConnection, version: int, name: str, sql_file: Path
) -> None:
    """Apply a single migration."""
    sql = sql_file.read_text()
    print(f"  Applying {version:03d}_{name}...")
    await conn.execute(sql)
    await conn.execute(
        f"INSERT INTO {SCHEMA}.schema_migrations (version, name) VALUES (%s, %s)",
        (version, name),
    )
    print(f"  ✓ Applied {version:03d}_{name}")


async def rollback_migration(
    conn: psycopg.AsyncConnection, version: int, name: str, sql_file: Path
) -> None:
    """Rollback a single migration."""
    if not sql_file.exists():
        raise FileNotFoundError(f"Down migration not found: {sql_file}")

    sql = sql_file.read_text()
    print(f"  Rolling back {version:03d}_{name}...")
    await conn.execute(sql)
    await conn.execute(
        f"DELETE FROM {SCHEMA}.schema_migrations WHERE version = %s", (version,)
    )
    print(f"  ✓ Rolled back {version:03d}_{name}")


async def migrate_up() -> None:
    """Apply all pending migrations."""
    url = get_database_url()
    migrations = get_migration_files()

    if not migrations:
        print("No migration files found.")
        return

    async with await psycopg.AsyncConnection.connect(url) as conn:
        await ensure_migrations_table(conn)
        applied = await get_applied_versions(conn)

        pending = [(v, n, up, down) for v, n, up, down in migrations if v not in applied]

        if not pending:
            print("All migrations are up to date.")
            return

        print(f"Applying {len(pending)} migration(s)...")
        for version, name, up_file, _ in pending:
            await apply_migration(conn, version, name, up_file)
            await conn.commit()

        print(f"\n✓ Applied {len(pending)} migration(s)")


async def migrate_down() -> None:
    """Rollback the last applied migration."""
    url = get_database_url()
    migrations = get_migration_files()

    async with await psycopg.AsyncConnection.connect(url) as conn:
        await ensure_migrations_table(conn)
        applied = await get_applied_versions(conn)

        if not applied:
            print("No migrations to rollback.")
            return

        last_version = max(applied)
        migration = next(
            ((v, n, up, down) for v, n, up, down in migrations if v == last_version),
            None,
        )

        if not migration:
            raise ValueError(f"Migration {last_version} not found in files")

        _, name, _, down_file = migration
        await rollback_migration(conn, last_version, name, down_file)
        await conn.commit()

        print("\n✓ Rolled back 1 migration")


async def show_status() -> None:
    """Show current migration status."""
    url = get_database_url()
    migrations = get_migration_files()

    async with await psycopg.AsyncConnection.connect(url) as conn:
        await ensure_migrations_table(conn)
        applied = await get_applied_versions(conn)

        print("Migration Status:")
        print("-" * 50)

        if not migrations:
            print("No migration files found.")
            return

        for version, name, _, _ in migrations:
            status = "✓ applied" if version in applied else "  pending"
            print(f"  {version:03d}_{name}: {status}")

        pending_count = sum(1 for v, _, _, _ in migrations if v not in applied)
        print("-" * 50)
        print(f"Total: {len(migrations)} migrations, {pending_count} pending")


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "up":
        asyncio.run(migrate_up())
    elif command == "down":
        asyncio.run(migrate_down())
    elif command == "status":
        asyncio.run(show_status())
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
