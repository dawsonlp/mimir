"""Parser for Apache AGE agtype values.

AGE returns all values as Python str via psycopg. Vertices and edges have
``::vertex`` / ``::edge`` suffixes that must be stripped before JSON parsing.
Collections (paths, nodes(), relationships()) embed these suffixes within
the JSON array string.

This module provides two pure functions — no I/O, no side effects — for
converting raw agtype strings into Python dicts/lists.

Reference: AGE 1.7.0 agtype format (validated by spike in scripts/age_cypher_spike.py)
"""

import json
import re

# Regex to strip ::vertex or ::edge suffix at end of string
_SUFFIX_RE = re.compile(r"::(?:vertex|edge)\s*$")

# Regex to strip all ::vertex / ::edge suffixes within a collection string
_COLLECTION_SUFFIX_RE = re.compile(r"::(?:vertex|edge)")


def parse_agtype_value(raw: str | None) -> dict | str | int | float | bool | None:
    """Parse a single agtype value returned by AGE.

    Handles:
    - None / null → None
    - Vertex: ``'{...}::vertex'`` → dict
    - Edge: ``'{...}::edge'`` → dict
    - Scalar string: ``'"derived_from"'`` → ``"derived_from"``
    - Scalar integer: ``'1'`` → ``1``
    - Scalar float: ``'3.14'`` → ``3.14``
    - Scalar boolean: ``'true'`` / ``'false'`` → ``True`` / ``False``

    Args:
        raw: The raw string value from an agtype column, or None.

    Returns:
        Parsed Python value.

    Raises:
        ValueError: If the string cannot be parsed.
    """
    if raw is None:
        return None

    if not isinstance(raw, str):
        return raw

    # Strip ::vertex or ::edge suffix
    cleaned = _SUFFIX_RE.sub("", raw)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to parse agtype value: {raw!r}"
        ) from exc


def parse_agtype_collection(raw: str | None) -> list[dict]:
    """Parse an agtype collection (path, nodes(), relationships()).

    AGE collections are JSON arrays with ``::vertex`` / ``::edge`` suffixes
    interspersed within the array elements::

        '[{"id": 1, ...}::vertex, {"id": 2, ...}::edge, {"id": 3, ...}::vertex]'

    This function strips all such suffixes, then parses as a JSON array.

    Args:
        raw: The raw string from an agtype column, or None.

    Returns:
        List of parsed dicts. Empty list if raw is None or empty.

    Raises:
        ValueError: If the string cannot be parsed after suffix stripping.
    """
    if raw is None:
        return []

    if not isinstance(raw, str):
        return []

    stripped = raw.strip()
    if not stripped:
        return []

    # Strip all ::vertex / ::edge suffixes within the collection
    cleaned = _COLLECTION_SUFFIX_RE.sub("", stripped)

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to parse agtype collection: {raw!r}"
        ) from exc

    if not isinstance(result, list):
        raise ValueError(
            f"Expected JSON array from agtype collection, got {type(result).__name__}: {raw!r}"
        )

    return result