"""
Performance test for Phase 1 hierarchy scoping (recursive CTE).

Creates a realistic 3-level hierarchy (~200 artifacts) in a test tenant,
times the recursive CTE query, and verifies correctness.

Requires: docker compose up (PostgreSQL running on port 35432)

Run: cd backend && .venv/bin/python -m pytest tests/integration/test_hierarchy_performance.py -v -s
"""

import os
import time
from uuid import uuid4

import psycopg
import pytest

# Database connection — uses the docker compose PostgreSQL
DB_URL = os.environ.get(
    "DATABASE_URL",
    f"postgresql://mimir:{os.environ.get('POSTGRES_PASSWORD', 'mimir')}@localhost:35432/mimir",
)

SCHEMA = "mimirdata"


def _get_connection():
    """Get a synchronous connection to the test database."""
    return psycopg.connect(DB_URL)


def _ensure_test_tenant(conn, tenant_id: int = 99999) -> int:
    """Create or verify a test tenant exists. Returns tenant_id."""
    # Check if tenant_type 'experiment' exists
    row = conn.execute(
        f"SELECT code FROM {SCHEMA}.tenant_type WHERE code = 'experiment'"
    ).fetchone()
    if not row:
        conn.execute(
            f"INSERT INTO {SCHEMA}.tenant_type (code, display_name) VALUES ('experiment', 'Experiment') ON CONFLICT DO NOTHING"
        )

    # Check if test tenant exists
    row = conn.execute(
        f"SELECT id FROM {SCHEMA}.tenant WHERE id = %s", (tenant_id,)
    ).fetchone()
    if not row:
        conn.execute(
            f"""
            INSERT INTO {SCHEMA}.tenant (id, shortname, name, tenant_type)
            VALUES (%s, %s, %s, 'experiment')
            ON CONFLICT DO NOTHING
            """,
            (tenant_id, f"perf-test-{tenant_id}", "Performance Test Tenant"),
        )
    conn.commit()
    return tenant_id


def _ensure_artifact_type(conn, code: str = "document") -> str:
    """Ensure an artifact type exists. Returns code."""
    conn.execute(
        f"""
        INSERT INTO {SCHEMA}.artifact_type (code, display_name)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING
        """,
        (code, code.title()),
    )
    conn.commit()
    return code


