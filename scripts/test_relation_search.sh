#!/bin/bash
# Test script for P2: Relation-Aware Search Filters

API_BASE="http://localhost:38000"
TENANT_ID="1"

echo "=== Testing P2: Relation-Aware Search Filters ==="
echo ""

# Generate UUIDs for test artifacts
UUID1="01926a5c-0001-7000-8000-000000000001"
UUID2="01926a5c-0002-7000-8000-000000000002"
UUID3="01926a5c-0003-7000-8000-000000000003"
UUID4="01926a5c-0004-7000-8000-000000000004"

echo "Step 1: Create test artifacts..."
echo ""

# Create document artifact (anchor)
echo "Creating anchor document: $UUID1"
curl -s -X POST "$API_BASE/artifacts" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -d '{
    "id": "'$UUID1'",
    "artifact_type": "document",
    "title": "PostgreSQL Performance Guide",
    "content": "This guide covers PostgreSQL optimization techniques for large databases."
  }' | jq -r '.id // .detail'

# Create related decision
echo "Creating related decision: $UUID2"
curl -s -X POST "$API_BASE/artifacts" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -d '{
    "id": "'$UUID2'",
    "artifact_type": "decision",
    "title": "Use PostgreSQL for data storage",
    "content": "Decision to use PostgreSQL because of vector search support and performance."
  }' | jq -r '.id // .detail'

# Create related note
echo "Creating related note: $UUID3"
curl -s -X POST "$API_BASE/artifacts" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -d '{
    "id": "'$UUID3'",
    "artifact_type": "note",
    "title": "PostgreSQL Setup Notes",
    "content": "Notes on PostgreSQL configuration and tuning parameters."
  }' | jq -r '.id // .detail'

# Create unrelated artifact (should NOT appear in filtered results)
echo "Creating unrelated document: $UUID4"
curl -s -X POST "$API_BASE/artifacts" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -d '{
    "id": "'$UUID4'",
    "artifact_type": "document",
    "title": "Python Best Practices",
    "content": "Python coding standards and best practices for PostgreSQL applications."
  }' | jq -r '.id // .detail'

echo ""
echo "Step 2: Create relations..."
echo ""

# Create relation: decision derives_from document
echo "Creating relation: decision derives_from document"
curl -s -X POST "$API_BASE/relations" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -d '{
    "source_id": "'$UUID2'",
    "target_id": "'$UUID1'",
    "relation_type": "derived_from"
  }' | jq -r '.id // .detail'

# Create relation: note references document
echo "Creating relation: note references document"
curl -s -X POST "$API_BASE/relations" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -d '{
    "source_id": "'$UUID3'",
    "target_id": "'$UUID1'",
    "relation_type": "references"
  }' | jq -r '.id // .detail'

echo ""
echo "Step 3: Test fulltext search WITHOUT relation filter..."
echo ""

echo "Search for 'PostgreSQL' (should return all 4 artifacts):"
curl -s -X GET "$API_BASE/search/fulltext?query=PostgreSQL" \
  -H "X-Tenant-ID: $TENANT_ID" | jq '{total: .total, results: [.results[] | {id: .artifact.id, title: .artifact.title, type: .artifact.artifact_type}]}'

echo ""
echo "Step 4: Test fulltext search WITH relation filter..."
echo ""

echo "Search for 'PostgreSQL' related_to=$UUID1 (should return only UUID2 and UUID3):"
curl -s -X GET "$API_BASE/search/fulltext?query=PostgreSQL&related_to=$UUID1" \
  -H "X-Tenant-ID: $TENANT_ID" | jq '{total: .total, results: [.results[] | {id: .artifact.id, title: .artifact.title, type: .artifact.artifact_type}]}'

echo ""
echo "Step 5: Test relation filter with direction..."
echo ""

echo "Search with direction=incoming (anchor is target - others point to it):"
curl -s -X GET "$API_BASE/search/fulltext?query=PostgreSQL&related_to=$UUID1&relation_direction=incoming" \
  -H "X-Tenant-ID: $TENANT_ID" | jq '{total: .total, results: [.results[] | {id: .artifact.id, title: .artifact.title}]}'

echo ""
echo "Step 6: Test relation filter with relation_type..."
echo ""

echo "Search with relation_type=derived_from (should return only UUID2):"
curl -s -X GET "$API_BASE/search/fulltext?query=PostgreSQL&related_to=$UUID1&relation_type=derived_from" \
  -H "X-Tenant-ID: $TENANT_ID" | jq '{total: .total, results: [.results[] | {id: .artifact.id, title: .artifact.title}]}'

echo ""
echo "=== P2 Testing Complete ==="