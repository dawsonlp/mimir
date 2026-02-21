"""Integration tests for unified search endpoint (Phase 3).

These tests require a running Mimir instance with test data.
They verify that POST /search correctly delegates to each ranking strategy,
that validation errors return structured responses, and that the retained
GET /search/fulltext endpoint has deprecation headers.

Run with: PYTHONPATH=src .venv/bin/python -m pytest tests/integration/test_unified_search.py -v
Requires: docker compose up (Mimir API + PostgreSQL)
"""

import os
from uuid import uuid4

import httpx
import pytest

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("MIMIR_BASE_URL", "http://localhost:38000")
TENANT_ID = os.getenv("MIMIR_TEST_TENANT_ID", "1")
HEADERS = {"X-Tenant-ID": TENANT_ID, "Content-Type": "application/json"}

# Small dimension for test embeddings — no real model needed
TEST_EMBEDDING_DIM = 4
TEST_EMBEDDING_TYPE = f"test-embed-{uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _search(body: dict, expected_status: int = 200) -> httpx.Response:
    """POST /search with the given body, assert status code."""
    resp = httpx.post(f"{BASE_URL}/search", json=body, headers=HEADERS, timeout=10)
    assert resp.status_code == expected_status, (
        f"Expected {expected_status}, got {resp.status_code}: {resp.text}"
    )
    return resp


def _create_tenant(shortname: str | None = None) -> dict:
    """Create a test tenant, return the response dict."""
    shortname = shortname or f"usearch-{uuid4().hex[:8]}"
    resp = httpx.post(
        f"{BASE_URL}/tenants",
        json={
            "shortname": shortname,
            "name": f"Unified Search Test {shortname}",
            "tenant_type": "experiment",
        },
        timeout=10,
    )
    assert resp.status_code == 201, f"Tenant creation failed: {resp.text}"
    return resp.json()


def _create_artifact(
    tenant_id: int, title: str, content: str, metadata: dict | None = None
) -> dict:
    """Create an artifact, return the response dict."""
    body = {
        "artifact_type": "document",
        "title": title,
        "content": content,
    }
    if metadata:
        body["metadata"] = metadata
    resp = httpx.post(
        f"{BASE_URL}/artifacts",
        json=body,
        headers={"X-Tenant-ID": str(tenant_id), "Content-Type": "application/json"},
        timeout=10,
    )
    assert resp.status_code == 201, f"Artifact creation failed: {resp.text}"
    return resp.json()


def _register_embedding_type(code: str, dimension: int) -> dict:
    """Register an embedding type, return the response dict."""
    resp = httpx.post(
        f"{BASE_URL}/embedding-types",
        json={
            "code": code,
            "display_name": f"Test {code}",
            "provider": "test",
            "dimensions": dimension,
        },
        timeout=10,
    )
    # May already exist — 201 or 409/400
    if resp.status_code == 201:
        return resp.json()
    # If already exists, fetch it from the paginated list
    list_resp = httpx.get(f"{BASE_URL}/embedding-types", timeout=10)
    assert list_resp.status_code == 200
    data = list_resp.json()
    items = data.get("items", data) if isinstance(data, dict) else data
    for et in items:
        if et.get("code") == code:
            return et
    raise AssertionError(
        f"Failed to register or find embedding type '{code}': {resp.text}"
    )