def _create_hierarchy(conn, tenant_id: int) -> dict:
    """Create a 3-level hierarchy: 1 project → 10 files → ~19 chunks each ≈ 200 artifacts.

    Returns dict with:
        project_id: UUID of root
        file_ids: list of file UUIDs
        chunk_ids: list of chunk UUIDs
        total_count: total artifact count including root
    """
    project_type = _ensure_artifact_type(conn, "project")
    file_type = _ensure_artifact_type(conn, "file")
    chunk_type = _ensure_artifact_type(conn, "chunk")

    # Level 1: Project (root)
    project_id = uuid4()
    conn.execute(
        f"""
        INSERT INTO {SCHEMA}.artifact (id, tenant_id, artifact_type, title, content)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (str(project_id), tenant_id, project_type, "Perf Test Project", "Root project"),
    )

    # Level 2: Files
    file_ids = []
    for i in range(10):
        file_id = uuid4()
        file_ids.append(file_id)
        conn.execute(
            f"""
            INSERT INTO {SCHEMA}.artifact (id, tenant_id, artifact_type, parent_artifact_id, title, content)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (str(file_id), tenant_id, file_type, str(project_id), f"File {i}", f"File content {i}"),
        )

    # Level 3: Chunks (~19 per file = ~190 chunks)
    chunk_ids = []
    for file_id in file_ids:
        for j in range(19):
            chunk_id = uuid4()
            chunk_ids.append(chunk_id)
            conn.execute(
                f"""
                INSERT INTO {SCHEMA}.artifact (id, tenant_id, artifact_type, parent_artifact_id, title, content)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (str(chunk_id), tenant_id, chunk_type, str(file_id), f"Chunk {j}", f"Chunk content {j}"),
            )

    conn.commit()

    total = 1 + len(file_ids) + len(chunk_ids)
    return {
        "project_id": project_id,
        "file_ids": file_ids,
        "chunk_ids": chunk_ids,
        "total_count": total,
    }


def _cleanup_hierarchy(conn, tenant_id: int):
    """Delete all artifacts for the test tenant."""
    conn.execute(
        f"DELETE FROM {SCHEMA}.artifact WHERE tenant_id = %s",
        (tenant_id,),
    )
    conn.commit()


def _run_recursive_cte(conn, tenant_id: int, scope_id, explain: bool = False) -> tuple[list, float]:
    """Run the recursive CTE and time it.

    Returns (list of descendant IDs, elapsed_ms).
    """
    cte_sql = f"""
        WITH RECURSIVE descendants AS (
            SELECT id
            FROM {SCHEMA}.artifact
            WHERE id = %s AND tenant_id = %s

            UNION ALL

            SELECT a.id
            FROM {SCHEMA}.artifact a
            INNER JOIN descendants d ON a.parent_artifact_id = d.id
            WHERE a.tenant_id = %s
        )
        SELECT id FROM descendants
    """

    params = (str(scope_id), tenant_id, tenant_id)

    if explain:
        # Run EXPLAIN ANALYZE for diagnostics
        explain_result = conn.execute(f"EXPLAIN ANALYZE {cte_sql}", params).fetchall()
        for row in explain_result:
            print(f"  {row[0]}")

    # Timed run
    start = time.perf_counter()
    rows = conn.execute(cte_sql, params).fetchall()
    elapsed_ms = (time.perf_counter() - start) * 1000

    return [row[0] for row in rows], elapsed_ms


# =============================================================================
# Tests
# =============================================================================


@pytest.mark.integration
class TestHierarchyScopingPerformance:
    """Performance tests for recursive CTE hierarchy scoping.

    Tests use a 3-level hierarchy: 1 project → 10 files → 19 chunks = 201 artifacts.
    """

    @pytest.fixture(scope="class")
    def db_conn(self):
        """Provide a database connection for the test class."""
        conn = _get_connection()
        yield conn
        conn.close()

    @pytest.fixture(scope="class")
    def test_tenant_id(self, db_conn) -> int:
        """Create/verify test tenant."""
        return _ensure_test_tenant(db_conn, tenant_id=99999)

    @pytest.fixture(scope="class")
    def hierarchy(self, db_conn, test_tenant_id) -> dict:
        """Create a 200-artifact hierarchy and clean up after tests."""
        h = _create_hierarchy(db_conn, test_tenant_id)
        yield h
        _cleanup_hierarchy(db_conn, test_tenant_id)

    def test_cte_returns_all_descendants(self, db_conn, test_tenant_id, hierarchy):
        """Recursive CTE from project root should return all 201 artifacts."""
        ids, elapsed_ms = _run_recursive_cte(db_conn, test_tenant_id, hierarchy["project_id"])
        expected = hierarchy["total_count"]

        print(f"\n  CTE returned {len(ids)} descendants in {elapsed_ms:.2f}ms (expected {expected})")

        assert len(ids) == expected, (
            f"Expected {expected} descendants, got {len(ids)}"
        )

    def test_cte_from_file_returns_file_and_chunks(self, db_conn, test_tenant_id, hierarchy):
        """Recursive CTE from a file should return the file + its 19 chunks = 20."""
        file_id = hierarchy["file_ids"][0]
        ids, elapsed_ms = _run_recursive_cte(db_conn, test_tenant_id, file_id)

        print(f"\n  CTE from file returned {len(ids)} descendants in {elapsed_ms:.2f}ms (expected 20)")

        assert len(ids) == 20  # 1 file + 19 chunks

    def test_cte_from_chunk_returns_only_self(self, db_conn, test_tenant_id, hierarchy):
        """Recursive CTE from a leaf chunk should return only itself."""
        chunk_id = hierarchy["chunk_ids"][0]
        ids, elapsed_ms = _run_recursive_cte(db_conn, test_tenant_id, chunk_id)

        print(f"\n  CTE from chunk returned {len(ids)} descendants in {elapsed_ms:.2f}ms (expected 1)")

        assert len(ids) == 1

    def test_cte_nonexistent_scope_returns_empty(self, db_conn, test_tenant_id, hierarchy):
        """Recursive CTE for nonexistent scope anchor returns empty."""
        fake_id = uuid4()
        ids, elapsed_ms = _run_recursive_cte(db_conn, test_tenant_id, fake_id)

        print(f"\n  CTE for nonexistent scope returned {len(ids)} in {elapsed_ms:.2f}ms")

        assert len(ids) == 0

    def test_cte_tenant_isolation(self, db_conn, test_tenant_id, hierarchy):
        """Recursive CTE with wrong tenant_id should return empty."""
        wrong_tenant = test_tenant_id + 1
        ids, elapsed_ms = _run_recursive_cte(db_conn, wrong_tenant, hierarchy["project_id"])

        print(f"\n  CTE with wrong tenant returned {len(ids)} in {elapsed_ms:.2f}ms (expected 0)")

        assert len(ids) == 0

    def test_cte_performance_under_10ms(self, db_conn, test_tenant_id, hierarchy):
        """Recursive CTE for 200-artifact tree should complete in <10ms.

        Runs 10 iterations and checks the median.
        """
        times = []
        for _ in range(10):
            _, elapsed_ms = _run_recursive_cte(db_conn, test_tenant_id, hierarchy["project_id"])
            times.append(elapsed_ms)

        times.sort()
        median_ms = times[len(times) // 2]
        avg_ms = sum(times) / len(times)
        p95_ms = times[int(len(times) * 0.95)]

        print(f"\n  10 iterations: median={median_ms:.2f}ms, avg={avg_ms:.2f}ms, p95={p95_ms:.2f}ms")
        print(f"  All times: {[f'{t:.2f}' for t in times]}")

        assert median_ms < 10, f"Median CTE time {median_ms:.2f}ms exceeds 10ms threshold"

    def test_cte_explain_plan(self, db_conn, test_tenant_id, hierarchy):
        """Print EXPLAIN ANALYZE for the CTE query (diagnostic, always passes)."""
        print("\n  EXPLAIN ANALYZE for full hierarchy CTE:")
        _run_recursive_cte(db_conn, test_tenant_id, hierarchy["project_id"], explain=True)