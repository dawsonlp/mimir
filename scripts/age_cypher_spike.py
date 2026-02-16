#!/usr/bin/env python3
"""AGE Cypher Spike — Validate Cypher patterns against AGE 1.7.0.

Runs against the local PostgreSQL+AGE instance to determine which Cypher
features are available for the Graph Traversal Engine.

Required: Running PostgreSQL with AGE extension on localhost:35432.
Usage:
    cd backend && docker compose up -d postgres
    cd .. && python scripts/age_cypher_spike.py

See: docs/graph-engine-technical-design.md §5.1
See: docs/graph-engine-agreed-approach.md (D3 — path data requirement)
"""

import asyncio
import json
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import psycopg


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://mimir:{password}@localhost:35432/mimir",
)


def _resolve_database_url():
    """Resolve the database URL, loading password from env or dotfiles."""
    url = DATABASE_URL
    if "{password}" in url:
        password = os.environ.get("POSTGRES_PASSWORD", "")
        if not password:
            for env_path in [Path.home() / ".env", Path("backend/.env")]:
                if env_path.exists():
                    for line in env_path.read_text().splitlines():
                        line = line.strip()
                        if line.startswith("POSTGRES_PASSWORD="):
                            password = line.split("=", 1)[1].strip().strip("'\"")
                            break
                if password:
                    break
        if not password:
            print("ERROR: POSTGRES_PASSWORD not found. Set it or add to ~/.env")
            sys.exit(1)
        url = url.replace("{password}", password)
    return url


GRAPH_NAME = "mimir_tenant_99999"


# ---------------------------------------------------------------------------
# Test data — known graph topology
# ---------------------------------------------------------------------------
# A → B → C → D       (chain, depth 3, relation_type=derived_from)
# A → E                (branch from A, relation_type=supports)
# C → F → G            (branch from C, relation_type=parent_of)
# H → A                (incoming to A, relation_type=derived_from)
# X (disconnected)

ARTIFACT_IDS = {
    "A": str(uuid4()),
    "B": str(uuid4()),
    "C": str(uuid4()),
    "D": str(uuid4()),
    "E": str(uuid4()),
    "F": str(uuid4()),
    "G": str(uuid4()),
    "H": str(uuid4()),
    "X": str(uuid4()),
}

RELATIONS = [
    ("A", "B", "derived_from", str(uuid4())),
    ("B", "C", "derived_from", str(uuid4())),
    ("C", "D", "derived_from", str(uuid4())),
    ("A", "E", "supports", str(uuid4())),
    ("C", "F", "parent_of", str(uuid4())),
    ("F", "G", "parent_of", str(uuid4())),
    ("H", "A", "derived_from", str(uuid4())),
]


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    name: str
    passed: bool
    output: str = ""
    error: str = ""
    notes: str = ""


