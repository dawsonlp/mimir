"""Unit tests for MimirClientSettings (config.py).

Tests mutual exclusion, deprecation warnings, and field mapping.
"""

import pytest

from mimir_client import MimirClientSettings


class TestMimirClientSettings:
    def test_tenant_only(self):
        settings = MimirClientSettings(tenant="rademo1")
        assert settings.tenant == "rademo1"
        assert settings.tenant_id is None

    def test_tenant_id_only_emits_deprecation(self):
        with pytest.warns(DeprecationWarning, match="MIMIR_TENANT_ID is deprecated"):
            settings = MimirClientSettings(tenant_id=5)
        assert settings.tenant is None
        assert settings.tenant_id == 5

    def test_both_raises_value_error(self):
        with pytest.raises(ValueError, match="Cannot set both"):
            MimirClientSettings(tenant="dev", tenant_id=1)

    def test_neither_is_valid(self):
        settings = MimirClientSettings()
        assert settings.tenant is None
        assert settings.tenant_id is None

    def test_defaults(self):
        settings = MimirClientSettings()
        assert settings.api_url == "http://localhost:38000"
        assert settings.timeout == 30.0
