# CLI-01: Technical Design -- Tenant Shortname Migration

**From:** Lead Systems Engineer
**To:** Implementing Engineer
**Date:** 2026-03-29
**Status:** Ready for implementation
**Implements:** cli-01-design.md (Architect's Design Document)
**Target:** mimir-client v5.3.0

---

## Purpose

This document bridges the architect's design to implementation. It specifies
library and pattern choices, data structures, resolution mechanics, error
handling, and testing strategy for the tenant shortname migration in
`mimir-client`.

The implementing engineer retains authority over final coding decisions within
these constraints.

---

## Architecture Summary

The change replaces `tenant_id: int` with `tenant: str` (domain shortname) as
the primary tenant identifier in both `MimirSyncClient` and `MimirClient`.
Internally, the client lazily resolves the shortname to the integer required
by the backend `X-Tenant-ID` header. The `tenant_id: int` parameter is
retained as a deprecated keyword-only argument for backward compatibility,
with removal planned for v6.0.0.

---

## Files Changed

| File | Change Type | Summary |
|------|-------------|---------|
| `sync_client.py` | Modify | Constructor, properties, lazy resolution, `ensure_tenant()` |
| `client.py` | Modify | Same changes as sync, with `async`/`await` variants |
| `config.py` | Modify | Add `tenant: str` field, deprecation validator |
| `exceptions.py` | Modify | Refactor `MimirTenantError` to accept message parameter |
| `__init__.py` | Modify | Add `MimirTenantError` to exports |
| `pyproject.toml` | Modify | Version bump to 5.3.0 |
| `tests/unit/test_sync_client.py` | Modify | New tests for tenant shortname, deprecation, resolution |
| `tests/unit/test_client.py` | Modify | Mirror sync test changes for async client |
| `tests/unit/test_config.py` | Add | Tests for settings mutual exclusion and deprecation |

---

## Engineering Clarifications

The following gaps were identified during analysis. Resolutions are documented
here as engineering decisions within the architect's design boundaries.

### C1: Header Injection Strategy

**Decision:** Set persistent header on `httpx.Client`/`httpx.AsyncClient` after
first resolution, consistent with the current `tenant_id` setter pattern.

The v5.2.0 client sets `X-Tenant-ID` as a persistent header on the httpx client
instance. This continues unchanged. After lazy resolution completes, the resolved
integer is written to `self._client.headers["X-Tenant-ID"]` exactly as the
current `tenant_id` setter does. No per-request header injection is needed.

### C2: `tenant_id` Setter Clears `_tenant`

**Decision:** Setting `tenant_id` directly (deprecated path) clears `_tenant`
and the resolution cache.

This prevents inconsistent state where `_tenant = "rademo1"` but
`_resolved_tenant_id = 5` (an unrelated integer). The deprecated `tenant_id`
setter establishes a pure integer-based state, equivalent to v5.2.0 behavior.

### C3: `MimirTenantError` Refactoring

**Decision:** Change `MimirTenantError.__init__` to accept an optional message
parameter with a sensible default that references the new `tenant` parameter.

The default message updates from referencing `tenant_id` to referencing `tenant`.
The exception remains in the same position in the hierarchy.

### C4: `MimirTenantError` Public Export

**Decision:** Add `MimirTenantError` to `__init__.py` imports and `__all__`.

This exception is part of the public API but was not exported in v5.2.0. Since
the design makes it a documented error condition, it must be importable.

### C5: No Per-Call Tenant Override

**Decision:** The original `design.md` describes per-call `tenant_id` on each
data method, but v5.2.0 never implemented this. CLI-01 does not introduce it.
This is explicitly out of scope.

---

## Internal State Model

### New Instance Variables

| Variable | Type | Purpose |
|----------|------|---------|
| `_tenant` | `str or None` | Shortname provided at construction or via property |
| `_resolved_tenant_id` | `int or None` | Cached integer from resolution |
| `_resolve_lock` | `threading.Lock` (sync) / `asyncio.Lock` (async) | Thread-safety for lazy resolution |

### State Transitions

The client has three valid states:

**State A -- No tenant:** `_tenant = None`, `_resolved_tenant_id = None`.
Tenant-scoped requests raise `MimirTenantError`. System-level operations
(tenant management, health) work normally.

**State B -- Shortname set, not yet resolved:** `_tenant = "rademo1"`,
`_resolved_tenant_id = None`. First tenant-scoped request triggers resolution.
No `X-Tenant-ID` header is present on the httpx client yet.

**State C -- Resolved (or direct integer):** `_tenant = "rademo1"` (or `None`
if set via deprecated path), `_resolved_tenant_id = 1`. The `X-Tenant-ID`
header is set on the httpx client. All tenant-scoped requests proceed normally.

**Transitions:**

```
Construction with tenant="x"     -> State B
Construction with tenant_id=N    -> State C (_tenant=None, _resolved_tenant_id=N)
Construction with neither        -> State A
State B + first tenant request   -> State C (via resolution)
State C + tenant setter = "y"    -> State B (cache cleared)
State C + tenant setter = None   -> State A
State C + tenant_id setter = N   -> State C (_tenant cleared)
State C + tenant_id setter = None -> State A
State * + ensure_tenant("x")     -> State C (_tenant="x", _resolved_tenant_id=N)
```

---

## Constructor Implementation Pattern

### Sync Client

```python
def __init__(
    self,
    api_url: str = "http://localhost:38000",
    tenant: str | None = None,
    timeout: float = 30.0,
    *,
    tenant_id: int | None = None,
):
```

**Initialization logic:**

1. If both `tenant` and `tenant_id` are provided, raise `ValueError`.
2. If `tenant_id` is provided (and `tenant` is not), emit `DeprecationWarning`.
   Set `_resolved_tenant_id = tenant_id`, `_tenant = None`. Set `X-Tenant-ID`
   header on httpx client immediately (v5.2.0 behavior).
3. If `tenant` is provided, set `_tenant = tenant`, `_resolved_tenant_id = None`.
   Do not set `X-Tenant-ID` header (deferred to resolution).
4. If neither is provided, set both to `None`. No header.

### Async Client

Identical logic. The only difference is `httpx.AsyncClient` instead of
`httpx.Client`, and `asyncio.Lock` instead of `threading.Lock`.

---

## Lazy Resolution Implementation Pattern

### Resolution Method (Sync)

A private method `_resolve_tenant()` is called from `_request()` before
dispatching the HTTP request, if resolution is needed.

**Guard condition:** Resolution is needed when `_tenant is not None` and
`_resolved_tenant_id is None`.

**Flow:**

```python
def _ensure_resolved(self):
    if self._tenant is not None and self._resolved_tenant_id is None:
        with self._resolve_lock:
            if self._resolved_tenant_id is not None:
                return  # Another thread resolved while we waited
            tenant = self._resolve_shortname(self._tenant)
            self._resolved_tenant_id = tenant.id
            self._client.headers["X-Tenant-ID"] = str(tenant.id)
```

The `_resolve_shortname` method calls `GET /tenants/by-shortname/{shortname}`
directly using `self._client.request()` (bypassing the `_request` wrapper to
avoid infinite recursion). On 404, it raises `MimirTenantError` with the
shortname in the message. On other errors, it propagates normally.

**Integration point:** `_ensure_resolved()` is called at the top of `_request()`
before the actual HTTP call. This means every request path goes through
resolution check, but after the first resolution, the check is a simple
`None` comparison with no lock overhead.

### Resolution Method (Async)

Same pattern with `async def _ensure_resolved(self)` and `async with
self._resolve_lock`.

### Resolution Bypass

The following methods do NOT trigger resolution (they are system-level or
not tenant-scoped):

- `create_tenant()`
- `get_tenant()`
- `get_tenant_by_shortname()`
- `list_tenants()`
- `update_tenant()`
- `delete_tenant()`
- `health()`
- `is_healthy()`
- All `*_type` methods (artifact types, relation types, embedding types)

**Implementation approach:** Rather than listing exempt methods, the resolution
check fires in `_request()` but only resolves if `_tenant is not None` and
`_resolved_tenant_id is None`. System-level methods work regardless because
they do not require the `X-Tenant-ID` header -- the backend does not check
for it on those endpoints. If a tenant is set, the header is sent even on
system-level calls (this matches v5.2.0 behavior where the header was set
on the httpx client globally).

The only case where resolution failure would block system-level calls is if
the shortname is invalid and the user tries to make a tenant-scoped call
first. System-level calls that happen to run before any tenant-scoped call
will succeed without triggering resolution (because the header is not yet
set, and system-level endpoints do not require it).

**Refinement:** To avoid unnecessary resolution attempts on system-level calls,
`_ensure_resolved()` should be a no-op when `_tenant is None` (State A). When
`_tenant is not None` and `_resolved_tenant_id is None` (State B), resolution
fires. This means system-level calls while in State B will NOT trigger
resolution -- resolution only fires when the header would actually be needed.

However, this creates a subtlety: in State B, the `X-Tenant-ID` header is
absent. If a system-level endpoint happens to be called first, it succeeds
without the header. If a tenant-scoped endpoint is called first, resolution
fires. This is correct behavior.

**Simplest correct approach:** Call `_ensure_resolved()` in `_request()`.
It checks `_tenant is not None and _resolved_tenant_id is None`. If true,
it resolves. If `_tenant is None`, it is a no-op. System-level calls in
State A pass through. System-level calls in State B also trigger resolution
(since we cannot distinguish system-level from tenant-scoped calls at the
`_request()` level without inspecting the URL path, which is fragile).

This means that if a client is constructed with `tenant="rademo1"` and the
first call is `list_tenants()`, the resolution will fire even though
`list_tenants()` does not need it. This is acceptable: one extra HTTP call
that was going to happen anyway, just slightly earlier than strictly necessary.
The alternative (path-based routing of resolution) adds complexity for minimal
benefit.

---

## Property Implementation

### `tenant` Property

```python
@property
def tenant(self) -> str | None:
    return self._tenant

@tenant.setter
def tenant(self, value: str | None):
    self._tenant = value
    self._resolved_tenant_id = None
    if value is None:
        self._client.headers.pop("X-Tenant-ID", None)
    # If value is not None, header will be set on next resolution
```

### `tenant_id` Property (Deprecated)

```python
@property
def tenant_id(self) -> int | None:
    return self._resolved_tenant_id

@tenant_id.setter
def tenant_id(self, value: int | None):
    import warnings
    warnings.warn(
        "tenant_id is deprecated and will be removed in v6.0.0. "
        "Use tenant (shortname string) instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    self._tenant = None  # Clear shortname -- pure integer mode
    self._resolved_tenant_id = value
    if value is not None:
        self._client.headers["X-Tenant-ID"] = str(value)
    else:
        self._client.headers.pop("X-Tenant-ID", None)
```

---

## `ensure_tenant()` Implementation Pattern

```python
def ensure_tenant(self, shortname: str = "dev", name: str = "Development") -> Tenant:
    try:
        tenant = self.get_tenant_by_shortname(shortname)
    except MimirNotFoundError:
        tenant = self.create_tenant(shortname, name)
    self._tenant = shortname
    self._resolved_tenant_id = tenant.id
    self._client.headers["X-Tenant-ID"] = str(tenant.id)
    return tenant
```

This is functionally identical to v5.2.0 but now sets both `_tenant` and
`_resolved_tenant_id` instead of just `_tenant_id`.

---

## Configuration Implementation Pattern

### `MimirClientSettings`

```python
class MimirClientSettings(BaseSettings):
    api_url: str = "http://localhost:38000"
    tenant: str | None = None      # env: MIMIR_TENANT
    tenant_id: int | None = None   # env: MIMIR_TENANT_ID (deprecated)
    timeout: float = 30.0

    model_config = {"env_prefix": "MIMIR_", "env_file": ".env"}

    @model_validator(mode="after")
    def _check_tenant_mutual_exclusion(self) -> Self:
        if self.tenant is not None and self.tenant_id is not None:
            raise ValueError(
                "Cannot set both MIMIR_TENANT and MIMIR_TENANT_ID. "
                "Use MIMIR_TENANT (shortname string). "
                "MIMIR_TENANT_ID is deprecated."
            )
        if self.tenant_id is not None:
            import warnings
            warnings.warn(
                "MIMIR_TENANT_ID is deprecated and will be removed in v6.0.0. "
                "Use MIMIR_TENANT (shortname string) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        return self
```

### `from_settings()`

```python
@classmethod
def from_settings(cls, settings: MimirClientSettings) -> MimirSyncClient:
    return cls(
        api_url=settings.api_url,
        tenant=settings.tenant,
        timeout=settings.timeout,
        tenant_id=settings.tenant_id,
    )
```

Both `tenant` and `tenant_id` are passed through. The constructor handles
mutual exclusion and deprecation warnings. The `from_settings()` method
does not add its own logic.

---

## Exception Changes

### `MimirTenantError`

```python
class MimirTenantError(MimirError):
    """Raised when tenant context is missing or cannot be resolved."""

    def __init__(self, message: str | None = None):
        super().__init__(
            message or (
                "No tenant set. Provide tenant (shortname) at construction "
                "or call ensure_tenant() before making tenant-scoped requests."
            )
        )
```

Usage examples:

- Missing tenant: `raise MimirTenantError()` (default message)
- Resolution failure: `raise MimirTenantError(f"Tenant shortname '{shortname}' not found. Create the tenant first or check the shortname.")`

### `__init__.py` Export Addition

Add `MimirTenantError` to both the import block and `__all__`.

---

## Deprecation Warning Text

All deprecation warnings use the same format:

**Constructor:** `"tenant_id parameter is deprecated and will be removed in v6.0.0. Use tenant (shortname string) instead."`

**Property setter:** `"tenant_id is deprecated and will be removed in v6.0.0. Use tenant (shortname string) instead."`

**Config:** `"MIMIR_TENANT_ID is deprecated and will be removed in v6.0.0. Use MIMIR_TENANT (shortname string) instead."`

---

## Testing Strategy

Tests follow RULES.md testing philosophy: test outcomes under change, not
implementation details. The self-check applies to every test.

### Unit Tests -- Domain Decisions

These test the business-meaningful behaviors of the tenant shortname migration.

**Construction behaviors:**

| Test | Asserts |
|------|---------|
| Construct with `tenant="x"` stores shortname, no header set | State B established correctly |
| Construct with `tenant_id=N` (deprecated) sets header, emits warning | Backward compatibility preserved |
| Construct with both `tenant` and `tenant_id` raises `ValueError` | Mutual exclusion enforced |
| Construct with neither leaves no tenant state | State A established correctly |

**Lazy resolution behaviors (using respx mocks):**

| Test | Asserts |
|------|---------|
| First tenant-scoped request resolves shortname via GET endpoint | Resolution call made, header set, original request succeeds |
| Second tenant-scoped request reuses cached integer, no resolution call | Amortized cost verified |
| Resolution with unknown shortname raises `MimirTenantError` | Fail-fast on invalid tenant |
| Resolution with network failure raises `MimirConnectionError` | Error propagation correct |

**Property behaviors:**

| Test | Asserts |
|------|---------|
| Setting `tenant` to new value clears resolution cache | Re-resolution on next request |
| Setting `tenant` to `None` removes header | State A reachable from State C |
| `tenant_id` getter returns `None` before resolution, integer after | State-dependent return |
| `tenant_id` setter (deprecated) clears `_tenant`, sets header, emits warning | Backward compat escape hatch |

**`ensure_tenant()` behaviors:**

| Test | Asserts |
|------|---------|
| `ensure_tenant()` with existing tenant sets both `_tenant` and resolved ID | Cache populated |
| `ensure_tenant()` with missing tenant creates it, sets state | Create-if-missing works |
| `ensure_tenant()` with different shortname replaces previous tenant | Explicit override |

**Configuration behaviors:**

| Test | Asserts |
|------|---------|
| `MIMIR_TENANT` sets `tenant` field | New primary path |
| `MIMIR_TENANT_ID` sets `tenant_id` field with deprecation warning | Backward compat |
| Both `MIMIR_TENANT` and `MIMIR_TENANT_ID` raises `ValueError` | Mutual exclusion |
| `from_settings()` maps both fields to constructor | Integration correct |

### Tests NOT Written

Per RULES.md anti-patterns:

- No tests that `_tenant` field exists or is set (tests fields, not behavior)
- No tests that `_resolve_lock` is a `threading.Lock` (tests implementation)
- No tests mirroring method structure (one test per method)
- No tests that `warnings.warn` is called with specific `stacklevel` (tests wiring)

### Test Count Heuristic

The module has approximately 12-15 meaningful domain decisions (construction
modes, resolution triggers, property state transitions, error conditions,
configuration validation). The test count should be in that range per client
(sync + async), not 50+ tests that mirror code structure.

---

## Version Bump

`pyproject.toml` version changes from `"5.2.0"` to `"5.3.0"`.

---

## Construction Order

Per RULES.md:

1. **Exceptions first** -- Refactor `MimirTenantError`, add to exports
2. **Config next** -- Add `tenant` field, mutual exclusion validator
3. **Sync client** -- Constructor, properties, resolution, `ensure_tenant()`
4. **Sync client tests** -- Verify all behaviors
5. **Async client** -- Mirror sync changes with `async`/`await`
6. **Async client tests** -- Mirror sync tests
7. **Version bump** -- `pyproject.toml` to 5.3.0

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Lazy resolution adds latency to first request | Certain | Low -- one extra HTTP call, amortized | Document in README; `ensure_tenant()` available for eager resolution |
| `tenant_id` deprecation warning noise | Medium | Low | `stacklevel=2` ensures warning points to caller, not library internals |
| Thread contention on resolution lock | Low | Low | Lock only contended on first call; after that, no locking overhead |
| Callers depend on `tenant_id` returning integer at construction | Medium | Medium | `tenant_id` returns `None` until resolution; documented behavioral change |
| Config mutual exclusion breaks existing `.env` files with both vars | Low | Medium | Clear error message with migration guidance |

---

## Out of Scope

- Per-call `tenant_id` override on individual methods (design.md Section 2 describes this but v5.2.0 never implemented it; not part of CLI-01)
- Backend changes of any kind
- Cache invalidation for deleted tenants (thin wrapper philosophy)
- Shared connection pool for multi-client-instance deployments (see Future Considerations)
- `README.md` rewrite (minor updates to usage examples only)

---

## Future Considerations (v6.0.0)

These items are explicitly out of scope for v5.3.0 but are documented here
based on feedback from the RADEMO1 customer engagement. Their agent systems
will operate across multiple tenants simultaneously (organization knowledge
graph, agent practices knowledge graph, project-specific knowledge graph).

**Shared connection pool.** Multiple `MimirSyncClient` instances pointing at
the same `api_url` each create a separate `httpx.Client` with its own TCP
connection pool. For 3-5 tenant clients this is negligible overhead. If
many-tenant deployments become common, a shared transport mechanism
(e.g., `MimirConnectionPool` that vends tenant-bound client instances
sharing one httpx connection pool) would reduce resource usage. The current
per-client architecture does not prevent this -- it is an additive change.

**Cross-tenant context assembly.** The current context API is tenant-scoped:
graph traversal in tenant A does not surface artifacts from tenant B. The
multi-tenant agent pattern requires the agent to query each tenant
separately and synthesize at the application layer. Whether Mimir should
support cross-tenant queries natively is a deeper architectural question
that depends on customer feedback from production multi-tenant agent usage.

**Per-call tenant override.** The original `design.md` describes per-call
`tenant_id` on each data method. v5.2.0 never implemented this. v5.3.0
does not introduce it. If multi-tenant scripts that traverse many tenants
with a single client instance become a significant pattern, per-call tenant
override could be reconsidered for v6.0.0, potentially with shortname-based
resolution integrated into the call path.

---

## References

- Architect's design: `cli-01-design.md`
- Product assessment: `cli-01-product-assessment.md`
- Original client design: `design.md`
- Current sync client: `src/mimir_client/sync_client.py`
- Current async client: `src/mimir_client/client.py`
- Current config: `src/mimir_client/config.py`
- Current exceptions: `src/mimir_client/exceptions.py`
- Backend tenant router: `backend/src/mimir/routers/tenants.py`