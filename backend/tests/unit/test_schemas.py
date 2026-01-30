"""
Unit tests for Pydantic schemas.

Focus: Test business constraints that could be accidentally removed
and would cause subtle data integrity issues.
"""

import pytest
from pydantic import ValidationError

from mimir.schemas.tenant import TenantCreate


class TestTenantShortname:
    """Test TenantCreate shortname validation.
    
    Shortname constraints exist to ensure database-safe identifiers
    and URL-safe values. These tests document the rules and catch
    accidental removal of the regex pattern.
    """

    def test_rejects_uppercase(self):
        """Shortname must be lowercase - prevents case-sensitivity bugs."""
        with pytest.raises(ValidationError):
            TenantCreate(shortname="TestTenant", name="Test")

    def test_rejects_starting_with_number(self):
        """Shortname must start with letter - SQL identifier safety."""
        with pytest.raises(ValidationError):
            TenantCreate(shortname="123tenant", name="Test")

    def test_rejects_empty(self):
        """Shortname cannot be empty."""
        with pytest.raises(ValidationError):
            TenantCreate(shortname="", name="Test")

    def test_accepts_valid_patterns(self):
        """Document valid shortname patterns."""
        valid = ["a", "test", "my-tenant", "tenant_1", "test-tenant-name"]
        for shortname in valid:
            t = TenantCreate(shortname=shortname, name="Test")
            assert t.shortname == shortname