results: list[TestResult] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def cypher_escape(value: str) -> str:
    """Escape a string for embedding in Cypher (matches migration 007)."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


async def execute_cypher(conn, cypher_text: str, result_columns: str):
    """Execute a Cypher query via ag_catalog.cypher() and return rows."""
    sql = (
        f"SELECT * FROM ag_catalog.cypher('{GRAPH_NAME}', "
        f"$$ {cypher_text} $$) AS {result_columns}"
    )
    cursor = await conn.execute(sql)
    return await cursor.fetchall()


def id_label(uid: str) -> str:
    """Look up the label (A, B, C...) for a given artifact UUID."""
    return next((lbl for lbl, u in ARTIFACT_IDS.items() if u == uid), "?")


# ---------------------------------------------------------------------------
# Setup / Teardown
# ---------------------------------------------------------------------------

async def setup_graph(conn):
    """Create test graph with known topology."""
    print("\n=== SETUP: Creating test graph ===")

    # Drop graph if it exists from a previous run
    try:
        await conn.execute(
            f"SELECT ag_catalog.drop_graph('{GRAPH_NAME}', true)"
        )
        await conn.commit()
        print(f"  Dropped existing graph '{GRAPH_NAME}'")
    except Exception:
        await conn.rollback()

    # Create graph
    await conn.execute(f"SELECT ag_catalog.create_graph('{GRAPH_NAME}')")
    await conn.commit()
    print(f"  Created graph '{GRAPH_NAME}'")

    # Create Artifact vertex label via placeholder (migration 007 pattern)
    await execute_cypher(
        conn,
        "CREATE (a:Artifact {mimir_id: '__ph__', artifact_type: 'ph', "
        "title: 'ph', created_at: '2026-01-01T00:00:00Z'}) RETURN a",
        "(v agtype)",
    )
    await conn.commit()
    await execute_cypher(
        conn,
        "MATCH (a:Artifact {mimir_id: '__ph__'}) DELETE a",
        "(v agtype)",
    )
    await conn.commit()

    # Create Relation edge label via placeholder
    await execute_cypher(
        conn,
        "CREATE (a:Artifact {mimir_id: '__ts__', artifact_type: 't', "
        "title: 't', created_at: '2026-01-01T00:00:00Z'}), "
        "(b:Artifact {mimir_id: '__tt__', artifact_type: 't', "
        "title: 't', created_at: '2026-01-01T00:00:00Z'}), "
        "(a)-[:Relation {mimir_id: '__tr__', relation_type: 't', "
        "confidence: 1.0, created_at: '2026-01-01T00:00:00Z'}]->(b) "
        "RETURN a",
        "(v agtype)",
    )
    await conn.commit()
    await execute_cypher(
        conn,
        "MATCH (a:Artifact {mimir_id: '__ts__'})-[r:Relation]-"
        "(b:Artifact {mimir_id: '__tt__'}) DELETE r, a, b",
        "(v agtype)",
    )
    await conn.commit()
    print("  Created Artifact and Relation labels")

    # Insert vertices
    for label, uid in ARTIFACT_IDS.items():
        eid = cypher_escape(uid)
        await execute_cypher(
            conn,
            f"CREATE (a:Artifact {{mimir_id: '{eid}', "
            f"artifact_type: 'document', title: 'Test Artifact {label}', "
            f"created_at: '2026-01-01T00:00:00Z'}}) RETURN a",
            "(v agtype)",
        )
    await conn.commit()
    print(f"  Inserted {len(ARTIFACT_IDS)} vertices")

    # Insert edges
    for src, tgt, rel_type, rel_id in RELATIONS:
        sid = cypher_escape(ARTIFACT_IDS[src])
        tid = cypher_escape(ARTIFACT_IDS[tgt])
        rid = cypher_escape(rel_id)
        rt = cypher_escape(rel_type)
        await execute_cypher(
            conn,
            f"MATCH (a:Artifact {{mimir_id: '{sid}'}}), "
            f"(b:Artifact {{mimir_id: '{tid}'}}) "
            f"CREATE (a)-[:Relation {{mimir_id: '{rid}', "
            f"relation_type: '{rt}', confidence: 1.0, "
            f"created_at: '2026-01-01T00:00:00Z'}}]->(b) RETURN a",
            "(v agtype)",
        )
    await conn.commit()
    print(f"  Inserted {len(RELATIONS)} edges")
    print("  Setup complete.\n")


async def teardown_graph(conn):
    """Drop the test graph."""
    print("\n=== TEARDOWN ===")
    try:
        await conn.execute(
            f"SELECT ag_catalog.drop_graph('{GRAPH_NAME}', true)"
        )
        await conn.commit()
        print(f"  Dropped graph '{GRAPH_NAME}'")
    except Exception as e:
        await conn.rollback()
        print(f"  Warning: Could not drop graph: {e}")


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

async def test_1_vlp_outgoing(conn):
    """Test 1 — Variable-length path (outgoing)."""
    name = "Test 1: Variable-length path (outgoing)"
    sid = cypher_escape(ARTIFACT_IDS["A"])
    try:
        rows = await execute_cypher(
            conn,
            f"MATCH (s:Artifact)-[:Relation*1..3]->(r:Artifact) "
            f"WHERE s.mimir_id = '{sid}' "
            f"RETURN DISTINCT r.mimir_id",
            "(mimir_id agtype)",
        )
        await conn.commit()

        cleaned = {str(r[0]).strip('"') for r in rows}
        # A→B(1), B→C(2), C→D(3), A→E(1), C→F(3). G is 4 hops—excluded.
        expected = {ARTIFACT_IDS[x] for x in ("B", "C", "D", "E", "F")}
        missing = expected - cleaned
        extra = cleaned - expected

        output = f"Returned {len(rows)} rows. Cleaned IDs: {[id_label(x) for x in cleaned]}"
        notes = ""
        if missing:
            notes += f"Missing: {[id_label(x) for x in missing]}. "
        if extra:
            notes += f"Extra: {[id_label(x) for x in extra]}. "

        results.append(TestResult(name, not missing and not extra, output,
                                  notes=notes or "All expected IDs found"))
    except Exception as e:
        await conn.rollback()
        results.append(TestResult(name, False, error=traceback.format_exc()))


async def test_2_vlp_undirected(conn):
    """Test 2 — Variable-length path (undirected / both)."""
    name = "Test 2: Variable-length path (undirected/both)"
    sid = cypher_escape(ARTIFACT_IDS["A"])
    try:
        rows = await execute_cypher(
            conn,
            f"MATCH (s:Artifact)-[:Relation*1..3]-(r:Artifact) "
            f"WHERE s.mimir_id = '{sid}' "
            f"RETURN DISTINCT r.mimir_id",
            "(mimir_id agtype)",
        )
        await conn.commit()

        cleaned = {str(r[0]).strip('"') for r in rows}
        # Adds H(1 incoming) to the outgoing set
        expected = {ARTIFACT_IDS[x] for x in ("B", "C", "D", "E", "F", "H")}
        missing = expected - cleaned
        extra = cleaned - expected

        output = f"Returned {len(rows)} rows. Cleaned IDs: {[id_label(x) for x in cleaned]}"
        notes = ""
        if missing:
            notes += f"Missing: {[id_label(x) for x in missing]}. "
        if extra:
            notes += f"Extra: {[id_label(x) for x in extra]}. "

        results.append(TestResult(name, not missing, output,
                                  notes=notes or "All expected IDs found"))
    except Exception as e:
        await conn.rollback()
        results.append(TestResult(name, False, error=traceback.format_exc()))


async def test_3_relation_type_filtering(conn):
    """Test 3 — Relation type filtering in variable-length paths.

    Sub-tests:
      3A: path variable + length()
      3B: ALL() predicate on relationships(path)
      3C: relationships() function return
      3D: nodes() function return
    """
    name = "Test 3: Relation type filtering in VLP"
    sid = cypher_escape(ARTIFACT_IDS["A"])
    sections = {}

    # 3A: path variable + length
    try:
        rows = await execute_cypher(
            conn,
            f"MATCH path = (s:Artifact)-[r:Relation*1..3]->(t:Artifact) "
            f"WHERE s.mimir_id = '{sid}' "
            f"RETURN t.mimir_id, length(path)",
            "(mimir_id agtype, depth agtype)",
        )
        await conn.commit()
        out = f"3A: Returned {len(rows)} rows.\n"
        for r in rows:
            out += f"  {id_label(str(r[0]).strip(chr(34)))} depth={r[1]}\n"
        sections["3A"] = (True, out)
    except Exception as e:
        await conn.rollback()
        sections["3A"] = (False, f"3A FAILED: {e}\n")

    # 3B: ALL() predicate
    try:
        rows = await execute_cypher(
            conn,
            f"MATCH path = (s:Artifact)-[r:Relation*1..3]->(t:Artifact) "
            f"WHERE s.mimir_id = '{sid}' "
            f"AND ALL(rel IN relationships(path) WHERE rel.relation_type = 'derived_from') "
            f"RETURN DISTINCT t.mimir_id, length(path)",
            "(mimir_id agtype, depth agtype)",
        )
        await conn.commit()
        unique = {str(r[0]).strip('"') for r in rows}
        expected = {ARTIFACT_IDS[x] for x in ("B", "C", "D")}
        ok = expected.issubset(unique) and not (unique - expected)
        out = f"3B: Returned {len(rows)} rows. IDs: {[id_label(x) for x in unique]}. Correct: {ok}\n"
        sections["3B"] = (ok, out)
    except Exception as e:
        await conn.rollback()
        sections["3B"] = (False, f"3B FAILED: {e}\n")

    # 3C: relationships() function
    try:
        rows = await execute_cypher(
            conn,
            f"MATCH path = (s:Artifact)-[:Relation*1..3]->(t:Artifact) "
            f"WHERE s.mimir_id = '{sid}' "
            f"RETURN t.mimir_id, length(path), relationships(path)",
            "(mimir_id agtype, depth agtype, rels agtype)",
        )
        await conn.commit()
        out = f"3C: Returned {len(rows)} rows.\n"
        if rows:
            out += f"  First rels type: {type(rows[0][2]).__name__}\n"
            out += f"  First rels value: {repr(rows[0][2])[:300]}\n"
        sections["3C"] = (True, out)
    except Exception as e:
        await conn.rollback()
        sections["3C"] = (False, f"3C FAILED: {e}\n")

    # 3D: nodes() function
    try:
        rows = await execute_cypher(
            conn,
            f"MATCH path = (s:Artifact)-[:Relation*1..3]->(t:Artifact) "
            f"WHERE s.mimir_id = '{sid}' "
            f"RETURN t.mimir_id, length(path), nodes(path)",
            "(mimir_id agtype, depth agtype, nds agtype)",
        )
        await conn.commit()
        out = f"3D: Returned {len(rows)} rows.\n"
        if rows:
            out += f"  First nodes type: {type(rows[0][2]).__name__}\n"
            out += f"  First nodes value: {repr(rows[0][2])[:300]}\n"
        sections["3D"] = (True, out)
    except Exception as e:
        await conn.rollback()
        sections["3D"] = (False, f"3D FAILED: {e}\n")

    output = "".join(v[1] for v in sections.values())
    statuses = {k: v[0] for k, v in sections.items()}
    passed = statuses.get("3A", False)  # Minimum: path variable works
    notes = ", ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in statuses.items())

    results.append(TestResult(name, passed, output, notes=notes))


async def test_4_shortest_path(conn):
    """Test 4 — shortestPath()."""
    name = "Test 4: shortestPath()"
    a_id = cypher_escape(ARTIFACT_IDS["A"])
    d_id = cypher_escape(ARTIFACT_IDS["D"])
    try:
        rows = await execute_cypher(
            conn,
            f"MATCH p = shortestPath((a:Artifact)-[:Relation*..5]-(b:Artifact)) "
            f"WHERE a.mimir_id = '{a_id}' AND b.mimir_id = '{d_id}' "
            f"RETURN p",
            "(path agtype)",
        )
        await conn.commit()

        output = f"Returned {len(rows)} rows.\n"
        if rows:
            output += f"  Path type: {type(rows[0][0]).__name__}\n"
            output += f"  Path value: {repr(rows[0][0])[:400]}\n"

        results.append(TestResult(name, len(rows) > 0, output,
                                  notes="shortestPath() supported"))
    except Exception as e:
        await conn.rollback()
        results.append(TestResult(name, False, error=str(e),
                                  notes="shortestPath() NOT supported — fallback needed"))


async def test_5_length_function(conn):
    """Test 5 — length() function on paths."""
    name = "Test 5: length() function"
    sid = cypher_escape(ARTIFACT_IDS["A"])
    try:
        rows = await execute_cypher(
            conn,
            f"MATCH path = (s:Artifact)-[:Relation*1..5]->(t:Artifact) "
            f"WHERE s.mimir_id = '{sid}' "
            f"RETURN t.mimir_id, length(path) AS depth",
            "(mimir_id agtype, depth agtype)",
        )
        await conn.commit()

        # Build shortest-depth map
        depth_map = {}
        for r in rows:
            uid = str(r[0]).strip('"')
            try:
                d = int(str(r[1]))
            except ValueError:
                d = str(r[1])
            lbl = id_label(uid)
            if lbl not in depth_map or (isinstance(d, int) and d < depth_map[lbl]):
                depth_map[lbl] = d

        output = f"Returned {len(rows)} rows.\nDepth map: {depth_map}\n"
        expected = {"B": 1, "C": 2, "D": 3, "E": 1, "F": 3, "G": 4}
        correct = all(depth_map.get(k) == v for k, v in expected.items() if k in depth_map)
        output += f"Expected depths correct: {correct}\n"

        results.append(TestResult(name, True, output,
                                  notes=f"length() works. Depths correct: {correct}"))
    except Exception as e:
        await conn.rollback()
        results.append(TestResult(name, False, error=traceback.format_exc()))


async def test_6_limit(conn):
    """Test 6 — LIMIT clause."""
    name = "Test 6: LIMIT clause"
    sid = cypher_escape(ARTIFACT_IDS["A"])
    try:
        rows = await execute_cypher(
            conn,
            f"MATCH (s:Artifact)-[:Relation*1..10]->(t:Artifact) "
            f"WHERE s.mimir_id = '{sid}' "
            f"RETURN DISTINCT t.mimir_id LIMIT 3",
            "(mimir_id agtype)",
        )
        await conn.commit()

        output = f"Returned {len(rows)} rows (LIMIT 3).\n"
        passed = len(rows) <= 3
        results.append(TestResult(name, passed, output,
                                  notes=f"LIMIT respected: {passed}"))
    except Exception as e:
        await conn.rollback()
        results.append(TestResult(name, False, error=traceback.format_exc()))


async def test_7_agtype_parsing(conn):
    """Test 7 — agtype parsing: how values are returned to psycopg v3."""
    name = "Test 7: agtype parsing"
    a_id = cypher_escape(ARTIFACT_IDS["A"])
    b_id = cypher_escape(ARTIFACT_IDS["B"])
    output = ""

    try:
        # Property returns
        rows = await execute_cypher(
            conn,
            f"MATCH (a:Artifact {{mimir_id: '{a_id}'}}) "
            f"RETURN a.mimir_id, a.title, a.artifact_type, a",
            "(mid agtype, title agtype, atype agtype, vertex agtype)",
        )
        await conn.commit()
        output += "=== Property returns ===\n"
        if rows:
            for i, col in enumerate(["mimir_id", "title", "artifact_type", "vertex"]):
                v = rows[0][i]
                output += f"  {col}: type={type(v).__name__}, repr={repr(v)[:200]}\n"

        # Edge returns
        rows = await execute_cypher(
            conn,
            f"MATCH (a:Artifact {{mimir_id: '{a_id}'}})-[r:Relation]->"
            f"(b:Artifact {{mimir_id: '{b_id}'}}) "
            f"RETURN r, r.relation_type, r.mimir_id",
            "(edge agtype, rtype agtype, rid agtype)",
        )
        await conn.commit()
        output += "\n=== Edge returns ===\n"
        if rows:
            for i, col in enumerate(["edge", "relation_type", "mimir_id"]):
                v = rows[0][i]
                output += f"  {col}: type={type(v).__name__}, repr={repr(v)[:200]}\n"

        # Single-hop path return
        rows = await execute_cypher(
            conn,
            f"MATCH path = (a:Artifact {{mimir_id: '{a_id}'}})-[:Relation]->"
            f"(b:Artifact {{mimir_id: '{b_id}'}}) RETURN path",
            "(p agtype)",
        )
        await conn.commit()
        output += "\n=== Path return (single hop) ===\n"
        if rows:
            v = rows[0][0]
            output += f"  type={type(v).__name__}\n"
            output += f"  repr={repr(v)[:500]}\n"
            output += f"  str={str(v)[:500]}\n"

        # Scalar returns
        rows = await execute_cypher(
            conn,
            f"MATCH path = (a:Artifact {{mimir_id: '{a_id}'}})-[:Relation]->"
            f"(b:Artifact) RETURN length(path), 42, 3.14, true",
            "(len agtype, ival agtype, fval agtype, bval agtype)",
        )
        await conn.commit()
        output += "\n=== Scalar returns ===\n"
        if rows:
            for i, col in enumerate(["length(path)", "int(42)", "float(3.14)", "bool(true)"]):
                v = rows[0][i]
                output += f"  {col}: type={type(v).__name__}, repr={repr(v)}\n"

        results.append(TestResult(name, True, output,
                                  notes="See output for agtype parsing details"))
    except Exception as e:
        await conn.rollback()
        results.append(TestResult(name, False, output, error=traceback.format_exc()))


async def test_8_path_data_extraction(conn):
    """Test 8 (D3 critical) — Extract full path data from VLP results.

    The agreed approach requires traverse() to return complete relation_path
    data (the sequence of relations and intermediate artifacts).
    """
    name = "Test 8: Path data extraction (D3 critical)"
    sid = cypher_escape(ARTIFACT_IDS["A"])
    output = ""

    try:
        # Return full paths from A
        rows = await execute_cypher(
            conn,
            f"MATCH path = (s:Artifact)-[:Relation*1..3]->(t:Artifact) "
            f"WHERE s.mimir_id = '{sid}' "
            f"RETURN path, t.mimir_id, length(path)",
            "(p agtype, target_id agtype, depth agtype)",
        )
        await conn.commit()

        output += f"Returned {len(rows)} path rows.\n\n"

        for i, row in enumerate(rows[:6]):
            path_val = row[0]
            target = str(row[1]).strip('"')
            depth = row[2]
            tlbl = id_label(target)
            output += f"--- Path {i+1} → {tlbl} (depth {depth}) ---\n"
            output += f"  python type: {type(path_val).__name__}\n"

            path_str = str(path_val)
            output += f"  str (first 400 chars): {path_str[:400]}\n"

            # Attempt JSON parse
            try:
                parsed = json.loads(path_str)
                output += f"  JSON parse: SUCCESS, type={type(parsed).__name__}\n"
                if isinstance(parsed, list):
                    output += f"  list length: {len(parsed)}\n"
                    for j, elem in enumerate(parsed):
                        etype = "vertex" if isinstance(elem, dict) and "label" in elem else "edge" if isinstance(elem, dict) else type(elem).__name__
                        output += f"    [{j}] {etype}: {json.dumps(elem)[:200]}\n"
                elif isinstance(parsed, dict):
                    output += f"  dict keys: {list(parsed.keys())}\n"
            except (json.JSONDecodeError, TypeError):
                output += f"  JSON parse: FAILED (not valid JSON)\n"

            output += "\n"

        # Also test: can we extract nodes and edges separately from a VLP path?
        output += "=== Separate nodes/relationships extraction ===\n"
        try:
            rows2 = await execute_cypher(
                conn,
                f"MATCH path = (s:Artifact)-[:Relation*1..2]->(t:Artifact) "
                f"WHERE s.mimir_id = '{sid}' "
                f"RETURN nodes(path), relationships(path), t.mimir_id",
                "(nds agtype, rels agtype, tid agtype)",
            )
            await conn.commit()

            for i, row in enumerate(rows2[:3]):
                tlbl = id_label(str(row[2]).strip('"'))
                output += f"\n  Path to {tlbl}:\n"
                output += f"    nodes type: {type(row[0]).__name__}, val: {repr(row[0])[:300]}\n"
                output += f"    rels  type: {type(row[1]).__name__}, val: {repr(row[1])[:300]}\n"

                # Try parsing nodes
                try:
                    nodes_parsed = json.loads(str(row[0]))
                    output += f"    nodes JSON: {len(nodes_parsed)} elements\n"
                    for n in nodes_parsed:
                        if isinstance(n, dict):
                            mid = n.get("properties", {}).get("mimir_id", "?")
                            output += f"      vertex: {id_label(mid)} ({mid[:8]}...)\n"
                except (json.JSONDecodeError, TypeError):
                    output += f"    nodes JSON parse failed\n"

                # Try parsing relationships
                try:
                    rels_parsed = json.loads(str(row[1]))
                    output += f"    rels JSON: {len(rels_parsed)} elements\n"
                    for r in rels_parsed:
                        if isinstance(r, dict):
                            rt = r.get("properties", {}).get("relation_type", "?")
                            output += f"      edge: {rt}\n"
                except (json.JSONDecodeError, TypeError):
                    output += f"    rels JSON parse failed\n"

        except Exception as e2:
            output += f"  nodes/relationships extraction FAILED: {e2}\n"

        results.append(TestResult(name, True, output,
                                  notes="See output for path data structure details"))
    except Exception as e:
        await conn.rollback()
        results.append(TestResult(name, False, output, error=traceback.format_exc()))


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report():
    """Print a formatted report of all test results."""
    print("\n" + "=" * 70)
    print("AGE CYPHER SPIKE — RESULTS SUMMARY")
    print("=" * 70)

    passed_count = sum(1 for r in results if r.passed)
    total = len(results)

    for r in results:
        status = "✅ PASS" if r.passed else "❌ FAIL"
        print(f"\n{status}  {r.name}")
        if r.notes:
            print(f"  Notes: {r.notes}")
        if r.error:
            print(f"  Error: {r.error[:200]}")

    print(f"\n{'=' * 70}")
    print(f"Results: {passed_count}/{total} passed")
    print("=" * 70)


def write_results_markdown():
    """Write detailed results to docs/age-cypher-spike-results.md."""
    from datetime import datetime

    lines = [
        "# AGE Cypher Spike — Results",
        "",
        f"**Date**: {datetime.now().isoformat()[:19]}",
        "**AGE Version**: 1.7.0  ",
        "**PostgreSQL Image**: dawsonlp/postgres-batteries-inc:18  ",
        f"**Driver**: psycopg {psycopg.__version__}  ",
        "",
        "---",
        "",
    ]

    passed_count = sum(1 for r in results if r.passed)
    total = len(results)
    lines.append(f"## Summary: {passed_count}/{total} passed\n")

    for r in results:
        status = "✅ PASS" if r.passed else "❌ FAIL"
        lines.append(f"### {status} — {r.name}\n")
        if r.notes:
            lines.append(f"**Notes**: {r.notes}\n")
        if r.error:
            lines.append(f"**Error**:\n```\n{r.error}\n```\n")
        if r.output:
            lines.append(f"**Output**:\n```\n{r.output}\n```\n")
        lines.append("")

    lines.append("---\n")
    lines.append("## Decisions for Implementation\n")
    lines.append("*(To be filled in after reviewing results with architect)*\n")
    lines.append("")
    lines.append("| Pattern | Works? | Chosen Approach |")
    lines.append("|---------|--------|-----------------|")
    lines.append("| Variable-length path (outgoing) | | |")
    lines.append("| Variable-length path (undirected) | | |")
    lines.append("| Relation type filtering in VLP | | |")
    lines.append("| shortestPath() | | |")
    lines.append("| length() function | | |")
    lines.append("| LIMIT clause | | |")
    lines.append("| agtype parsing | | |")
    lines.append("| Path data extraction (D3) | | |")

    outpath = Path("docs/age-cypher-spike-results.md")
    outpath.write_text("\n".join(lines) + "\n")
    print(f"\nResults written to {outpath}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    """Run all spike tests."""
    url = _resolve_database_url()
    print(f"Connecting to: {url.split('@')[1] if '@' in url else url}")

    conn = await psycopg.AsyncConnection.connect(
        url, autocommit=False
    )

    try:
        # Load AGE and set search path (same as database.py configure callback)
        await conn.execute("LOAD 'age'")
        await conn.execute(
            "SET search_path = ag_catalog, mimirdata, public"
        )
        await conn.commit()
        print("AGE loaded, search_path set.")

        await setup_graph(conn)

        # Run all tests
        test_functions = [
            test_1_vlp_outgoing,
            test_2_vlp_undirected,
            test_3_relation_type_filtering,
            test_4_shortest_path,
            test_5_length_function,
            test_6_limit,
            test_7_agtype_parsing,
            test_8_path_data_extraction,
        ]

        for test_fn in test_functions:
            print(f"Running {test_fn.__doc__.strip().split(chr(10))[0]}...")
            await test_fn(conn)

        await teardown_graph(conn)

    finally:
        await conn.close()

    print_report()
    write_results_markdown()

    # Return exit code based on results
    failed = sum(1 for r in results if not r.passed)
    return failed


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