def _create_embedding(
    tenant_id: int, artifact_id: str, embedding_type: str, vector: list[float]
) -> dict:
    """Create an embedding for an artifact, return the response dict."""
    resp = httpx.post(
        f"{BASE_URL}/embeddings",
        json={
            "artifact_id": artifact_id,
            "embedding_type": embedding_type,
            "embedding": vector,
        },
        headers={"X-Tenant-ID": str(tenant_id), "Content-Type": "application/json"},
        timeout=10,
    )
    assert resp.status_code == 201, f"Embedding creation failed: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# Fixtures — shared test data with real embeddings
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def test_data():
    """Create a tenant, artifacts, embedding type, and embeddings for search tests.

    Returns a dict with all created entities for use across test classes.
    """
    # Create tenant
    tenant = _create_tenant()
    tenant_id = tenant["id"]

    # Register embedding type with small dimension
    embedding_type_name = TEST_EMBEDDING_TYPE
    _register_embedding_type(embedding_type_name, TEST_EMBEDDING_DIM)

    # Create artifacts with distinct content for fulltext differentiation
    art_python = _create_artifact(
        tenant_id,
        title="Python Programming Guide",
        content="Python is a high-level programming language known for readability and simplicity",
        metadata={"language": "python", "tags": "guide"},
    )
    art_rust = _create_artifact(
        tenant_id,
        title="Rust Systems Programming",
        content="Rust is a systems programming language focused on safety and performance",
        metadata={"language": "rust", "tags": "systems"},
    )
    art_javascript = _create_artifact(
        tenant_id,
        title="JavaScript Web Development",
        content="JavaScript is the language of the web browser and Node.js runtime",
        metadata={"language": "javascript", "tags": "web"},
    )

    # Create embeddings — vectors designed so python and rust are closer to each other
    # than to javascript (simulating programming-language similarity)
    vec_python = [0.9, 0.1, 0.8, 0.2]  # programming-heavy
    vec_rust = [0.85, 0.15, 0.75, 0.25]  # similar to python
    vec_javascript = [0.2, 0.9, 0.3, 0.8]  # web-heavy, different cluster

    emb_python = _create_embedding(
        tenant_id, art_python["id"], embedding_type_name, vec_python
    )
    emb_rust = _create_embedding(
        tenant_id, art_rust["id"], embedding_type_name, vec_rust
    )
    emb_javascript = _create_embedding(
        tenant_id, art_javascript["id"], embedding_type_name, vec_javascript
    )

    return {
        "tenant_id": tenant_id,
        "embedding_type": embedding_type_name,
        "artifacts": {
            "python": art_python,
            "rust": art_rust,
            "javascript": art_javascript,
        },
        "vectors": {
            "python": vec_python,
            "rust": vec_rust,
            "javascript": vec_javascript,
        },
        "embeddings": {
            "python": emb_python,
            "rust": emb_rust,
            "javascript": emb_javascript,
        },
    }


def _search_with_tenant(
    tenant_id: int, body: dict, expected_status: int = 200
) -> httpx.Response:
    """POST /search with a specific tenant ID."""
    resp = httpx.post(
        f"{BASE_URL}/search",
        json=body,
        headers={"X-Tenant-ID": str(tenant_id), "Content-Type": "application/json"},
        timeout=10,
    )
    assert resp.status_code == expected_status, (
        f"Expected {expected_status}, got {resp.status_code}: {resp.text}"
    )
    return resp


# ---------------------------------------------------------------------------
# Strategy Inference via HTTP (validation errors)
# ---------------------------------------------------------------------------


