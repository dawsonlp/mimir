# CLI-01: Implementation Checklist -- Tenant Shortname Migration

**Implements:** cli-01-technical-design.md
**Target:** mimir-client v5.3.0
**Status:** Complete

---

## Construction Order

Per RULES.md, domain objects first, then tests, then infrastructure.

### Step 1: Exceptions (domain error types)

- [x] Modify `exceptions.py`: Refactor `MimirTenantError.__init__` to accept
  optional `message: str | None` parameter with sensible default. Update default
  message to reference `tenant` (shortname) instead of `tenant_id`.

### Step 2: Exports

- [x] Modify `__init__.py`: Add `MimirTenantError` to both the import block and
  `__all__` list.

### Step 3: Configuration

- [x] Modify `config.py`: Add `tenant: str | None = None` field to
  `MimirClientSettings`. Add `model_validator(mode="after")` for mutual
  exclusion (both `tenant` and `tenant_id` set raises `ValueError`). Emit
  `DeprecationWarning` when `tenant_id` is set alone. Requires `Self` import
  for validator return type.

### Step 4: Sync client

- [x] Modify `sync_client.py` constructor: Change signature to
  `(api_url, tenant: str | None, timeout, *, tenant_id: int | None)`.
  Add mutual exclusion check. Add deprecation warning for `tenant_id` path.
  Initialize `_tenant`, `_resolved_tenant_id`, `_resolve_lock`
  (`threading.Lock`). Set header immediately only on deprecated `tenant_id`
  path.
- [x] Add `tenant` property (read/write). Setter clears `_resolved_tenant_id`
  and removes header if value is None.
- [x] Modify `tenant_id` property: Getter returns `_resolved_tenant_id`. Setter
  emits deprecation warning, clears `_tenant`, sets header directly.
- [x] Add `_resolve_shortname(shortname)` private method: Calls
  `GET /tenants/by-shortname/{shortname}` using `self._client.request()`
  directly (NOT through `_request()` to avoid recursion). Returns `Tenant` on
  success. Raises `MimirTenantError` on 404. Propagates other errors.
- [x] Add `_ensure_resolved()` private method: Double-checked locking pattern.
  No-op if `_tenant is None` or `_resolved_tenant_id is not None`. On
  resolution success, caches integer and sets header.
- [x] Modify `_request()`: Call `self._ensure_resolved()` at the top before
  dispatching.
- [x] Modify `ensure_tenant()`: After resolve/create, set both `self._tenant`
  and `self._resolved_tenant_id` directly (not via property setter, to avoid
  deprecation warning).
- [x] Update `from_settings()`: Pass both `settings.tenant` and
  `settings.tenant_id` to constructor.
- [x] Update module docstring to reflect new `tenant: str` API.

### Step 5: Sync client tests

- [x] Modify `tests/unit/test_sync_client.py`: Add tests for new construction
  behaviors (tenant shortname, mutual exclusion, deprecation warning). Add lazy
  resolution tests using respx mocks (first request resolves, second reuses
  cache, unknown shortname raises error). Add property behavior tests (tenant
  setter clears cache, tenant_id setter deprecated). Add ensure_tenant alignment
  tests. Add config mutual exclusion tests (new `test_config.py` or inline).
  Update existing tests that use `tenant_id=N` construction to remain passing
  (backward compat path).

### Step 6: Async client

- [x] Modify `client.py`: Mirror all sync client changes with `async`/`await`
  variants. Use `asyncio.Lock` instead of `threading.Lock`. Use
  `await self._client.request()` in `_resolve_shortname`. Same constructor
  signature, same property logic, same `_ensure_resolved()` pattern (with
  `async with self._resolve_lock`).
- [x] Update `from_settings()`: Pass both `settings.tenant` and
  `settings.tenant_id` to constructor.
- [x] Update module docstring to reflect new `tenant: str` API.

### Step 7: Async client tests

- [x] Modify `tests/unit/test_client.py`: Mirror sync test changes for async
  client. Same test matrix: construction, lazy resolution, properties,
  ensure_tenant, configuration.

### Step 8: Version bump and packaging

- [x] Modify `pyproject.toml`: Bump version from `"5.2.0"` to `"5.3.0"`.

### Step 9: Verification

- [x] Run full test suite: `cd clients/python && uv venv .venv && source
  .venv/bin/activate && uv pip install -e ".[dev]" && pytest tests/ -v`
  -- 63 passed in 0.72s
- [x] Verify no ruff lint errors: `ruff check src/ tests/`
  -- All checks passed!
- [x] Verify deprecation warnings are emitted correctly (manual spot check or
  test assertion using `pytest.warns(DeprecationWarning)`)
  -- 7 tests assert DeprecationWarning via `pytest.warns()`

---

## Files Modified (9 total)

| File | Action | Step |
|------|--------|------|
| `src/mimir_client/exceptions.py` | Modify | 1 |
| `src/mimir_client/__init__.py` | Modify | 2 |
| `src/mimir_client/config.py` | Modify | 3 |
| `src/mimir_client/sync_client.py` | Modify | 4 |
| `tests/unit/test_sync_client.py` | Modify | 5 |
| `src/mimir_client/client.py` | Modify | 6 |
| `tests/unit/test_client.py` | Modify | 7 |
| `pyproject.toml` | Modify | 8 |
| `tests/unit/test_config.py` | Add | 5 |

---

## Test Budget

Per RULES.md test count heuristic, the module has approximately 12-15
meaningful domain decisions per client variant:

- 4 construction modes (tenant only, tenant_id only, both, neither)
- 3 resolution behaviors (success, 404, cached reuse)
- 4 property transitions (tenant set/clear, tenant_id set/clear)
- 3 ensure_tenant behaviors (existing, create, replace)
- 3 config behaviors (tenant only, tenant_id only, both)

Expect approximately 15-20 tests per client (sync + async), plus 3-5 config
tests. Total: approximately 35-45 tests across all test files. Existing
passing tests that use `tenant_id=N` construction continue to pass (backward
compatibility).

---

## Out of Scope (explicit)

- No backend changes
- No per-call tenant override on data methods
- No README rewrite (already updated for v5.3.0)
- No changelog update (already has [Unreleased] section)