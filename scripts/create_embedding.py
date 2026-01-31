#!/usr/bin/env python3
"""Create an embedding for an artifact using Ollama and store via Mímir API.

V2.1: Updated to use embedding_type instead of model/dimensions.
Requires the embedding type to be registered first:
  curl -X POST http://localhost:38000/embedding-types \
    -H "Content-Type: application/json" \
    -d '{"code":"nomic-embed-text","display_name":"Nomic Embed Text","provider":"ollama","dimensions":768}'
"""

import httpx
import sys

MIMIR_URL = "http://localhost:38000"
OLLAMA_URL = "http://localhost:11434"
TENANT_ID = 1
EMBEDDING_TYPE = "nomic-embed-text"
MODEL = "nomic-embed-text"


def ensure_embedding_type_exists():
    """Create embedding type if it doesn't exist."""
    # Check if type exists
    resp = httpx.get(f"{MIMIR_URL}/embedding-types/{EMBEDDING_TYPE}")
    if resp.status_code == 200:
        print(f"Embedding type '{EMBEDDING_TYPE}' already registered")
        return

    # Create it
    print(f"Registering embedding type '{EMBEDDING_TYPE}'...")
    resp = httpx.post(
        f"{MIMIR_URL}/embedding-types",
        json={
            "code": EMBEDDING_TYPE,
            "display_name": "Nomic Embed Text",
            "provider": "ollama",
            "dimensions": 768,
            "distance_metric": "cosine",
            "max_tokens": 8192,
            "description": "Local Ollama model for document embeddings",
        },
    )
    if resp.status_code == 201:
        print(f"Created embedding type and vector table")
    elif resp.status_code == 409:
        print(f"Embedding type already exists")
    else:
        resp.raise_for_status()


def main(artifact_id: str):
    # Ensure embedding type is registered
    ensure_embedding_type_exists()

    # Get artifact content
    resp = httpx.get(
        f"{MIMIR_URL}/artifacts/{artifact_id}",
        headers={"X-Tenant-ID": str(TENANT_ID)},
    )
    resp.raise_for_status()
    artifact = resp.json()
    print(f"Artifact: {artifact['title']} ({len(artifact.get('content', ''))} chars)")

    # Generate embedding via Ollama
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": MODEL, "prompt": artifact["content"]},
        timeout=60,
    )
    resp.raise_for_status()
    embedding = resp.json().get("embedding", [])
    print(f"Generated embedding: {len(embedding)} dimensions")

    # Store in Mímir (V2.1 schema: uses embedding_type instead of model/dimensions)
    resp = httpx.post(
        f"{MIMIR_URL}/embeddings",
        headers={"X-Tenant-ID": str(TENANT_ID)},
        json={
            "artifact_id": artifact_id,
            "embedding_type": EMBEDDING_TYPE,
            "embedding": embedding,
        },
    )
    resp.raise_for_status()
    result = resp.json()
    print(f"Created embedding: {result['id']}")
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python create_embedding.py <artifact_uuid>")
        sys.exit(1)
    main(sys.argv[1])