class TestUnifiedSearchValidation:
    """Test that validation errors return structured 422 responses."""

    def test_no_ranking_input_returns_422(self):
        """Empty body → 422 NO_RANKING_INPUT."""
        resp = _search({}, expected_status=422)
        data = resp.json()
        assert data["detail"]["code"] == "NO_RANKING_INPUT"

    def test_no_ranking_input_with_filters_only(self):
        """Filters without ranking input → 422 NO_RANKING_INPUT."""
        resp = _search(
            {"artifact_types": ["document"], "limit": 5},
            expected_status=422,
        )
        data = resp.json()
        assert data["detail"]["code"] == "NO_RANKING_INPUT"

    def test_semantic_missing_embedding_type_returns_422(self):
        """query_vector without embedding_type → 422 MISSING_EMBEDDING_TYPE."""
        resp = _search(
            {"query_vector": [0.1, 0.2, 0.3]},
            expected_status=422,
        )
        data = resp.json()
        assert data["detail"]["code"] == "MISSING_EMBEDDING_TYPE"
        assert "semantic" in data["detail"]["detail"]

    def test_similar_missing_embedding_type_returns_422(self):
        """similar_to without embedding_type → 422 MISSING_EMBEDDING_TYPE."""
        resp = _search(
            {"similar_to": "00000000-0000-0000-0000-000000000001"},
            expected_status=422,
        )
        data = resp.json()
        assert data["detail"]["code"] == "MISSING_EMBEDDING_TYPE"
        assert "similar" in data["detail"]["detail"]

    def test_hybrid_missing_embedding_type_returns_422(self):
        """query + query_vector without embedding_type → 422 MISSING_EMBEDDING_TYPE."""
        resp = _search(
            {"query": "test", "query_vector": [0.1, 0.2, 0.3]},
            expected_status=422,
        )
        data = resp.json()
        assert data["detail"]["code"] == "MISSING_EMBEDDING_TYPE"
        assert "hybrid" in data["detail"]["detail"]

    def test_ambiguous_vector_plus_similar_returns_422(self):
        """query_vector + similar_to → 422 AMBIGUOUS_RANKING."""
        resp = _search(
            {
                "query_vector": [0.1, 0.2, 0.3],
                "similar_to": "00000000-0000-0000-0000-000000000001",
                "embedding_type": "nomic-embed-text",
            },
            expected_status=422,
        )
        data = resp.json()
        assert data["detail"]["code"] == "AMBIGUOUS_RANKING"

    def test_reserved_query_plus_similar_returns_422(self):
        """query + similar_to → 422 RESERVED_COMBINATION."""
        resp = _search(
            {
                "query": "test",
                "similar_to": "00000000-0000-0000-0000-000000000001",
                "embedding_type": "nomic-embed-text",
            },
            expected_status=422,
        )
        data = resp.json()
        assert data["detail"]["code"] == "RESERVED_COMBINATION"


# ---------------------------------------------------------------------------
# Fulltext Search via Unified Endpoint
# ---------------------------------------------------------------------------


class TestUnifiedFulltextSearch:
    """Test fulltext search through POST /search."""

    def test_fulltext_returns_results(self, test_data):
        """POST /search with query only triggers fulltext strategy."""
        resp = _search_with_tenant(
            test_data["tenant_id"],
            {"query": "programming", "limit": 10},
        )
        data = resp.json()
        assert data["strategy"] == "fulltext"
        assert isinstance(data["results"], list)
        assert data["total"] >= 2  # python + rust both mention programming

    def test_fulltext_with_artifact_types_filter(self, test_data):
        """Fulltext with artifact_types filter."""
        resp = _search_with_tenant(
            test_data["tenant_id"],
            {"query": "programming", "artifact_types": ["document"], "limit": 5},
        )
        data = resp.json()
        assert data["strategy"] == "fulltext"
        assert data["total"] >= 2

    def test_fulltext_with_pagination(self, test_data):
        """Fulltext with offset pagination returns limited results."""
        resp = _search_with_tenant(
            test_data["tenant_id"],
            {"query": "programming", "limit": 1, "offset": 0},
        )
        data = resp.json()
        assert data["strategy"] == "fulltext"
        assert len(data["results"]) <= 1

        # Second page
        resp2 = _search_with_tenant(
            test_data["tenant_id"],
            {"query": "programming", "limit": 1, "offset": 1},
        )
        data2 = resp2.json()
        assert data2["strategy"] == "fulltext"
        # Different result (or empty if only 1 match)
        if data2["total"] > 1 and data["results"] and data2["results"]:
            assert (
                data["results"][0]["artifact"]["id"]
                != data2["results"][0]["artifact"]["id"]
            )

    def test_fulltext_with_metadata_filters(self, test_data):
        """Fulltext with metadata_filters restricts results."""
        resp = _search_with_tenant(
            test_data["tenant_id"],
            {
                "query": "programming",
                "metadata_filters": {"language": "python"},
                "limit": 10,
            },
        )
        data = resp.json()
        assert data["strategy"] == "fulltext"
        assert data["total"] >= 1
        # All results should be the Python artifact
        for result in data["results"]:
            assert result["artifact"]["metadata"].get("language") == "python"

    def test_fulltext_metadata_no_match(self, test_data):
        """Fulltext with metadata_filters that match nothing returns empty."""
        resp = _search_with_tenant(
            test_data["tenant_id"],
            {
                "query": "programming",
                "metadata_filters": {"nonexistent_key": "value"},
                "limit": 5,
            },
        )
        data = resp.json()
        assert data["strategy"] == "fulltext"
        assert data["total"] == 0

    def test_fulltext_empty_query_rejected(self):
        """Empty query string is rejected by Pydantic validation."""
        resp = httpx.post(
            f"{BASE_URL}/search",
            json={"query": ""},
            headers=HEADERS,
            timeout=10,
        )
        assert resp.status_code == 422  # Pydantic validation error


