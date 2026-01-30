#!/usr/bin/env python3
"""
Simple test script for the echo server.

Sends "Hello, World!" and prints the response for both
non-streaming and streaming modes.

Usage:
    1. Start the server: cd echo-server && poetry run uvicorn src.server:app --port 8000
    2. Run this test: cd echo-server && poetry run python test_hello.py
"""

import asyncio
import httpx


async def test_non_streaming():
    """Test non-streaming JSON response."""
    print("=" * 60)
    print("TEST: Non-streaming (application/json)")
    print("=" * 60)
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/v1/chat",
            json={
                "message": {
                    "role": "user",
                    "content": "Hello, World!"
                }
            },
            headers={"Accept": "application/json"},
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response:\n{response.json()}")
    print()


async def test_streaming_ndjson():
    """Test streaming NDJSON response."""
    print("=" * 60)
    print("TEST: Streaming (application/x-ndjson)")
    print("=" * 60)
    
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            "http://localhost:8000/v1/chat",
            json={
                "message": {
                    "role": "user",
                    "content": "Hello, World!"
                }
            },
            headers={"Accept": "application/x-ndjson"},
        ) as response:
            print(f"Status: {response.status_code}")
            print("Events:")
            
            # Collect content from deltas
            content = ""
            async for line in response.aiter_lines():
                if line.strip():
                    import json
                    event = json.loads(line)
                    print(f"  {event}")
                    
                    # Accumulate delta content
                    if event.get("type") == "message.delta":
                        content += event.get("delta", "")
            
            print(f"\nAssembled content: {content!r}")
    print()


async def test_health():
    """Test health check endpoint."""
    print("=" * 60)
    print("TEST: Health check")
    print("=" * 60)
    
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/health")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
    print()


async def main():
    print("\n🚀 Echo Server Test\n")
    
    try:
        await test_health()
        await test_non_streaming()
        await test_streaming_ndjson()
        print("✅ All tests passed!")
    except httpx.ConnectError:
        print("❌ Could not connect to server.")
        print("   Make sure the server is running:")
        print("   cd echo-server && poetry run uvicorn src.server:app --port 8000")


if __name__ == "__main__":
    asyncio.run(main())