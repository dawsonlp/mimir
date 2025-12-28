#!/usr/bin/env python3
"""
Ingest a file into Mímir's ontology via the API.

Usage:
    python scripts/ingest_file.py <file_path> [--title "Document Title"]
    
Examples:
    python scripts/ingest_file.py readme.md
    python scripts/ingest_file.py design_decisions.md --title "Design Decisions"
    python scripts/ingest_file.py notes.txt --type note --source "manual"
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

# Configuration
API_BASE_URL = "http://localhost:38000/api/v1"
DEFAULT_TENANT_ID = 1


def ensure_tenant(client: httpx.Client, tenant_id: int = DEFAULT_TENANT_ID) -> dict:
    """Ensure a tenant exists, create if not."""
    # Try to get existing tenant
    response = client.get(f"{API_BASE_URL}/tenants/{tenant_id}")
    if response.status_code == 200:
        return response.json()
    
    # Create tenant if not found
    if response.status_code == 404:
        response = client.post(
            f"{API_BASE_URL}/tenants",
            json={"name": "Default Tenant", "metadata": {"created_by": "ingest_file.py"}}
        )
        response.raise_for_status()
        return response.json()
    
    response.raise_for_status()
    return {}


def create_artifact(
    client: httpx.Client,
    tenant_id: int,
    content: str,
    title: str,
    artifact_type: str = "document",
    source: str = "file",
    metadata: dict | None = None,
) -> dict:
    """Create an artifact with content."""
    payload = {
        "artifact_type": artifact_type,
        "source": source,
        "title": title,
        "content": content,
        "metadata": metadata or {},
    }
    
    response = client.post(
        f"{API_BASE_URL}/artifacts",
        json=payload,
        headers={"X-Tenant-ID": str(tenant_id)},
    )
    response.raise_for_status()
    return response.json()


def create_embedding(
    client: httpx.Client,
    tenant_id: int,
    artifact_id: int,
    model: str = "openai-text-embedding-3-small",
) -> dict | None:
    """Create an embedding for an artifact (requires OPENAI_API_KEY)."""
    payload = {
        "artifact_id": artifact_id,
        "model": model,
    }
    
    try:
        response = client.post(
            f"{API_BASE_URL}/embeddings",
            json=payload,
            headers={"X-Tenant-ID": str(tenant_id)},
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        if "OPENAI_API_KEY" in str(e.response.text):
            print("  ⚠ Skipping embedding: OPENAI_API_KEY not configured")
            return None
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Ingest a file into Mímir's ontology",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/ingest_file.py readme.md
    python scripts/ingest_file.py design_decisions.md --title "Design Decisions"
    python scripts/ingest_file.py notes.txt --type note --source "manual"
    python scripts/ingest_file.py doc.md --embed  # Also create embeddings
        """,
    )
    parser.add_argument("file", type=Path, help="Path to file to ingest")
    parser.add_argument("--title", "-t", help="Document title (default: filename)")
    parser.add_argument(
        "--type",
        choices=["conversation", "document", "note"],
        default="document",
        help="Artifact type (default: document)",
    )
    parser.add_argument("--source", "-s", default="file", help="Source identifier")
    parser.add_argument("--tenant-id", type=int, default=DEFAULT_TENANT_ID, help="Tenant ID")
    parser.add_argument("--embed", "-e", action="store_true", help="Create embedding (requires OPENAI_API_KEY)")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    # Validate file exists
    if not args.file.exists():
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)
    
    # Read file content
    content = args.file.read_text(encoding="utf-8")
    title = args.title or args.file.name
    
    # Metadata
    metadata = {
        "filename": args.file.name,
        "path": str(args.file.absolute()),
        "size_bytes": args.file.stat().st_size,
        "ingested_by": "ingest_file.py",
    }
    
    # API calls
    with httpx.Client(timeout=30.0) as client:
        # Ensure tenant exists
        if not args.json:
            print(f"📁 Ingesting: {args.file}")
            print(f"   Title: {title}")
            print(f"   Type: {args.type}")
            print(f"   Size: {len(content)} chars")
        
        tenant = ensure_tenant(client, args.tenant_id)
        tenant_id = tenant.get("id", args.tenant_id)
        
        if not args.json:
            print(f"   Tenant: {tenant_id}")
        
        # Create artifact
        artifact = create_artifact(
            client,
            tenant_id=tenant_id,
            content=content,
            title=title,
            artifact_type=args.type,
            source=args.source,
            metadata=metadata,
        )
        
        if not args.json:
            print(f"✓ Created artifact: ID={artifact['id']}")
        
        # Optionally create embedding
        embedding = None
        if args.embed:
            if not args.json:
                print("  Creating embedding...")
            embedding = create_embedding(client, tenant_id, artifact["id"])
            if embedding and not args.json:
                print(f"  ✓ Created embedding: ID={embedding['id']}, dimensions={embedding['dimensions']}")
        
        # Output
        if args.json:
            result = {
                "artifact": artifact,
                "embedding": embedding,
            }
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"\n🎉 Successfully ingested '{title}' as artifact #{artifact['id']}")
            print(f"   View at: http://localhost:38000/api/v1/artifacts/{artifact['id']}")


if __name__ == "__main__":
    main()
