#!/bin/bash
# Test Context Retrieval Service
# Run: bash scripts/test_context.sh

set -e

BASE_URL="http://localhost:38000"
TENANT_ID=1

echo "=== Context Retrieval Service Test ==="
echo "Base URL: $BASE_URL"
echo ""

# Generate UUIDs using Python (portable)
DOC_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
SUMMARY_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
DECISION_ID=$(python3 -c "import uuid; print(uuid.uuid4())")

echo "Generated UUIDs:"
echo "  Document: $DOC_ID"
echo "  Summary:  $SUMMARY_ID"
echo "  Decision: $DECISION_ID"
echo ""

# Create primary artifact (a document)
echo "=== Creating primary artifact (document) ==="
curl -s -X POST "$BASE_URL/artifacts" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -d "{
    \"id\": \"$DOC_ID\",
    \"artifact_type\": \"document\",
    \"title\": \"Architecture Decision Record\",
    \"content\": \"This document describes the decision to use PostgreSQL for the knowledge graph.\"
  }" | jq '.id'

# Create derived artifact (a summary)
echo ""
echo "=== Creating derived artifact (summary) ==="
curl -s -X POST "$BASE_URL/artifacts" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -d "{
    \"id\": \"$SUMMARY_ID\",
    \"artifact_type\": \"summary\",
    \"title\": \"ADR Summary\",
    \"content\": \"Summary: PostgreSQL chosen for graph storage.\"
  }" | jq '.id'

# Create another derived artifact (a decision)
echo ""
echo "=== Creating another derived artifact (decision) ==="
curl -s -X POST "$BASE_URL/artifacts" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -d "{
    \"id\": \"$DECISION_ID\",
    \"artifact_type\": \"decision\",
    \"title\": \"Use PostgreSQL\",
    \"content\": \"Decision: Use PostgreSQL with pgvector for semantic storage.\"
  }" | jq '.id'

# Create relations: summary derived_from document
echo ""
echo "=== Creating relation: summary derived_from document ==="
curl -s -X POST "$BASE_URL/relations" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -d "{
    \"source_id\": \"$SUMMARY_ID\",
    \"target_id\": \"$DOC_ID\",
    \"relation_type\": \"derived_from\",
    \"confidence\": 1.0
  }" | jq '.id'

# Create relations: decision derived_from document
echo ""
echo "=== Creating relation: decision derived_from document ==="
curl -s -X POST "$BASE_URL/relations" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -d "{
    \"source_id\": \"$DECISION_ID\",
    \"target_id\": \"$DOC_ID\",
    \"relation_type\": \"derived_from\",
    \"confidence\": 1.0
  }" | jq '.id'

echo ""
echo "=========================================="
echo "=== TESTING CONTEXT RETRIEVAL SERVICE ==="
echo "=========================================="

# Test 1: Context retrieval with derived_lineage policy
echo ""
echo "=== TEST 1: derived_lineage policy on document ==="
echo "Expected: Should find summary and decision (both derived from doc)"
curl -s -X POST "$BASE_URL/context/$DOC_ID?policy=derived_lineage&depth=2" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" | jq '{
    primary_title: .artifact.title,
    policy: .policy,
    context_count: (.context | length),
    context_titles: [.context[].artifact.title],
    metadata: .metadata
  }'

# Test 2: Context from summary (follow incoming derived_from back to doc)
echo ""
echo "=== TEST 2: derived_lineage from summary ==="
echo "Expected: Should find document (summary derived_from doc)"
curl -s -X POST "$BASE_URL/context/$SUMMARY_ID?policy=derived_lineage&depth=1" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" | jq '{
    primary_title: .artifact.title,
    context_count: (.context | length),
    context_artifacts: [.context[] | {title: .artifact.title, distance: .distance, reason: .inclusion_reason}]
  }'

# Test 3: direct_relations policy (should get all related artifacts)
echo ""
echo "=== TEST 3: direct_relations policy ==="
echo "Expected: Should find all directly related artifacts"
curl -s -X POST "$BASE_URL/context/$DOC_ID?policy=direct_relations" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" | jq '{
    policy: .policy,
    context_count: (.context | length),
    context_artifacts: [.context[] | {title: .artifact.title, type: .artifact.artifact_type, reason: .inclusion_reason}]
  }'

# Test 4: Type filter
echo ""
echo "=== TEST 4: Filter to only 'summary' types ==="
curl -s -X POST "$BASE_URL/context/$DOC_ID?policy=direct_relations&types=summary" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" | jq '{
    context_count: (.context | length),
    context_types: [.context[].artifact.artifact_type]
  }'

# Test 5: include_content=false
echo ""
echo "=== TEST 5: Without content ==="
curl -s -X POST "$BASE_URL/context/$DOC_ID?policy=direct_relations&include_content=false" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" | jq '{
    primary_has_content: (.artifact.content != null),
    context_has_content: ([.context[].artifact.content] | any(. != null))
  }'

# Test 6: 404 for non-existent artifact
echo ""
echo "=== TEST 6: Non-existent artifact returns 404 ==="
curl -s -X POST "$BASE_URL/context/00000000-0000-0000-0000-000000000000?policy=direct_relations" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" | jq '.'

# Test 7: full_graph policy with depth 2
echo ""
echo "=== TEST 7: full_graph policy with depth 2 ==="
curl -s -X POST "$BASE_URL/context/$DOC_ID?policy=full_graph&depth=2" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" | jq '{
    policy: .policy,
    depth_used: .metadata.depth_used,
    context_count: (.context | length)
  }'

echo ""
echo "=== All tests complete ==="