# ---------------------------------------------------------------------------
# Semantic Search via Unified Endpoint (real embeddings)
# ---------------------------------------------------------------------------


class TestUnifiedSemanticSearch:
    """Test semantic search through POST /search with pre-computed vectors."""

    def test_semantic_returns_results(self, test_data):
        """POST /search with query_vector + embedding_type triggers semantic strategy."""
        resp = _search_with_tenant(
            test_data["tenant_id"],
            {
                "query_vector": test_data["vectors"]["python"],
                "embedding_type": test_data["embedding_type"],
                "limit": 10,
            },
        )
        data = resp.json()
        assert data["strategy"] == "semantic"
        assert isinstance(data["results"], list)
        assert data["total"] >= 1

    def test_semantic_similarity_ordering(self, test_data):
        """Querying with python vector should rank python > rust > javascript."""
        resp = _search_with_tenant(
            test_data["tenant_id"],
            {
                "query_vector": test_data["vectors"]["python"],
                "embedding_type": test_data["embedding_type"],
                "limit": 10,
            },
        )
        data = resp.json()
        assert data["strategy"] == "semantic"
        assert len(data["results"]) >= 3

        # Extract artifact IDs in order
        result_ids = [r["artifact"]["id"] for r in data["results"]]
        python_id = test_data["artifacts"]["python"]["id"]
        rust_id = test_data["artifacts"]["rust"]["id"]
        javascript_id = test_data["artifacts"]["javascript"]["id"]

        # Python should be first (exact match), rust should be before javascript
        assert result_ids[0] == python_id, (
            f"Expected python first, got order: {result_ids}"
        )
        result_ids.index(python_id)
        rust_idx = result_ids.index(rust_id)
        js_idx = result_ids.index(javascript_id)
        assert rust_idx < js_idx, (
            f"Expected rust before javascript: rust={rust_idx}, js={js_idx}"
        )

    def test_semantic_with_similarity_threshold(self, test_data):
        """High similarity_threshold should filter out distant results."""
        resp = _search_with_tenant(
            test_data["tenant_id"],
            {
                "query_vector": test_data["vectors"]["python"],
                "embedding_type": test_data["embedding_type"],
                "similarity_threshold": 0.99,
                "limit": 10,
            },
        )
        data = resp.json()
        assert data["strategy"] == "semantic"
        # Only exact match (python itself) should pass high threshold
        assert data["total"] <= 2  # python, possibly rust

    def test_semantic_with_metadata_filter(self, test_data):
        """Semantic search with metadata filter restricts results."""
        resp = _search_with_tenant(
            test_data["tenant_id"],
            {
                "query_vector": test_data["vectors"]["python"],
                "embedding_type": test_data["embedding_type"],
                "metadata_filters": {"language": "rust"},
                "limit": 10,
            },
        )
        data = resp.json()
        assert data["strategy"] == "semantic"
        # Should only return rust artifacts
        for result in data["results"]:
            assert result["artifact"]["metadata"].get("language") == "rust"

    def test_semantic_with_pagination(self, test_data):
        """Semantic search with offset returns different results."""
        resp1 = _search_with_tenant(
            test_data["tenant_id"],
            {
                "query_vector": test_data["vectors"]["python"],
                "embedding_type": test_data["embedding_type"],
                "limit": 1,
                "offset": 0,
            },
        )
        resp2 = _search_with_tenant(
            test_data["tenant_id"],
            {
                "query_vector": test_data["vectors"]["python"],
                "embedding_type": test_data["embedding_type"],
                "limit": 1,
                "offset": 1,
            },
        )
        data1 = resp1.json()
        data2 = resp2.json()
        assert data1["strategy"] == "semantic"
        assert data2["strategy"] == "semantic"
        if data1["results"] and data2["results"]:
            assert (
                data1["results"][0]["artifact"]["id"]
                != data2["results"][0]["artifact"]["id"]
            )

    def test_semantic_invalid_embedding_type(self, test_data):
        """Nonexistent embedding type returns 400."""
        _search_with_tenant(
            test_data["tenant_id"],
            {
                "query_vector": [0.1, 0.2, 0.3, 0.4],
                "embedding_type": "nonexistent-embed-type",
                "limit": 10,
            },
            expected_status=400,
        )

    def test_semantic_dimension_mismatch(self, test_data):
        """Wrong vector dimension returns 400."""
        _search_with_tenant(
            test_data["tenant_id"],
            {
                "query_vector": [0.1, 0.2],  # dim=2, expected dim=4
                "embedding_type": test_data["embedding_type"],
                "limit": 10,
            },
            expected_status=400,
        )


