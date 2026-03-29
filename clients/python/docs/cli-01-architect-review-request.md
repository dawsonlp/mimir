# CLI-01: Architect Review Request -- tenant_id String Shortname Migration

**From:** Chief Product Officer
**To:** Chief Architect
**Date:** 2026-03-29
**Priority:** High (blocking RADEMO1 technical design)
**Source:** RADEMO1 design review -- CLI-01 enhancement request

---

## Context

The RADEMO1 team has identified a valid abstraction leak in `mimir-client` v5.2.0.
The `MimirSyncClient` and `MimirClient` constructors expose `tenant_id: int` as
the primary tenant identifier. This integer is a database surrogate key. The Mimir
domain identifies tenants by string shortname, and all downstream consumers
(including the `ooda_framework` `MemoryProtocol`) use `tenant: str`.

Product has reviewed and accepted this as a high-priority bug fix. The backend API
requires no changes -- it already provides `GET /tenants/by-shortname/{shortname}`
for resolution, and the `X-Tenant-ID` header remains integer. This is purely a
client-library concern.

## Current State (v5.2.0)

```python
# Constructor
MimirSyncClient(api_url="...", tenant_id: int | None = None, timeout=30.0)

# Config
class MimirClientSettings(BaseSettings):
    tenant_id: int | None = None  # env: MIMIR_TENANT_ID

# Header injection
headers["X-Tenant-ID"] = str(tenant_id)  # sends integer as string

# ensure_tenant() resolves shortname -> sets self.tenant_id = tenant.id (int)
```

## Decisions Requested

Please review and confirm or revise the following interface design decisions:

### 1. Constructor Signature

**Proposed:** Replace `tenant_id: int | None` with `tenant: str | None` as the
primary parameter.

```python
class MimirSyncClient:
    def __init__(
        self,
        api_url: str = "http://localhost:38000",
        tenant: str | None = None,      # shortname (new primary)
        timeout: float = 30.0,
    ):
```

**Question:** Should we also accept `tenant_id: int | None` as a deprecated
backward-compatible parameter during a transition period? If both are provided,
which takes precedence?

### 2. Internal Resolution Strategy

The backend `X-Tenant-ID` header requires an integer. The client must resolve
shortname to integer internally.

**Option A -- Eager resolution:** Call `GET /tenants/by-shortname/{shortname}`
at construction time (or on first use). Cache the resolved integer for the
lifetime of the client.

**Option B -- Lazy resolution:** Defer resolution until the first tenant-scoped
request. Cache afterward.

**Option C -- Piggyback on ensure_tenant:** Require callers to call
`ensure_tenant()` before making tenant-scoped requests (current pattern).

**Question:** Which resolution strategy? Option A seems cleanest but adds a
network call at construction. Option B defers but adds complexity. Option C
maintains current behavior where `ensure_tenant` already does this.

### 3. Configuration Alignment

**Proposed:**

```python
class MimirClientSettings(BaseSettings):
    tenant: str | None = None   # env: MIMIR_TENANT (new primary)
    tenant_id: int | None = None  # env: MIMIR_TENANT_ID (deprecated)
```

**Question:** Confirm env var naming. Should `MIMIR_TENANT` be the new primary,
with `MIMIR_TENANT_ID` emitting a deprecation warning?

### 4. Scope Boundary

**Assertion:** This change is client-only. The backend `X-Tenant-ID` header
continues to accept integer values. No backend API changes are needed.

**Question:** Confirm this scope boundary. Is there any reason to also support
string shortnames in the `X-Tenant-ID` header at the backend level?

### 5. Impact on MimirClient (Async)

The same issue exists in the async `MimirClient`. Both clients should be updated
in the same release for API surface consistency.

**Question:** Confirm both sync and async clients are in scope.

## Files Affected (for reference)

- `clients/python/src/mimir_client/sync_client.py` -- constructor, tenant_id property
- `clients/python/src/mimir_client/client.py` -- constructor, tenant_id property
- `clients/python/src/mimir_client/config.py` -- MimirClientSettings
- `clients/python/src/mimir_client/__init__.py` -- re-exports
- `clients/python/tests/unit/test_sync_client.py` -- test updates
- `clients/python/tests/unit/test_client.py` -- test updates
- `clients/python/pyproject.toml` -- version bump

## Requested Deliverable

An architectural decision on each of the five questions above, so Product can
create the implementation checklist and hand off to engineering.