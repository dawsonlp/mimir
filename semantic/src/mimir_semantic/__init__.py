"""Mímir Semantic Layer - Python client library for intelligent context assembly.

This library provides high-level operations for context assembly, semantic search,
and token budgeting built on top of the Mímir Storage API.

Example
-------
>>> from mimir_semantic import MimirClient
>>> 
>>> async def main():
...     client = MimirClient.from_env()
...     artifact = await client.get_artifact("abc123-...")
...     await client.close()

See Also
--------
- README.md for quick start guide
- docs/design.md for architecture details
- Mímir Storage API docs at {MIMIR_DOCS_URL}
"""

from mimir_semantic.client import MimirClient
from mimir_semantic.config import Settings
from mimir_semantic.exceptions import (
    MimirError,
    MimirAPIError,
    MimirNotFoundError,
    MimirValidationError,
)

__version__ = "0.1.0"

__all__ = [
    "MimirClient",
    "Settings",
    "MimirError",
    "MimirAPIError",
    "MimirNotFoundError",
    "MimirValidationError",
    "__version__",
]