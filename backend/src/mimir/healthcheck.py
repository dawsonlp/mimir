#!/usr/bin/env python3
"""Container healthcheck - uses only stdlib, no external dependencies.

Run as: python -m mimir.healthcheck
Returns exit code 0 if healthy, 1 if unhealthy.
"""
import json
import sys
import urllib.request


def main() -> int:
    """Check API health endpoint and return appropriate exit code."""
    try:
        with urllib.request.urlopen("http://localhost:8000/health", timeout=5) as resp:
            data = json.loads(resp.read())
            if data.get("status") == "healthy":
                return 0
    except Exception:
        pass
    return 1


if __name__ == "__main__":
    sys.exit(main())