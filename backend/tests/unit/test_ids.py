"""Tests for Mimir identifier generation."""

from mimir.ids import new_uuid7


def test_new_uuid7_generates_uuid_version_7():
    """Server-generated identifiers should be UUIDv7."""
    generated = new_uuid7()

    assert generated.version == 7
