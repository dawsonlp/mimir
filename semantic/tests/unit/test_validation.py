"""Tests for dimension validation utility."""

import pytest
from hypothesis import given, strategies as st

from mimir_embeddings.exceptions import DimensionMismatchError
from mimir_embeddings.validation import validate_dimensions


def test_validate_dimensions_matching_does_not_raise():
    validate_dimensions([0.1, 0.2, 0.3], expected=3)


def test_validate_dimensions_mismatch_raises():
    with pytest.raises(DimensionMismatchError) as exc_info:
        validate_dimensions([0.1, 0.2], expected=3)
    assert exc_info.value.expected == 3
    assert exc_info.value.actual == 2


def test_validate_dimensions_empty_vector_matching():
    validate_dimensions([], expected=0)


def test_validate_dimensions_empty_vector_mismatch():
    with pytest.raises(DimensionMismatchError):
        validate_dimensions([], expected=1)


def test_validate_dimensions_passes_model_to_error():
    with pytest.raises(DimensionMismatchError) as exc_info:
        validate_dimensions([0.1], expected=2, model="test-model")
    assert exc_info.value.model == "test-model"


def test_validate_dimensions_default_model_is_unknown():
    with pytest.raises(DimensionMismatchError) as exc_info:
        validate_dimensions([0.1], expected=2)
    assert exc_info.value.model == "unknown"


# Property-based tests

@given(
    st.lists(
        st.floats(allow_nan=False, allow_infinity=False),
        min_size=0,
        max_size=2048,
    )
)
def test_validate_dimensions_passes_when_length_matches(vector):
    """Invariant: validation passes iff len(vector) == expected."""
    validate_dimensions(vector, expected=len(vector))


@given(
    st.lists(
        st.floats(allow_nan=False, allow_infinity=False),
        min_size=0,
        max_size=2048,
    ),
    st.integers(min_value=0, max_value=4096),
)
def test_validate_dimensions_raises_iff_length_mismatches(vector, expected):
    """Invariant: raises DimensionMismatchError iff len(vector) != expected."""
    if len(vector) == expected:
        validate_dimensions(vector, expected=expected)
    else:
        with pytest.raises(DimensionMismatchError) as exc_info:
            validate_dimensions(vector, expected=expected)
        assert exc_info.value.expected == expected
        assert exc_info.value.actual == len(vector)