"""Domain objects for embedding results."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    """Immutable result of a single embedding generation call.

    Attributes:
        embedding: The embedding vector as a list of floats.
        model: Model identifier that produced this embedding.
        dimensions: Length of the embedding vector (validated by provider).
        token_count: Token count from the provider API, or None if unavailable.
    """

    embedding: list[float]
    model: str
    dimensions: int
    token_count: int | None = None