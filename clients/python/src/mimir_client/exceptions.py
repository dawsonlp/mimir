"""Typed exceptions for Mímir API errors.

All exceptions inherit from MimirError for catch-all handling.

Exception hierarchy:
    MimirError
    ├── MimirConnectionError  — cannot reach API
    ├── MimirNotFoundError    — 404
    ├── MimirConflictError    — 409
    ├── MimirValidationError  — 422
    ├── MimirServerError      — 5xx
    └── MimirTenantError      — missing tenant_id
"""


class MimirError(Exception):
    """Base exception for all Mímir client errors."""


class MimirConnectionError(MimirError):
    """Raised when the Mímir API is unreachable or times out."""


class MimirNotFoundError(MimirError):
    """Raised when a requested resource does not exist (404)."""


class MimirConflictError(MimirError):
    """Raised when a resource already exists (409)."""


class MimirValidationError(MimirError):
    """Raised when request data fails validation (422)."""


class MimirServerError(MimirError):
    """Raised for server-side errors (5xx)."""


class MimirTenantError(MimirError):
    """Raised when a tenant-scoped operation is called without tenant_id."""

    def __init__(self):
        super().__init__(
            "tenant_id is required for this operation. "
            "Set it via MimirClient(tenant_id=...) or MIMIR_TENANT_ID env var."
        )