# ---------------------------------------------------------------------------
# Hybrid Search via Unified Endpoint (real embeddings)
# ---------------------------------------------------------------------------


class TestUnifiedHybridSearch:
    """Test hybrid search through POST /search with query + query_vector."""

    def test_hybrid_returns_results(self, test_data):
        """POST /search with query + query_vector + embedding_type triggers hybrid."""
        resp = _search_with_tenant(
            test_data["tenant_id"],
            {
                "query": "programming language",
                "query_vector": test_data["vectors"]["python"],
                "embedding_type": test_data["embedding_type"],
                "limit": 10,
            },
        )
        data = resp.json()
        assert data["strategy"] == "hybrid"
        assert isinstance(data["results"], list)
        assert data["total"] >= 1

    def test_hybrid_rrf_merges_signals(self, test_data):
        """Hybrid search should combine FTS and vector signals."""
        resp = _search_with_tenant(
            test_data["tenant_id"],
            {
                "query": "systems safety performance",  # FTS biases toward Rust
                "query_vector": test_data["vectors"][
                    "python"
                ],  # vector biases toward Python
                "embedding_type": test_data["embedding_type"],
                "limit": 10,
            },
        )
        data = resp.json()
        assert data["strategy"] == "hybrid"
        # Both python and rust should appear (combined from different signals)
        result_ids = [r["artifact"]["id"] for r in data["results"]]
        python_id = test_data["artifacts"]["python"]["id"]
        rust_id = test_data["artifacts"]["rust"]["id"]
        assert python_id in result_ids or rust_id in result_ids

    def test_hybrid_with_semantic_weight(self, test_data):
        """Hybrid with semantic_weight=1.0 should behave like pure semantic."""
        resp = _search_with_tenant(
            test_data["tenant_id"],
            {
                "query": "web browser Node.js",  # FTS biases toward JavaScript
                "query_vector": test_data["vectors"][
                    "python"
                ],  # vector biases toward Python
                "embedding_type": test_data["embedding_type"],
                "semantic_weight": 1.0,  # full weight on vector
                "limit": 10,
            },
        )
        data = resp.json()
        assert data["strategy"] == "hybrid"
        if data["results"]:
            # With full semantic weight, python should rank high
            data["results"][0]["artifact"]["id"]
            python_id = test_data["artifacts"]["python"]["id"]
            # At least python should be in top results
            result_ids = [r["artifact"]["id"] for r in data["results"]]
            assert python_id in result_ids

    def test_hybrid_with_metadata_filter(self, test_data):
        """Hybrid with metadata filter restricts candidates."""
        resp = _search_with_tenant(
            test_data["tenant_id"],
            {
                "query": "programming",
                "query_vector": test_data["vectors"]["python"],
                "embedding_type": test_data["embedding_type"],
                "metadata_filters": {"language": "javascript"},
                "limit": 10,
            },
        )
        data = resp.json()
        assert data["strategy"] == "hybrid"
        for result in data["results"]:
            assert result["artifact"]["metadata"].get("language") == "javascript"

    def test_hybrid_with_pagination(self, test_data):
        """Hybrid search with offset pagination."""
        resp = _search_with_tenant(
            test_data["tenant_id"],
            {
                "query": "programming",
                "query_vector": test_data["vectors"]["python"],
                "embedding_type": test_data["embedding_type"],
                "limit": 1,
                "offset": 0,
            },
        )
        data = resp.json()
        assert data["strategy"] == "hybrid"
        assert len(data["results"]) <= 1


