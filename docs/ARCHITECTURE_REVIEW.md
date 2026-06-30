# TradeXV2 — Architectural Review

**Reviewer**: Principal Architect
**Date**: 2026-06-30
**Scope**: Full codebase structure, module organization, layer boundaries

---

## Executive Summary

The codebase has a solid hexagonal core but accumulated organizational debt across 4 phases of rapid development. The main issues are: duplicate modules that should be unified, misplaced files that violate layer intent, two parallel metric systems with no integration, and root-level data/state directories mixed with source code.

---

## Critical Issues (Fix First)

### 1. Two Parallel Metric Systems

`infrastructure/metrics/` (Counter/Gauge/Histogram/Timer with Prometheus export) and `infrastructure/observability/event_metrics.py` (EventMetrics with rate-based alerting) are independent, incompatible systems.

**Impact**: Every new metric must choose which system to use. The Prometheus exporter renders from both systems separately. Alerting only works with EventMetrics.

**Fix**: Refactor EventMetrics to use MetricsRegistry under the hood. The `EventMetrics.inc(event_type, outcome)` pattern becomes a labeled Counter in MetricsRegistry.

### 2. Duplicate Resource Managers

`resource_manager.py` (218 lines) and `async_resource_manager.py` (216 lines) are 90% identical code with sync vs async cleanup functions.

**Fix**: Unify into a single `ResourceManager` that detects coroutine cleanup functions via `asyncio.iscoroutine()`.

### 3. Dual DI Registration

`api/deps.py` maintains a `ServiceContainer` dataclass AND delegates to `infrastructure/di.py` Container. Services are registered in both places.

**Fix**: Eliminate `ServiceContainer`. Use `di.py` Container as single source of truth. The `get_*` functions resolve from the container.

### 4. Duplicate Entity Definitions

- `Instrument`: 3 definitions (domain, brokers/common, brokers/dhan)
- `Trade`: 4 definitions (domain, datalake, analytics, api)
- `OrderStatus`: 2 definitions (domain, analytics/paper)

**Fix**: Domain entities are canonical. Broker-specific fields go in broker adapters. API schemas use Pydantic wrappers over domain types.

---

## Moderate Issues (Fix Next)

### 5. Misplaced Files

| File | Current Location | Should Be |
|------|-----------------|-----------|
| `async_event_bus.py` | `infrastructure/` root | `infrastructure/event_bus/` |
| `tracing.py` | `infrastructure/` root | `infrastructure/observability/` |
| `opentelemetry_setup.py` | `infrastructure/` root | `infrastructure/observability/` |
| `audit.py` | `infrastructure/` | `application/` (AuditLogger is app logic) |
| `verify_deps.py` | project root | `scripts/` |

### 6. Root-Level Data Directory

`market_data/` at project root contains live SQLite databases, a 95MB DuckDB catalog, and JSON snapshots. This is runtime state, not source code.

**Fix**: Add `market_data/` to `.gitignore`. Document that it is created at runtime. Consider moving to a configurable data directory.

### 7. Backward-Compat Shims

Three root-level files are pure re-exports:
- `endpoints.py` → `config/endpoints.py`
- `indices.py` → `config/indices.py`
- `secrets_manager.py` → `config/secrets_manager.py`

**Fix**: Find all importers, update to canonical paths, delete shims.

### 8. SecretsManager Naming Collision

- `config/secrets_manager.py` (`SecretsManager`) — reads credentials from env/files
- `infrastructure/security/secret_manager.py` (`SecretManager`) — Fernet encryption

**Fix**: Rename to `CredentialReader` and `EncryptionManager` respectively.

---

## Minor Issues (Clean Up)

### 9. Stale `infrastructure/__init__.py`

The docstring lists "future" modules (logging, metrics, cache) that already exist. Exports nothing.

**Fix**: Update docstring or remove it.

### 10. Broker-Specific Code in Root conftest.py

`conftest.py` contains Dhan SDK monkeypatching that belongs in `brokers/dhan/tests/conftest.py`.

### 11. Low Fan-In Modules

These modules have 1-2 consumers and may be dead code or over-engineered:
- `portfolio_tracker.py` — 0 production consumers (only test)
- `position_repository_adapter.py` — 1 consumer
- `order_repository_adapter.py` — 1 consumer

---

## Recommended Module Organization (Target State)

```
infrastructure/
  logging_config.py        # Logging + correlation
  metrics/                 # Single metrics system (unified)
  cache.py                 # MemoryCache
  cache_redis.py           # RedisCache
  health.py                # HealthCheck, HealthRegistry
  observability/           # ALL observability in one place
    tracing.py             # @trace_operation, TraceContext
    opentelemetry_setup.py # OTel SDK init
    event_metrics.py       # Refactored to use MetricsRegistry
    alerting.py            # AlertingEngine
    http_server.py         # /healthz, /readyz, /metrics
  correlation.py           # Correlation IDs
  global_exception_handler.py
  retry.py                 # @retry decorator
  resource_manager.py      # Unified (sync + async)
  di.py                    # DI container
  di_scopes.py             # Request scope
  serialization.py         # JsonSerializer
  audit/                   # Moved from infrastructure root
    store.py               # AuditStore ABC, MemoryAuditStore, FileAuditStore
    logger.py              # AuditLogger (application logic)
  event_bus/
    event_bus.py
    async_event_bus.py     # Moved from infrastructure root
    dead_letter_queue.py
    processed_trade_repository.py
  events/
    schema.py
    versioned_event.py
    replay.py
  lifecycle/
    lifecycle.py
  db/
    duckdb_pool.py
  security/
    secret_manager.py
  state_machine.py
  time_service.py
  event_log.py

application/
  oms/
    order_manager.py
    position_manager.py
    risk_manager.py
    portfolio_tracker.py   # Remove if unused
    context.py
    _internal/             # Keep as-is
    persistence/
  execution/
  trading/
  composer/
  portfolio/
  scanner/
  backtest/

domain/
  entities/                # ALL entity types here
  ports/                   # ALL protocols here
  repositories/            # ALL repository interfaces here
  constants/               # ALL constants here
  events/                  # Event types
  models/                  # DTOs only
  enums.py                 # All enums

market_data/               # Gitignored, runtime-created
```

---

## Priority Matrix

| Priority | Issue | Effort | Risk |
|----------|-------|--------|------|
| P0 | Unify metric systems | High | Medium |
| P0 | Unify resource managers | Medium | Low |
| P0 | Remove dual DI registration | Medium | Medium |
| P1 | Consolidate entity definitions | High | High |
| P1 | Move misplaced files | Low | Low |
| P1 | Gitignore market_data/ | Trivial | None |
| P2 | Delete backward-compat shims | Low | Low |
| P2 | Rename SecretsManager classes | Low | Low |
| P3 | Clean up root conftest.py | Low | Low |
| P3 | Remove dead code (portfolio_tracker) | Low | Low |
| P3 | Update infrastructure/__init__.py | Trivial | None |
