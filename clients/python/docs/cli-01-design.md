# CLI-01: Design Document -- Tenant Shortname as Primary Client Identifier

**From:** Chief Architect
**To:** Senior Engineer / Implementing Engineer
**Date:** 2026-03-29
**Status:** Approved
**Applies to:** mimir-client v5.3.0
**Supersedes:** Relevant sections of design.md Section 2 (Tenant is per-call with an optional default)

---

## Problem

The `mimir-client` v5.2.0 constructor exposes `tenant_id: int` as the primary
tenant identifier. This integer is a database surrogate key -- an implementation
detail of the PostgreSQL backend. The Mimir domain identifies tenants by string
shortname (e.g., `"rademo1"`, `"dev"`). All downstream consumers, including the
`ooda_framework` `MemoryProtocol`, identify tenants by string.

Forcing callers to resolve shortnames to integers before constructing the client
is a leaked abstraction. It inverts the dependency: consumers must know about
database internals to use a domain-level API.

---

## Scope

This change is **client-library only**. No backend API changes.

| In Scope | Out of Scope |
|----------|--------------|
| `MimirSyncClient` constructor and tenant state | Backend `X-Tenant-ID` header handling |
| `MimirClient` (async) constructor and tenant state | Backend tenant resolution endpoints |
| `MimirClientSettings` configuration | Any backend router changes |
| Lazy resolution of shortname to integer | New backend endpoints |
| Deprecation path for `tenant_id: int` parameter | Database schema changes |
| `ensure_tenant()` behavior alignment | Other client methods (signatures unchanged) |

The backend `X-Tenant-ID` header continues to accept integer values. The existing
`GET /tenants/by-shortname/{shortname}` endpoint is the resolution mechanism. Both
are unchanged.

---

## Interface Changes

### Constructor

Both `MimirSyncClient` and `MimirClient` adopt the same signature:

| Parameter | Type | Position | Required | Notes |
|-----------|------|----------|----------|-------|
| `api_url` | `str` | Positional | No (default provided) | Unchanged |
| `tenant` | `str or None` | Positional | No | New primary. Domain shortname. |
| `timeout` | `float` | Positional | No | Unchanged |
| `tenant_id` | `int or None` | Keyword-only | No | Deprecated. Removed in v6.0.0. |

`tenant_id` is keyword-only (after `*`) to prevent positional confusion with
the v5.2.0 signature where `tenant_id` was the second positional parameter.

**Mutual exclusion:** If both `tenant` and `tenant_id` are provided, the client
raises `ValueError` immediately. No precedence rules. Ambiguity is the caller's
mistake.

**Deprecation:** When `tenant_id` is provided (and `tenant` is not), the client
emits a `DeprecationWarning` via `warnings.warn()` with `stacklevel=2`. The
warning message must state that `tenant_id` will be removed in v6.0.0 and that
callers should use `tenant` instead.

### Public Properties

| Property | Type | Replaces | Notes |
|----------|------|----------|-------|
| `tenant` | `str or None` | -- | New primary. Read/write. |
| `tenant_id` | `int or None` | Old primary | Deprecated. Returns resolved integer if available, `None` if not yet resolved. Setter emits deprecation warning. |

Setting `tenant` to a new value resets the internal resolution cache. The next
tenant-scoped request triggers re-resolution.

Setting `tenant_id` directly (deprecated path) sets the internal integer and
bypasses resolution. This is the backward-compatible escape hatch.

### Configuration

`MimirClientSettings` adds a new field and deprecates the old:

| Field | Type | Env Var | Notes |
|-------|------|---------|-------|
| `tenant` | `str or None` | `MIMIR_TENANT` | New primary |
| `tenant_id` | `int or None` | `MIMIR_TENANT_ID` | Deprecated. Emits warning when set. |

**Mutual exclusion at config level:** If both `MIMIR_TENANT` and `MIMIR_TENANT_ID`
are set in the environment, `MimirClientSettings` raises `ValueError` at
construction time. Do not guess.

`from_settings()` maps both fields to the constructor.

---

## Resolution Strategy

### Lazy Resolution

The client does not perform I/O at construction time. When `tenant: str` is
provided, the shortname is stored. The integer ID required for the `X-Tenant-ID`
header is resolved on the first tenant-scoped HTTP request.

**Resolution flow:**

1. Caller constructs client with `tenant="rademo1"`.
2. Client stores `_tenant = "rademo1"`, `_resolved_tenant_id = None`.
3. Caller makes first tenant-scoped request (e.g., `create_artifact(...)`).
4. Client detects `_resolved_tenant_id is None` and `_tenant is not None`.
5. Client calls `GET /tenants/by-shortname/rademo1`.
6. On success: caches `_resolved_tenant_id = tenant.id`, injects `X-Tenant-ID` header, proceeds with original request.
7. On 404: raises `MimirTenantError` -- "Tenant shortname 'rademo1' not found."
8. All subsequent requests reuse the cached integer. No further resolution calls.

