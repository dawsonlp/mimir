# CLI-01: Product Assessment and Resolution Plan

**From:** Chief Product Officer
**Date:** 2026-03-29
**Status:** Complete
**Priority:** High
**Target Release:** mimir-client v5.3.0
**Current Status:** Implemented and released in v5.3.0; carried forward in v5.5.1.

---

## Summary

The RADEMO1 team reported that `mimir-client` v5.2.0 exposes database surrogate
keys (`tenant_id: int`) as the primary tenant identifier in the client API. This
forces consumers to resolve string shortnames to integers before constructing the
client, inverting the intended abstraction.

**This is a valid bug.** The Mimir domain identifies tenants by string shortname.
The integer ID is a database implementation detail that should not leak into the
client API.

## Decision

**Accepted as a high-priority fix, blocking RADEMO1.**

The enhancement request is well-documented, correctly identifies the root cause,
and proposes a reasonable solution. The fix aligns with Mimir's domain model and
will improve the developer experience for all client library consumers.

## Resolution Plan

### Scope

- **Client library only.** No backend API changes required.
- Both `MimirSyncClient` and `MimirClient` (async) will be updated.
- `MimirClientSettings` configuration will be updated to accept string tenant.
- Backward compatibility will be maintained with deprecation warnings on the
  integer path.

### Expected API (pending architect review)

```python
# New primary API -- tenant as string shortname
client = MimirSyncClient(api_url="http://mimir:38000", tenant="rademo1")

# Configuration via environment
# MIMIR_TENANT=rademo1 (new primary)
settings = get_settings()
client = MimirSyncClient.from_settings(settings)

# Backward compatible (deprecated, emits warning)
client = MimirSyncClient(api_url="http://mimir:38000", tenant_id=1)
```

The client will resolve the shortname to the integer ID internally using the
existing `GET /tenants/by-shortname/{shortname}` endpoint. This resolution is
transparent to the consumer.

### Process

| Step | Owner | Status |
|------|-------|--------|
| Product assessment | Product | Complete |
| Architect interface design review | Architect | Complete |
| Implementation checklist | Product + Engineering | Complete |
| Engineering implementation | Engineering | Complete |
| Test verification | Engineering | Complete |
| Release v5.3.0 | Engineering | Complete |

### Historical RADEMO1 Workaround

The workaround described in the original request was functional before v5.3.0:

> Call `ensure_tenant(shortname)` at initialization to resolve the shortname to
> an integer, then use the integer for subsequent calls.

This workaround should be removed from downstream consumers now that v5.3.0+
is available.

### Timeline

This work shipped in `mimir-client` v5.3.0.

## References

- Original request: RADEMO1 design review, CLI-01
- Architect review request: `clients/python/docs/cli-01-architect-review-request.md`
- Client design document: `clients/python/docs/design.md`
