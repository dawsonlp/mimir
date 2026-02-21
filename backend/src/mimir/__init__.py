"""Mímir V4 - Knowledge graph and semantic memory API."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mimir")
except PackageNotFoundError:
    __version__ = "dev"
