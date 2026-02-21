"""
Integration Test: Basic Bootstrap Workflow

This test demonstrates a complete Mimir workflow from scratch:
1. Create tenant and embedding type
2. Create documents with content
3. Generate analysis using LLM (Ollama)
4. Create relations between artifacts
5. Generate and store embeddings
6. Use semantic search to find relevant context
7. Have an LLM conversation using that context
8. Record the conversation in Mimir
9. Display the results

Prerequisites:
- Mimir API running at http://localhost:38000
- Ollama running at http://localhost:11434 with models:
  - nomic-embed-text (embeddings)
  - llama3.2 (chat model)

Run with: pytest backend/tests/integration/test_bootstrap_workflow.py -v -s
"""

import os
from uuid import uuid4

import httpx
import pytest

# Configuration
MIMIR_API_URL = os.environ.get("MIMIR_API_URL", "http://localhost:38000")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "llama3.2")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
EMBED_DIMENSIONS = 768


class OllamaClient:
    """Helper client for Ollama API calls."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.Client(timeout=120.0)

    def generate_embedding(self, text: str, model: str = EMBED_MODEL) -> list[float]:
        """Generate embedding vector for text."""
        response = self.client.post(
            f"{self.base_url}/api/embeddings",
            json={"model": model, "prompt": text},
        )
        response.raise_for_status()
        return response.json()["embedding"]

    def generate_text(self, prompt: str, model: str = CHAT_MODEL) -> str:
        """Generate text response from prompt."""
        response = self.client.post(
            f"{self.base_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
        )
        response.raise_for_status()
        return response.json()["response"]

    def chat(self, messages: list[dict], model: str = CHAT_MODEL) -> str:
        """Chat completion with message history."""
        response = self.client.post(
            f"{self.base_url}/api/chat",
            json={"model": model, "messages": messages, "stream": False},
        )
        response.raise_for_status()
        return response.json()["message"]["content"]

    def close(self):
        self.client.close()


class MimirClient:
    """Helper client for Mimir API calls."""

    def __init__(self, base_url: str, tenant_id: int | None = None):
        self.base_url = base_url
        self.tenant_id = tenant_id
        self.client = httpx.Client(timeout=30.0)

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.tenant_id:
            headers["X-Tenant-ID"] = str(self.tenant_id)
        return headers

    def health(self) -> dict:
        """Check API health."""
        r = self.client.get(f"{self.base_url}/health")
        r.raise_for_status()
        return r.json()

    def create_tenant(self, shortname: str, name: str) -> dict:
        """Create a new tenant."""
        r = self.client.post(
            f"{self.base_url}/tenants",
            headers={"Content-Type": "application/json"},
            json={"shortname": shortname, "name": name, "tenant_type": "experiment"},
        )
        r.raise_for_status()
        return r.json()

    def create_embedding_type(
        self, code: str, display_name: str, provider: str, dimensions: int
    ) -> dict:
        """Create embedding type (creates vector table)."""
        r = self.client.post(
            f"{self.base_url}/embedding-types",
            headers={"Content-Type": "application/json"},
            json={
                "code": code,
                "display_name": display_name,
                "provider": provider,
                "dimensions": dimensions,
            },
        )
        if r.status_code == 409:
            return self.get_embedding_type(code)
        r.raise_for_status()
        return r.json()

    def get_embedding_type(self, code: str) -> dict:
        """Get embedding type by code."""
        r = self.client.get(f"{self.base_url}/embedding-types/{code}")
        r.raise_for_status()
        return r.json()

    def create_artifact(
        self, artifact_type: str, title: str, content: str, metadata: dict | None = None
    ) -> dict:
        """Create an artifact."""
        r = self.client.post(
            f"{self.base_url}/artifacts",
            headers=self._headers(),
            json={
                "artifact_type": artifact_type,
                "title": title,
                "content": content,
                "metadata": metadata or {},
            },
        )
        r.raise_for_status()
        return r.json()

    def get_artifact(self, artifact_id: str) -> dict:
        """Get artifact by ID."""
        r = self.client.get(
            f"{self.base_url}/artifacts/{artifact_id}", headers=self._headers()
        )
        r.raise_for_status()
        return r.json()

    def create_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        confidence: float = 1.0,
    ) -> dict:
        """Create a relation between artifacts."""
        r = self.client.post(
            f"{self.base_url}/relations",
            headers=self._headers(),
            json={
                "source_id": source_id,
                "target_id": target_id,
                "relation_type": relation_type,
                "confidence": confidence,
            },
        )
        r.raise_for_status()
        return r.json()

    def create_embedding(
        self, artifact_id: str, embedding_type: str, embedding: list[float]
    ) -> dict:
        """Store an embedding for an artifact."""
        r = self.client.post(
            f"{self.base_url}/embeddings",
            headers=self._headers(),
            json={
                "artifact_id": artifact_id,
                "embedding_type": embedding_type,
                "embedding": embedding,
            },
        )
        r.raise_for_status()
        return r.json()

    def similarity_search(
        self, query_vector: list[float], embedding_type: str, limit: int = 10
    ) -> dict:
        """Search for similar embeddings."""
        r = self.client.post(
            f"{self.base_url}/embeddings/similar",
            headers=self._headers(),
            json={
                "query_vector": query_vector,
                "embedding_type": embedding_type,
                "limit": limit,
            },
        )
        r.raise_for_status()
        return r.json()

    def get_context(self, artifact_id: str) -> dict:
        """Get full context for an artifact."""
        r = self.client.post(
            f"{self.base_url}/context/{artifact_id}",
            headers=self._headers(),
            json={},  # POST requires body
        )
        r.raise_for_status()
        return r.json()

    def close(self):
        self.client.close()


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'=' * 60}\n {title}\n{'=' * 60}")


@pytest.mark.integration
class TestBootstrapWorkflow:
    """Complete bootstrap workflow test."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up clients."""
        self.mimir = MimirClient(MIMIR_API_URL)
        self.ollama = OllamaClient(OLLAMA_URL)
        yield
        self.mimir.close()
        self.ollama.close()

    def test_full_workflow(self):
        """Execute the complete workflow."""

        # Step 1: Verify API Health
        print_section("Step 1: Verify API Health")
        health = self.mimir.health()
        assert health["status"] == "healthy", f"API not healthy: {health}"
        print(f"✓ Mimir API is healthy (version: {health.get('version', 'unknown')})")

        # Step 2: Create Tenant
        print_section("Step 2: Create Tenant")
        tenant = self.mimir.create_tenant(
            shortname=f"workflow-{uuid4().hex[:8]}",
            name="Bootstrap Workflow Test",
        )
        self.mimir.tenant_id = tenant["id"]
        print(f"✓ Created tenant: {tenant['shortname']} (ID: {tenant['id']})")

        # Step 3: Create Embedding Type
        print_section("Step 3: Create Embedding Type")
        emb_type = self.mimir.create_embedding_type(
            code="nomic",
            display_name="Nomic",
            provider="ollama",
            dimensions=EMBED_DIMENSIONS,
        )
        print(f"✓ Embedding type: {emb_type['code']} ({emb_type['dimensions']} dims)")

        # Step 4: Create Documents
        print_section("Step 4: Create Documents")
        doc1_content = """PostgreSQL Performance Optimization Guide

PostgreSQL is a powerful database. Key optimizations include:
1. Index Optimization - Create indexes on frequently queried columns
2. Connection Pooling - Use PgBouncer to reduce overhead
3. Query Optimization - Avoid SELECT *, use LIMIT for pagination
4. Configuration Tuning - Adjust shared_buffers and work_mem"""

        doc1 = self.mimir.create_artifact(
            artifact_type="document",
            title="PostgreSQL Performance Guide",
            content=doc1_content,
        )
        assert doc1["content"] is not None, "Document 1 content is null!"
        print(f"✓ Created Document 1: {doc1['title']}")

        doc2_content = """Vector Search with pgvector Extension

pgvector enables similarity search on vector embeddings. It supports:
- L2 distance (Euclidean)
- Cosine distance
- Inner product

Use HNSW indexes for fast retrieval."""

        doc2 = self.mimir.create_artifact(
            artifact_type="document", title="pgvector Guide", content=doc2_content
        )
        assert doc2["content"] is not None, "Document 2 content is null!"
        print(f"✓ Created Document 2: {doc2['title']}")

        # Step 5: Verify Document Retrieval
        print_section("Step 5: Verify Document Retrieval")
        retrieved_doc1 = self.mimir.get_artifact(doc1["id"])
        assert retrieved_doc1["content"] is not None, "Retrieved doc1 content is null!"
        print(
            f"✓ Document 1 content retrieved ({len(retrieved_doc1['content'])} chars)"
        )

        retrieved_doc2 = self.mimir.get_artifact(doc2["id"])
        assert retrieved_doc2["content"] is not None, "Retrieved doc2 content is null!"
        print(
            f"✓ Document 2 content retrieved ({len(retrieved_doc2['content'])} chars)"
        )

        # Step 6: Generate Analysis with LLM
        print_section("Step 6: Generate Analysis with Ollama")
        analysis_prompt = f"""Analyze this document briefly (under 100 words):
{retrieved_doc1["content"]}

Analysis:"""
        print(f"  Calling Ollama ({CHAT_MODEL})...")
        analysis_text = self.ollama.generate_text(analysis_prompt)
        print(f"✓ Generated analysis ({len(analysis_text)} chars)")

        # Step 7: Store Analysis Artifact
        print_section("Step 7: Store Analysis Artifact")
        analysis = self.mimir.create_artifact(
            artifact_type="analysis",
            title=f"Analysis of {doc1['title']}",
            content=analysis_text,
            metadata={"model": CHAT_MODEL},
        )
        print(f"✓ Created Analysis: {analysis['title']}")

        # Step 8: Create Relations
        print_section("Step 8: Create Relations")
        self.mimir.create_relation(analysis["id"], doc1["id"], "derived_from")
        print("✓ Relation: Analysis --derived_from--> Document 1")
        self.mimir.create_relation(doc2["id"], doc1["id"], "references")
        print("✓ Relation: Document 2 --references--> Document 1")

        # Step 9: Generate Embeddings
        print_section("Step 9: Generate Embeddings")
        artifacts = [
            (doc1["id"], retrieved_doc1["content"], "Doc1"),
            (doc2["id"], retrieved_doc2["content"], "Doc2"),
            (analysis["id"], analysis_text, "Analysis"),
        ]
        for art_id, content, name in artifacts:
            print(f"  Generating embedding for {name}...")
            emb = self.ollama.generate_embedding(content)
            assert len(emb) == EMBED_DIMENSIONS, f"Wrong dims: {len(emb)}"
            self.mimir.create_embedding(art_id, "nomic", emb)
            print(f"  ✓ Stored embedding for {name}")

        # Step 10: Semantic Search
        print_section("Step 10: Semantic Search")
        query = "How do I optimize database queries?"
        print(f"  Query: '{query}'")
        query_emb = self.ollama.generate_embedding(query)
        results = self.mimir.similarity_search(query_emb, "nomic", limit=5)
        print(f"✓ Found {results['total']} similar artifacts:")
        for i, r in enumerate(results["results"], 1):
            print(f"  {i}. {r['artifact_id'][:8]}... (sim: {r['similarity']:.3f})")

        # Step 11: Get Context
        print_section("Step 11: Get Context")
        if results["results"]:
            top_id = results["results"][0]["artifact_id"]
            ctx = self.mimir.get_context(top_id)
            print(
                f"✓ Context for {top_id[:8]}...: {len(ctx.get('relations', []))} relations"
            )

        # Step 12: LLM Conversation
        print_section("Step 12: LLM Conversation")
        context_str = f"Doc1: {retrieved_doc1['content'][:300]}...\nDoc2: {retrieved_doc2['content'][:300]}..."
        question = (
            "What are the top 3 things to do for PostgreSQL vector search performance?"
        )
        messages = [
            {"role": "system", "content": "You are a database expert."},
            {"role": "user", "content": f"{context_str}\n\nQuestion: {question}"},
        ]
        print(f"  Calling Ollama ({CHAT_MODEL}) with context...")
        llm_response = self.ollama.chat(messages)
        print(f"✓ Response ({len(llm_response)} chars): {llm_response[:100]}...")

        # Step 13: Store Conversation
        print_section("Step 13: Store Conversation")
        conv_content = f"User: {question}\n\nAssistant: {llm_response}"
        conversation = self.mimir.create_artifact(
            artifact_type="conversation",
            title="PostgreSQL Vector Search Q&A",
            content=conv_content,
            metadata={"model": CHAT_MODEL},
        )
        print(f"✓ Created Conversation: {conversation['title']}")

        # Link conversation to sources
        for src_id in [doc1["id"], doc2["id"], analysis["id"]]:
            self.mimir.create_relation(conversation["id"], src_id, "derived_from")
        print("✓ Linked conversation to 3 source artifacts")

        # Step 14: Final Summary
        print_section("Step 14: Final Summary")
        print("\nArtifacts Created:")
        print(f"  1. {doc1['title']} ({doc1['id'][:8]}...)")
        print(f"  2. {doc2['title']} ({doc2['id'][:8]}...)")
        print(f"  3. {analysis['title']} ({analysis['id'][:8]}...)")
        print(f"  4. {conversation['title']} ({conversation['id'][:8]}...)")
        print(
            "\nRelations: Analysis derived_from Doc1, Doc2 refs Doc1, Conversation derived_from all"
        )
        print(f"\nEmbeddings: 3 vectors ({EMBED_DIMENSIONS} dims)")
        print("\n" + "=" * 60)
        print(" CONVERSATION")
        print("=" * 60)
        print(f"\nQ: {question}\n\nA: {llm_response}")
        print("\n" + "=" * 60)
        print(" ✅ WORKFLOW COMPLETE")
        print("=" * 60)
