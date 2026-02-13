"""Custom exceptions for Mímir Semantic Layer.

All exceptions inherit from MimirError for easy catching.
"""


class MimirError(Exception):
    """Base exception for all Mímir Semantic Layer errors.
    
    Example
    -------
    >>> try:
    ...     await client.get_artifact("nonexistent")
    ... except MimirError as e:
    ...     print(f"Mímir error: {e}")
    """
    pass


class MimirAPIError(MimirError):
    """Error returned from the Mímir Storage API.
    
    Attributes
    ----------
    status_code : int
        HTTP status code from the API
    detail : str
        Error detail message from the API
    endpoint : str
        The API endpoint that was called
    
    Example
    -------
    >>> try:
    ...     await client.get_artifact("bad-uuid")
    ... except MimirAPIError as e:
    ...     print(f"API error {e.status_code}: {e.detail}")
    """
    
    def __init__(self, status_code: int, detail: str, endpoint: str = ""):
        self.status_code = status_code
        self.detail = detail
        self.endpoint = endpoint
        super().__init__(f"API error {status_code} from {endpoint}: {detail}")


class MimirNotFoundError(MimirAPIError):
    """Resource not found (HTTP 404).
    
    Raised when a requested artifact, relation, or other resource
    does not exist in the storage layer.
    
    Example
    -------
    >>> try:
    ...     artifact = await client.get_artifact("nonexistent-uuid")
    ... except MimirNotFoundError:
    ...     print("Artifact not found")
    """
    
    def __init__(self, resource_type: str, resource_id: str, endpoint: str = ""):
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(
            status_code=404,
            detail=f"{resource_type} '{resource_id}' not found",
            endpoint=endpoint,
        )


class MimirValidationError(MimirAPIError):
    """Validation error (HTTP 422).
    
    Raised when the API rejects a request due to invalid data.
    
    Attributes
    ----------
    errors : list[dict]
        List of validation error details from the API
    
    Example
    -------
    >>> try:
    ...     await client.create_artifact(artifact_type="", title="")
    ... except MimirValidationError as e:
    ...     for error in e.errors:
    ...         print(f"Field {error['loc']}: {error['msg']}")
    """
    
    def __init__(self, errors: list[dict], endpoint: str = ""):
        self.errors = errors
        detail = "; ".join(
            f"{'.'.join(str(p) for p in e.get('loc', []))}: {e.get('msg', '')}"
            for e in errors
        )
        super().__init__(
            status_code=422,
            detail=detail,
            endpoint=endpoint,
        )


class MimirConnectionError(MimirError):
    """Failed to connect to the Mímir Storage API.
    
    Raised when the HTTP connection fails, times out, or the
    API is unreachable.
    
    Example
    -------
    >>> try:
    ...     await client.health()
    ... except MimirConnectionError:
    ...     print("Cannot reach Mímir API")
    """
    
    def __init__(self, message: str, url: str = ""):
        self.url = url
        super().__init__(f"Connection error to {url}: {message}")


class MimirTenantError(MimirError):
    """Tenant ID not configured or invalid.
    
    Raised when an operation requires a tenant ID but none
    was provided.
    
    Example
    -------
    >>> client = MimirClient(base_url="...", tenant_id=None)
    >>> await client.create_artifact(...)  # Raises MimirTenantError
    """
    
    def __init__(self, message: str = "Tenant ID required for this operation"):
        super().__init__(message)