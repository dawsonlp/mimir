"""mimir-client — Official Python client for the Mímir Knowledge Graph API."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mimir-client")
except PackageNotFoundError:
    __version__ = "dev"