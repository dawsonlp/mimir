"""Ollama embedding provider for local embeddings.

Uses Ollama's REST API for embedding generation.
No API key required - runs locally.
"""

import httpx
import structlog
from mimir.services.embedding_providers.base import (
    EmbeddingModelInfo,
    EmbeddingProvider,
    EmbeddingResult,
)

logger = structlog.get_logger()


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Ollama embedding provider for local model inference.

    Supports any embedding model available in Ollama.
    Common models: nomic-embed-text, mxbai-embed-large, all-minilm, bge-large
    """

    # Well-known Ollama embedding models with their specs
    KNOWN_MODELS: dict[str, dict] = {
        "nomic-embed-text": {
            "dimensions": 768,
            "max_tokens": 8192,
            "description": "Nomic's text embedding model - good balance of quality and speed",
        },
        "mxbai-embed-large": {
            "dimensions": 1024,
            "max_tokens": 512,
            "description": "High quality embeddings, larger model",
        },
        "snowflake-arctic-embed": {
            "dimensions": 1024,
            "max_tokens": 8192,
            "description": "Snowflake's Arctic embedding model",
        },
        "all-minilm": {
            "dimensions": 384,
            "max_tokens": 256,
            "description": "Fast, lightweight embedding model",
        },
        "bge-large": {
            "dimensions": 1024,
            "max_tokens": 512,
            "description": "BAAI's General Embedding - large variant",
        },
        "bge-base": {
            "dimensions": 768,
            "max_tokens": 512,
            "description": "BAAI's General Embedding - base variant",
        },
    }

    def __init__(self, base_url: str | None = None):
        """Initialize Ollama provider.

        Args:
            base_url: Ollama server URL. If None, reads from OLLAMA_BASE_URL env var
                     or defaults to http://localhost:11434
        """
        if base_url is None:
            from mimir.config import get_settings
            settings = get_settings()
            base_url = settings.ollama_base_url
        self._base_url = base_url.rstrip("/")
        self._available_models: list[str] | None = None

    @property
    def provider_name(self) -> str:
        """Return provider identifier."""
        return "ollama"

    def _get_model_spec(self, model_id: str) -> dict:
        """Get model specifications, using known specs or defaults."""
        # Strip any tag suffix for lookup
        base_model = model_id.split(":")[0]
        return self.KNOWN_MODELS.get(base_model, {
            "dimensions": 768,  # Default assumption
            "max_tokens": 2048,
            "description": f"Ollama model: {model_id}",
        })

    async def _fetch_available_models(self) -> list[str]:
        """Fetch list of available embedding models from Ollama."""
        if self._available_models is not None:
            return self._available_models

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    # Filter for likely embedding models
                    embedding_keywords = ["embed", "minilm", "bge", "e5", "arctic"]
                    models = []
                    for model in data.get("models", []):
                        name = model.get("name", "")
                        if any(kw in name.lower() for kw in embedding_keywords):
                            models.append(name)
                    self._available_models = models
                    return models
        except Exception as e:
            await logger.awarning(
                "Failed to fetch Ollama models",
                error=str(e),
            )

        self._available_models = []
        return []

    def list_models(self) -> list[EmbeddingModelInfo]:
        """List known embedding models.

        Note: For dynamic discovery, call _fetch_available_models() async.
        """
        return [
            EmbeddingModelInfo(
                model_id=model_id,
                provider="ollama",
                display_name=model_id.replace("-", " ").title(),
                dimensions=spec["dimensions"],
                max_tokens=spec["max_tokens"],
                description=spec["description"],
            )
            for model_id, spec in self.KNOWN_MODELS.items()
        ]

    def get_model_info(self, model_id: str) -> EmbeddingModelInfo | None:
        """Get information about a specific model."""
        spec = self._get_model_spec(model_id)
        return EmbeddingModelInfo(
            model_id=model_id,
            provider="ollama",
            display_name=model_id.replace("-", " ").title(),
            dimensions=spec["dimensions"],
            max_tokens=spec["max_tokens"],
            description=spec["description"],
        )

    async def generate_embedding(
        self, text: str, model_id: str = "nomic-embed-text"
    ) -> EmbeddingResult:
        """Generate embedding using Ollama.

        Args:
            text: Text to embed
            model_id: Ollama model name (default: nomic-embed-text)

        Returns:
            EmbeddingResult with vector and metadata
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    f"{self._base_url}/api/embeddings",
                    json={
                        "model": model_id,
                        "prompt": text,
                    },
                )
                response.raise_for_status()
                data = response.json()

                embedding = data.get("embedding", [])
                spec = self._get_model_spec(model_id)

                await logger.adebug(
                    "Generated Ollama embedding",
                    model=model_id,
                    dimensions=len(embedding),
                    text_preview=text[:50] + "..." if len(text) > 50 else text,
                )

                return EmbeddingResult(
                    embedding=embedding,
                    model_id=model_id,
                    dimensions=len(embedding),
                    tokens_used=None,  # Ollama doesn't report token usage
                )

            except httpx.HTTPStatusError as e:
                await logger.aerror(
                    "Ollama API error",
                    status_code=e.response.status_code,
                    response_text=e.response.text[:200],
                    model=model_id,
                )
                raise ValueError(f"Ollama API error: {e.response.status_code}")
            except httpx.ConnectError:
                await logger.aerror(
                    "Cannot connect to Ollama",
                    base_url=self._base_url,
                )
                raise ValueError(
                    f"Cannot connect to Ollama at {self._base_url}. "
                    "Is Ollama running? Start with: ollama serve"
                )

    async def generate_embeddings_batch(
        self, texts: list[str], model_id: str = "nomic-embed-text"
    ) -> list[EmbeddingResult]:
        """Generate embeddings for multiple texts.

        Note: Ollama doesn't have native batch support, so we process sequentially.
        For large batches, consider using Voyage AI or OpenAI for better performance.

        Args:
            texts: List of texts to embed
            model_id: Ollama model name

        Returns:
            List of EmbeddingResult objects
        """
        results = []
        for text in texts:
            result = await self.generate_embedding(text, model_id)
            results.append(result)

        await logger.ainfo(
            "Generated Ollama embeddings batch",
            model=model_id,
            count=len(results),
        )

        return results

    def is_configured(self) -> bool:
        """Check if Ollama is available.

        Returns True if we can connect to Ollama server.
        """
        import socket

        # Parse host and port from base_url
        try:
            from urllib.parse import urlparse
            parsed = urlparse(self._base_url)
            host = parsed.hostname or "localhost"
            port = parsed.port or 11434

            # Quick socket check
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception:
            return False
