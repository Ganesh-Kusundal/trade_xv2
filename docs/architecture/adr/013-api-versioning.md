# ADR-013-API: REST API Versioning Strategy

## Status

Proposed

## Context

The REST API (`interface/api/`) serves multiple consumers: the Streamlit UI, CLI tools, MCP integrations, and potentially third-party clients. As the API evolves, breaking changes must not silently break existing consumers. The API currently has no versioning scheme, and endpoint changes are deployed directly.

The single API egress pattern (ADR-020) has been established for candle data (`candle_mapper.py`), but the broader API surface needs a versioning strategy.

## Decision

Adopt **URL-based API versioning** with the following conventions:

### Version Scheme

```
/api/v1/market/candles      # v1: current stable
/api/v2/market/candles      # v2: next breaking change (when needed)
```

### Rules

1. **Minor changes** (new fields, new endpoints) go into the current version without a version bump.
2. **Breaking changes** (removed fields, changed response shapes) require a new version.
3. **Deprecated versions** are maintained for 6 months with `Sunset` header.
4. **Version prefix** is enforced by FastAPI router grouping:

```python
# interface/api/app.py
app.include_router(v1_router, prefix="/api/v1")
app.include_router(v2_router, prefix="/api/v2")  # when needed
```

### Current State

The existing API is implicitly `v0`. The first formalized version will be `v1`, which documents the current stable contract. This is a non-breaking migration — existing endpoints are re-grouped under `/api/v1/` with redirects from the unversioned paths.

### Schema Versioning

Pydantic response schemas live in `interface/api/schemas.py` and are versioned alongside the API. The `Candle` schema (ADR-020) is the first versioned schema, with `candle_mapper.py` providing the wire-format mapping.

## Consequences

**Positive:**
- API consumers can pin to a known stable version.
- Breaking changes are explicit and announced.
- Multiple API versions can coexist during migration.

**Negative:**
- Multiple versions increase maintenance burden.
- Router grouping adds a layer of indirection.
- Schema duplication across versions (mitigated by inheritance).

## Enforcement

- `tests/architecture/test_domain_bar_types.py` — `test_api_candle_schema_is_wire_only`, `test_market_routers_use_series_mapper`
- `tests/architecture/test_candle_mapper.py` (existing) — wire-format mapping
- **NEW:** `tests/architecture/test_api_versioning.py` (proposed)