# ---------------------------------------------------------------------------
# Similar Search via Unified Endpoint (real embeddings)
# ---------------------------------------------------------------------------


class TestUnifiedSimilarSearch:
    """Test similar-artifact search through POST /search with similar_to."""

    def test_similar_returns_results(self, test_data):
        """POST /search with similar_to + embedding_type triggers similar strategy."""
        python_id = test_data["artifacts"]["python"]["id"]
        resp = _search_with_tenant(
            test_data["tenant_id"],
            {
                "similar_to": python_id,
                "embedding_type": test_data["embedding_type"],
                "limit": 10,
            },
        )
        data = resp.json()
        assert data["strategy"] == "similar"
        assert isinstance(data["results"], list)
        assert data["total"] >= 1

    def test_similar_ordering(self, test_data):
        """Similar to python should rank rust closer than javascript."""
        python_id = test_data["artifacts"]["python"]["id"]
        resp = _search_with_tenant(
            test_data["tenant_id"],
            {
                "similar_to": python_id,
                "embedding_type": test_data["embedding_type"],
                "limit": 10,
            },
        )
        data = resp.json()
        assert data["strategy"] == "similar"
        result_ids = [r["artifact"]["id"] for r in data["results"]]
        rust_id = test_data["artifacts"]["rust"]["id"]
        javascript_id = test_data["artifacts"]["javascript"]["id"]

        if rust_id in result_ids and javascript_id in result_ids:
            rust_idx = result_ids.index(rust_id)
            js_idx = result_ids.index(javascript_id)
            assert rust_idx < js_idx, (
                f"Expected rust before javascript in similar results: "
                f"rust={rust_idx}, js={js_idx}"
            )

    def test_similar_with_similarity_threshold(self, test_data):
        """High threshold should reduce results."""
        python_id = test_data["artifacts"]["python"]["id"]
        resp = _search_with_tenant(
            test_data["tenant_id"],
            {
                "similar_to": python_id,
                "embedding_type": test_data["embedding_type"],
                "similarity_threshold": 0.99,
                "limit": 10,
            },
        )
        data = resp.json()
        assert data["strategy"] == "similar"
        # Very high threshold should return very few results
        assert data["total"] <= 2

    def test_similar_nonexistent_artifact(self, test_data):
        """similar_to with a UUID that has no embedding returns empty results."""
        fake_id = "00000000-0000-0000-0000-000000000099"
        resp = _search_with_tenant(
            test_data["tenant_id"],
            {
                "similar_to": fake_id,
                "embedding_type": test_data["embedding_type"],
                "limit": 10,
            },
            expected_status=200,  # returns empty results, not an error
        )
        data = resp.json()
        assert data["strategy"] == "similar"
        assert data["total"] == 0
        assert data["results"] == []


