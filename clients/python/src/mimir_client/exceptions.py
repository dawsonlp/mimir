"""Typed exceptions for Mímir API errors.

All exceptions inherit from MimirError for catch-all handling.
"""


class MimirError(Exception):
    """Base exception for all Mímir client errors."""


class MimirConnectionError(MimirError):
    """Raised when the Mímir API is unreachable."""

    def __init__(self, message: str, base_url: str):
        self.base_url = base_url
        super().__init__(f"Cannot connect to Mímir API at {base_url}: {message}")


class MimirAPIError(MimirError):
    """Raised for unexpected API error responses (4xx/5xx)."""

    def __init__(self, status_code: int, detail: str, endpoint: str):
        self.status_code = status_code
        self.detail = detail
        self.endpoint = endpoint
        super().__init__(f"API error {status_code} on {endpoint}: {detail}")


class MimirNotFoundError(MimirError):
    """Raised when a requested resource does not exist (404)."""

    def __init__(self, resource_type: str, resource_id: str, endpoint: str):
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.endpoint = endpoint
        super().__init__(f"{resource_type} not found: {resource_id}")


class MimirValidationError(MimirError):
    """Raised when request data fails validation (422)."""

    def __init__(self, errors: list, endpoint: str):
        self.errors = errors
        self.endpoint = endpoint
        super().__init__(f"Validation error on {endpoint}: {errors}")


class MimirTenantError(MimirError):
    """Raised when a tenant-scoped operation is called without tenant_id."""

    def __init__(self):
        super().__init__(
            "tenant_id is required for this operation. "
            "Set it via MimirClient(tenant_id=...) or MIMIR_TENANT_ID env var."
        )