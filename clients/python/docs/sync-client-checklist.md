# Sync Client Implementation Checklist

**Enhancement**: mimir-client Sync Support
**Approach**: Option A — `MimirSyncClient` alongside existing async `MimirClient`
**Rationale**: Follows httpx pattern (`Client` sync + `AsyncClient` async). No event loop threading needed — httpx provides native sync `Client`.

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Pattern | Separate `MimirSyncClient` class | Follows httpx convention; clean separation; no runtime complexity |
| HTTP transport | `httpx.Client` (sync) | Same library, same error types, no event loop bridge needed |
| API surface | Mirror all `MimirClient` methods without `async`/`await` | 1:1 parity; no surprises for users switching between sync/async |
| Module | New `sync_client.py` | Keeps async client untouched; sync import does not pull asyncio |
| Context manager | `__enter__`/`__exit__` on sync; existing `__aenter__`/`__aexit__` on async | Standard Python protocol |

## Implementation Steps

- [x] Create `clients/python/src/mimir_client/sync_client.py` with `MimirSyncClient`
  - Uses `httpx.Client` (synchronous)
  - Same constructor: `api_url`, `tenant_id`, `timeout`
  - Same `from_settings()` classmethod
  - Same `tenant_id` property with header management
  - `close()` method (sync)
  - `__enter__`/`__exit__` context manager
  - All public methods from `MimirClient` as synchronous equivalents
  - Same error mapping via `_request()` (sync version)
- [x] Export `MimirSyncClient` from `__init__.py`
- [x] Add `MimirSyncClient` to `__all__` list
- [x] Create `clients/python/tests/unit/test_sync_client.py`
  - Construction tests (default, params, from_settings)
  - Error mapping tests (404, 409, 422, 5xx)
  - Tenant CRUD tests
  - Artifact create/list tests
  - Search test
  - Health test
  - Context manager test
  - Header injection test
- [x] Bump version to `5.1.0` in `pyproject.toml` (minor feature)
- [x] Update `README.md` with sync client usage section
- [x] Update `changelog.md`

## What Changes

| File | Change |
|------|--------|
| `sync_client.py` | **New** — `MimirSyncClient` class |
| `__init__.py` | Add `MimirSyncClient` import and `__all__` entry |
| `test_sync_client.py` | **New** — sync client unit tests |
| `pyproject.toml` | Version bump `5.0.5` -> `5.1.0` |
| `README.md` | Add sync usage documentation |
| `changelog.md` | Add entry for sync client |

## What Does NOT Change

- `client.py` — async `MimirClient` is untouched
- `models.py` — no changes
- `exceptions.py` — no changes
- `config.py` — no changes (already works for both)
- Existing tests — no changes