"""Dimension validation utilities."""

from mimir_embeddings.exceptions import DimensionMismatchError


def validate_dimensions(
    vector: list[float], expected: int, model: str = "unknown"
) -> None:
    """Raise DimensionMismatchError if vector length does not match expected.

    Providers call this internally on every result. Exposed publicly for
    callers who need to validate vectors from other sources.
    """
    actual = len(vector)
    if actual != expected:
        raise DimensionMismatchError(expected=expected, actual=actual, model=model)