"""Identifier generation for Mimir."""

from uuid import UUID, uuid7


def new_uuid7() -> UUID:
    """Generate a UUIDv7 for server-created entity identifiers."""
    return uuid7()