**Resolution does NOT create tenants.** If the shortname does not exist, the
client fails. Only `ensure_tenant()` creates tenants when missing.

### When `tenant_id: int` Is Provided Directly (Deprecated Path)

No resolution occurs. The integer is used directly for the `X-Tenant-ID` header,
exactly as in v5.2.0. This path exists solely for backward compatibility.

### Thread Safety

The lazy resolution must be thread-safe. The first thread to trigger resolution
acquires a lock, resolves, and caches. Other threads waiting on the lock then
read the cached value. After resolution, no locking overhead.

- Sync client: `threading.Lock`
- Async client: `asyncio.Lock`

---

## `ensure_tenant()` Alignment

`ensure_tenant(shortname, name)` continues to work as before:

1. Attempts to resolve the shortname via `GET /tenants/by-shortname/{shortname}`.
2. If not found, creates the tenant via `POST /tenants`.
3. Sets the client's tenant context to the resolved/created tenant.

With the new design, step 3 means:

- Sets `self._tenant = shortname`
- Sets `self._resolved_tenant_id = tenant.id` (populates the cache)

If the client was constructed with a different `tenant`, calling `ensure_tenant()`
with a new shortname replaces it. This is an explicit caller action.

`ensure_tenant()` is the only code path that creates tenants. Lazy resolution
only resolves existing tenants.

---

## Error Behavior

| Condition | Error | When |
|-----------|-------|------|
| Both `tenant` and `tenant_id` provided to constructor | `ValueError` | Construction |
| Both `MIMIR_TENANT` and `MIMIR_TENANT_ID` set in env | `ValueError` | Settings construction |
| `tenant` shortname not found during lazy resolution | `MimirTenantError` | First tenant-scoped request |
| No tenant set and tenant-scoped request made | `MimirTenantError` | Request time (fail fast, unchanged from v5.2.0) |
| Network failure during resolution | `MimirConnectionError` | First tenant-scoped request |

---

## Deprecation Timeline

| Version | State |
|---------|-------|
| v5.2.0 | `tenant_id: int` is the only path (current) |
| v5.3.0 | `tenant: str` is primary. `tenant_id: int` accepted with deprecation warning. |
| v6.0.0 | `tenant_id` parameter removed from constructor, settings, and properties. |

The deprecation warning message must include the version where removal occurs
and the migration path.

---

## Interaction Patterns (v5.3.0)

### Single-tenant agent (primary path)

```
client = MimirSyncClient(api_url="http://mimir:38000", tenant="rademo1")
artifact = client.create_artifact(artifact_type="document", title="Requirements v1")
# First call triggers lazy resolution of "rademo1" -> integer ID
# All subsequent calls reuse the cached integer
```

### Configuration via environment

```
# Environment: MIMIR_TENANT=rademo1
settings = get_settings()
client = MimirSyncClient.from_settings(settings)
```

### Backward compatible (deprecated)

```
# Emits DeprecationWarning
client = MimirSyncClient(api_url="http://mimir:38000", tenant_id=1)
```

### Integration test with disposable tenant

```
with MimirSyncClient(api_url="http://mimir:38000") as client:
    tenant = client.ensure_tenant("test-run-abc", "Test Run")
    # client.tenant is now "test-run-abc", resolution cache is populated
    artifact = client.create_artifact(artifact_type="document", title="Test")
    # ... test operations ...
    client.delete_tenant(tenant.id)
```

### Async client (identical surface)

```
async with MimirClient(api_url="http://mimir:38000", tenant="rademo1") as client:
    artifact = await client.create_artifact(artifact_type="document", title="Spec")
```

---

## Boundaries

### What this design does NOT change

- Backend `X-Tenant-ID` header format (remains integer)
- Backend tenant endpoints (no new endpoints, no changes)
- Per-call `tenant_id` override on individual methods (described in design.md Section 2 but never implemented in v5.2.0; not in scope for CLI-01)
- The `Tenant` model (still has `id: int` and `shortname: str`)
- Any non-tenant aspects of the client API surface
- The `ensure_tenant()` create-if-missing semantics

### What this design does NOT specify

- Internal code organization (the engineer decides)
- Specific locking implementation details
- Test structure (the engineer follows RULES.md testing philosophy)
- How the deprecation warning is formatted (standard Python `DeprecationWarning`)

---

## Relationship to Original Design Document

The original `design.md` states in Section 2: "Tenant IDs are integers, not
strings. The API uses integer primary keys for tenants." This accurately
describes the wire protocol but was incorrectly promoted to the client's public
interface.

This design corrects that: the client's public interface uses domain shortnames.
The integer is an internal resolution detail hidden behind lazy resolution. The
original design document receives an addendum noting this correction. The
original document is not rewritten -- its other constraints (thin wrapper, no
caching, no retry, fail fast, context manager, thread safety) remain in force.

---

## References

- Product assessment: `cli-01-product-assessment.md`
- Architect review request: `cli-01-architect-review-request.md`
- Original client design: `design.md`
- Backend tenant router: `backend/src/mimir/routers/tenants.py`