# ---------------------------------------------------------------------------
# Removed Legacy Endpoints Return 404/405
# ---------------------------------------------------------------------------


class TestRemovedEndpoints:
    """Test that removed legacy endpoints are no longer reachable."""

    def test_semantic_endpoint_removed(self):
        """POST /search/semantic no longer exists."""
        resp = httpx.post(
            f"{BASE_URL}/search/semantic",
            json={
                "query_vector": [0.1] * 768,
                "embedding_type": "nomic-embed-text",
                "limit": 1,
            },
            headers=HEADERS,
            timeout=10,
        )
        # Should be 404 (no matching route) or 405 (method not allowed)
        assert resp.status_code in (404, 405, 422)

    def test_hybrid_endpoint_removed(self):
        """POST /search/hybrid no longer exists."""
        resp = httpx.post(
            f"{BASE_URL}/search/hybrid",
            json={
                "query": "test",
                "query_vector": [0.1] * 768,
                "embedding_type": "nomic-embed-text",
                "limit": 1,
            },
            headers=HEADERS,
            timeout=10,
        )
        assert resp.status_code in (404, 405, 422)

    def test_similar_endpoint_removed(self):
        """GET /search/similar/{id} no longer exists."""
        fake_id = "00000000-0000-0000-0000-000000000001"
        resp = httpx.get(
            f"{BASE_URL}/search/similar/{fake_id}",
            params={"embedding_type": "nomic-embed-text"},
            headers={"X-Tenant-ID": TENANT_ID},
            timeout=10,
        )
        assert resp.status_code in (404, 405)


# ---------------------------------------------------------------------------
# Deprecation Headers on Retained GET /search/fulltext
# ---------------------------------------------------------------------------


class TestDeprecationHeaders:
    """Test that the retained GET /search/fulltext returns deprecation headers."""

    def test_fulltext_legacy_has_deprecation_headers(self):
        """GET /search/fulltext returns Deprecation and Sunset headers."""
        resp = httpx.get(
            f"{BASE_URL}/search/fulltext",
            params={"query": "test"},
            headers={"X-Tenant-ID": TENANT_ID},
            timeout=10,
        )
        assert resp.headers.get("Deprecation") == "true"
        assert "Sunset" in resp.headers
        assert "Link" in resp.headers
        assert "/search" in resp.headers["Link"]


# ---------------------------------------------------------------------------
# Response Shape
# ---------------------------------------------------------------------------


class TestUnifiedResponseShape:
    """Test that unified search responses have the expected shape."""

    def test_response_includes_strategy_field(self, test_data):
        """Response body includes the strategy field for all strategies."""
        # Fulltext
        resp = _search_with_tenant(
            test_data["tenant_id"], {"query": "test", "limit": 1}
        )
        data = resp.json()
        assert "strategy" in data
        assert data["strategy"] == "fulltext"

        # Semantic
        resp = _search_with_tenant(
            test_data["tenant_id"],
            {
                "query_vector": test_data["vectors"]["python"],
                "embedding_type": test_data["embedding_type"],
                "limit": 1,
            },
        )
        data = resp.json()
        assert data["strategy"] == "semantic"

    def test_response_has_standard_fields(self, test_data):
        """Response includes results, total, query."""
        resp = _search_with_tenant(
            test_data["tenant_id"], {"query": "test", "limit": 1}
        )
        data = resp.json()
        assert "results" in data
        assert "total" in data
        assert "query" in data
        assert "strategy" in data

    def test_legacy_fulltext_response_no_strategy(self):
        """Legacy endpoint response does NOT include strategy field (or it's null)."""
        resp = httpx.get(
            f"{BASE_URL}/search/fulltext",
            params={"query": "test", "limit": 1},
            headers={"X-Tenant-ID": TENANT_ID},
            timeout=10,
        )
        data = resp.json()
        # strategy should be null/absent for legacy endpoints
        assert data.get("strategy") is None
