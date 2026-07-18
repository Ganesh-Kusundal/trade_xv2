# TradeXV2 — Engineering Complexity Audit

**Date:** 2026-07-18
**Method:** Four parallel agents scanning 1,151 source files (158,211 lines) + 965 test files (144,789 lines) = 303,000 total lines.
**Scope:** Every production module from architectural root to executable leaf.

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Total source lines (src/) | 158,211 |
| Total test lines (tests/) | 144,789 |
| Total codebase | 303,000 |
| Source files | 1,151 |
| Test files | 965 |
| Findings | **136** |
| Estimated removable production lines | **~15,620** |
| Estimated removable test lines | **~3,000+** |
| Dead data (runtime-dev/) | **199 MB** |
| **Total removable as % of production code** | **~10%** |

The codebase is approximately **10% accidental complexity** — abstractions that exist for no observable business reason, pass-through wrappers, dead code, single-implementation interfaces, and duplicated logic.

---

## 1. Architectural Complexity Report

### Per-Module Complexity

| Module | Lines | Findings | Removable | % Removable |
|--------|------:|----------:|----------:|------------:|
| `src/brokers/` | 43,200 | 22 | ~1,000 | 2% |
| `src/domain/` | 22,896 | 30 | ~4,800 | 21% |
| `src/interface/` | 21,891 | 6 | ~350 | 2% |
| `src/analytics/` | 19,143 | 15 | ~3,600 | 19% |
| `src/application/` | 18,140 | 18 | ~1,185 | 7% |
| `src/infrastructure/` | 16,793 | 23 | ~3,114 | 18% |
| `src/datalake/` | 9,999 | 8 | ~350 | 4% |
| `src/config/` | 2,546 | 5 | ~730 | 29% |
| `src/runtime/` | 2,290 | 1 | ~24 | 1% |
| `src/tradex/` | 1,134 | 3 | ~110 | 10% |
| `src/plugins/` | 179 | 1 | 0 | 0% |
| **Total** | **158,211** | **136** | **~15,620** | **~10%** |

### Top-Level Architecture Concerns

1. **Triple simulation engines** — `analytics/replay/` (3,000 lines), `analytics/paper/` (1,200 lines), `analytics/backtest/` (1,200 lines). Three parallel bar-loop simulation frameworks solving the same problem.

2. **Port proliferation** — `domain/ports/` contains 10+ port files, many with single implementations, some superseded by newer ports in the same layer. Legacy ports retained for backward compatibility.

3. **Pass-through indirection chains** — Multiple 3-4 layer delegation paths: `Analytics facade → AnalyticsDataFetcher → AnalyticsAnalysisMethods → AnalyticsEngineFactory → engines`.

4. **Re-export shim accumulation** — ~15 re-export files that exist solely to maintain old import paths, each forwarding 1-8 symbols.

---

## 2. Abstraction Inventory

### Interfaces / Protocols with Single Implementation (YAGNI)

| Interface | Location | # Impl | Consumer Count | Verdict |
|-----------|----------|--------|----------------|---------|
| `IOrderManager` | `application/oms/protocols.py` | 1 | 0 (never used for typing) | Delete |
| `IPositionManager` | `application/oms/protocols.py` | 1 | 0 | Delete |
| `IRiskManager` | `application/oms/protocols.py` | 1 | 0 | Delete |
| `ITradingOrchestrator` | `application/oms/protocols.py` | 1 | 0 | Delete |
| `IExecutionAdapter` | `application/oms/protocols.py` | 1 | 0 | Delete |
| `IBrokerGateway` | `application/oms/protocols.py` | 1 | 0 | Delete |
| `ICapitalAllocationFn` | `application/oms/protocols.py` | 1 | 0 | Delete |
| `RiskCheckPort` | `application/oms/order_validator.py` | 1 | 0 | Delete |
| `BrokerAdapter` | `domain/ports/broker_adapter.py` | 1 | 0 | Delete |
| `BrokerInfrastructurePort` | `domain/ports/broker_infrastructure.py` | 1 | 1 | Simplify |
| `MarketDataPort` | `domain/ports/market_data.py` | 1 | 0 (superseded) | Delete |
| `SessionOpener` | `domain/ports/session_opener.py` | 1 | 0 | Delete |
| `CorrelationPort` | `domain/ports/correlation.py` | 1 | 0 | Delete |
| `ProviderRegistry` | `domain/providers/registry.py` | 1 | 0 | Delete |
| `BackoffStrategy` | `infrastructure/resilience/backoff.py` | 1 | 2 (tests only) | Simplify |
| `ExecutionModeAdapter` | `application/execution/execution_mode_adapter.py` | 1 | 0 (deprecated) | Delete |
| `BrokerInstrumentService` | `brokers/common/instruments/service.py` | 2 | 2 | Keep (polymorphic) |
| `IReconciliationService` | `application/oms/protocols.py` | 2 | 2 | **Keep** (genuine polymorphism) |
| `MarginProvider` | `brokers/common/oms/margin_provider.py` | 2 | 2 | **Keep** (genuine polymorphism) |

**18 single-implementation interfaces = ~800 lines of dead abstraction.**

### Factories with One Product

| Factory | Location | Product | Verdict |
|---------|----------|---------|---------|
| `AnalyticsEngineFactory` | `analytics/engine_factory.py` | 14 cached engines | Replace with `functools.cached_property` |
| `AsyncEventBusFactory` | `infrastructure/event_bus/factory.py` | EventBus | Delete — just `EventBus()` |
| `create_execution_adapter` | `application/execution/` | SimulatedOMSAdapter | Delete (deprecated) |

### Wrappers That Just Forward Calls

| Wrapper | Target | Logic Added | Verdict |
|---------|--------|-------------|---------|
| `domain/services/` (5 classes) | `ports/protocols.DataProvider` | None | Delete — inline |
| `Analytics facade` | `DataFetcher` + `AnalysisMethods` | Logging | Flatten |
| `MarketDataComposer` | `coordinator` | Logging only | Delete |
| `datalake/adapters/analytics_provider.py` | `DataLakeGateway` | Exchange param | Inline |
| `brokers/services/` (9 files) | `BrokerSession` | try/finally | Single context manager |

---

## 3. Indirection Chain Analysis

### Chain 1: Analytics Facade (4 layers)
```
Analytics (facade.py:420 lines)
  → AnalyticsDataFetcher (data_fetcher.py:288 lines)
    → AnalyticsAnalysisMethods (analysis_methods.py:70 lines)
      → AnalyticsEngineFactory (engine_factory.py:174 lines)
        → actual engines
```
**Depth: 5 layers.** Business logic lives at layer 5. Layers 1-4 are delegation + caching + logging.
**Recommendation:** Flatten to `Analytics` → engines via `cached_property`.

### Chain 2: Application OMS (4 layers)
```
TradingContext (god-constructor: 175 lines in __init__)
  → OrderManager
    → OrderValidator
      → RiskManager
```
**Depth: 4 layers.** `OrderValidator` (178 lines) duplicates work already inside `OrderManager.place_order`.
**Recommendation:** Merge `OrderValidator` into `OrderManager`.

### Chain 3: Broker Services (3 layers)
```
interface/api/routers/orders.py
  → brokers/services/core.py (re-export barrel)
    → brokers/services/orders.py (_borrow_session pattern)
      → BrokerSession methods
```
**Depth: 4 layers.** Every service function repeats the same `_borrow_session` / `try` / `finally close` pattern.
**Recommendation:** Extract `_with_broker(broker, fn)` context manager, eliminate 200 lines.

### Chain 4: Datalake → Analytics (4 layers)
```
datalake/gateway.py
  → datalake/adapters/analytics_provider.py
    → analytics/data_fetcher.py
      → analytics/engine_factory.py
        → engines
```
**Depth: 5 layers.** Two thin pass-through adapters in the chain.

---

## 4. Duplicate Responsibility Report

| Duplicated Logic | Location 1 | Location 2 | Location 3 | Verdict |
|------------------|-----------|-----------|-----------|---------|
| Exponential backoff | `infrastructure/resilience/backoff.py` | `brokers/common/backoff.py` | `brokers/common/transport_policy.py` | Keep `infrastructure/`, delete 2 |
| `snap_to_tick` | `domain/value_objects/price.py` (function) | `domain/conventions.py:MarketSurface` (method) | `domain/value_objects/money.py:TickSize.snap` (method) | Keep `price.py`, delete 2 |
| Scanner scoring | `analytics/scanner/scorer.py` | `analytics/scanner/scanners.py` (inline) | `analytics/scanner/rules/engine.py` | Keep 1, delete 2 |
| Session recording | `tradex/session_recorder.py` | `infrastructure/observability/session_recorder.py` | — | Delete `tradex/` shim |
| Broker extension collection | `tradex/gateway_extensions.py` | `interface/ui/services/broker_facade.py` | — | Delete `tradex/` |
| `EventMetrics` bookkeeping | `infrastructure/observability/event_metrics.py` (own dict) | `infrastructure/metrics/registry.py` | — | Unify |
| Gap fill strategy | `application/composer/gap_reconciler.py` (204 lines) | `application/composer/factory.py:_build_default_backfill_callback` (62 lines) | — | Keep 1 |
| Order conversion paths | `application/composer/execution.py` (3 converters) | `application/oms/session_bridge.py` (1 converter) | `brokers/*/execution/order_from_response` | Consolidate |
| Config validation | `config/schema.py` (Pydantic) | `config/validator.py` (hand-rolled) | — | Keep Pydantic, delete validator |
| Tick validation | `brokers/common/tick_validation.py` | `brokers/dhan/websocket/market_feed.py` (inline) | — | Move to common |

---

## 5. Dead Extension Point Report

| Extension Point | Location | # Extensions | Used? | Verdict |
|----------------|----------|-------------|-------|---------|
| `domain/extensions/super_order.py` | ABC | 1 (Dhan only) | Yes | Inline as Dhan-specific |
| `domain/extensions/forever_order.py` | ABC | 1 (Dhan only) | Yes | Inline |
| `domain/extensions/news.py` | ABC | 1 | Yes | Inline |
| `domain/extensions/fundamentals.py` | ABC | 1 | Yes | Inline |
| `domain/extensions/native_slice_order.py` | ABC | 1 | Yes | Inline |
| `domain/extensions/order_capability.py` | ABC | 1 | Yes | Inline |
| `domain/extensions/broker_plugin_interface.py` | ABC | 1 | Yes | Inline |
| `analytics/strategy/registry.py` | Plugin discovery | 2-3 built-in | Marginal | Delete registry, keep strategies |
| `analytics/scanner/rules/` | Rule engine | Overlaps with scanners | Partial | Delete one path |
| `plugins/exchanges/nse/` | Exchange adapter | 1 exchange | Yes | Keep, but note NSE is only exchange |
| `config/feature_flags.py` | Feature flag system | 5 flags | **None checked** | Delete entire system |
| `config/profiles/` | Profile ABC | 3 layers | **Never instantiated** | Delete |
| `datalake/mcp/` | MCP server | 1 | **No integration evidence** | Speculative — flag for removal |

**12 dead extension points, ~1,800 lines.**

---

## 6. Test Suite Rationalization Report

### Test Structure Overview

| Category | Files | Lines | Purpose |
|----------|------:|------:|---------|
| Architecture tests | 66 | ~4,000 | Import boundary / layering contracts |
| Chaos tests | 14 | ~1,500 | Failure injection |
| E2E tests | 33 | ~5,000 | Full pipeline |
| Integration tests | 161 | ~25,000 | Component wiring |
| Component tests | 95 | ~15,000 | Unit-level |
| Other (unit, conftest, fixtures) | 596 | ~94,000 | Various |

### Findings

| Finding | Recommendation | Lines Saved |
|---------|---------------|-------------|
| 66 architecture tests that are structurally identical (import boundary checks) | Parametrize into 1 test with 66 cases | ~3,500 |
| `tests/fixtures/test_fake_broker_gateway.py` (tests the fixture) | Delete — fixture-of-fixture testing | ~100 |
| 5 e2e/stability tests overlapping event_bus behavior | Consolidate | ~300 |
| 8 root-level test runner scripts (`run_all_tests.py`, `run_test.sh`, etc.) | Keep 1, delete 7 | ~60 |
| `test.ipynb` + `test copy.ipynb` | Delete both | ~4,500 lines of notebook |
| `test1_result.txt` + `test2_result.txt` | Delete | ~1,180 |

### Test Business Value Assessment

| Category | Business Value | Maintenance Cost | Recommendation |
|----------|---------------|-----------------|----------------|
| Architecture/import tests | Medium (prevents layering violations) | Low (automated) | **Keep** but parametrize |
| Chaos tests | High (validates resilience) | Medium | **Keep** |
| E2E tests | High (validates full pipeline) | High (fragile) | **Keep** — trim flaky ones |
| Integration tests | High (validates wiring) | Medium | **Keep** |
| Component tests | High (validates domain logic) | Low | **Keep** |

---

## 7. Dependency Injection Complexity Report

### DI Container Analysis (`infrastructure/di.py` — 263 lines)

| Feature | Lines | Used? | Verdict |
|---------|------:|-------|---------|
| Singleton scope | ~40 | Yes (all registrations) | Keep |
| Transient scope | ~30 | **No registrations** | Delete |
| Request scope | ~141 (`di_scopes.py`) | **No registrations** | Delete |
| Circular detection | ~30 | Yes | Keep |
| Container class | ~20 | Yes | Keep |

**DI total: 263 lines. Effective usage: ~90 lines. ~170 lines removable (65%).**

### Unnecessary DI Registrations

The DI container is accessed only from `infrastructure/deps.py` (API layer). Domain and application layers don't use DI — they use direct imports. The DI system adds indirection for the API layer only.

### Wrapper Registrations

- `AsyncEventBusFactory` — creates EventBus ignoring its own parameters
- `ConnectionPoolManager` — singleton pattern duplicating what DI already provides
- `SecretManager` — wraps stdlib keyring with encryption

---

## 8. Domain Purity Assessment

### Infrastructure Leakage into Domain

| Leak | Location | Impact |
|------|----------|--------|
| `domain/ports/broker_gateway.py` imports `BrokerStreamHandle`, `BrokerHealthSnapshot` | Transport types in domain ports | Domain knows about transport details |
| `domain/instrument_resolver.py` (240 lines) | Strategy DSL parser at domain root | Application concern in domain |
| `domain/provenance.py` | `TimestampSemantics` with 3 datetime fields | Over-engineered metadata |
| `analytics/shared/trade_types.py` | Domain types in analytics package | Types belong in `domain/` |

### Domain Logic Scattered in Infrastructure

| Concern | In Domain? | Also In Infrastructure? | Also In Application? |
|---------|-----------|------------------------|---------------------|
| Tick validation | `domain/value_objects/price.py` | — | `brokers/common/tick_validation.py` |
| Reconciliation | `domain/reconciliation.py` + `reconciliation_engine.py` | — | `application/oms/reconciliation/` |
| Backoff / retry | — | `infrastructure/resilience/backoff.py` | — (correctly isolated) |
| Event bus | — | `infrastructure/event_bus/` | `application/audit.py` (event logging) |

---

## 9. Component Classification Matrix

### Essential — Core Business Capability (keep all)

| Component | Lines | Justification |
|-----------|------:|---------------|
| `domain/entities/` | ~2,000 | Core domain objects |
| `domain/orders/` | ~1,500 | Order lifecycle |
| `domain/portfolio/` | ~1,000 | Portfolio tracking |
| `domain/value_objects/` | ~800 | Price, Money, TickSize |
| `domain/events/` | ~600 | Domain events |
| `domain/session.py` | ~400 | Session management |
| `application/oms/context/` | ~1,200 | Trading context + wiring |
| `application/oms/order_manager.py` | ~800 | Order management |
| `application/trading/` | ~2,000 | Trading orchestration |
| `brokers/dhan/` | ~15,000 | Primary broker integration |
| `brokers/upstox/` | ~12,000 | Secondary broker integration |
| `analytics/indicators/` | ~2,000 | Technical indicators |
| `analytics/core/` | ~1,500 | Analytics engine core |

### Supporting — Enables Core Behavior (keep, note justification)

| Component | Lines | Justification |
|-----------|------:|---------------|
| `infrastructure/event_bus/` | ~1,200 | Event infrastructure |
| `infrastructure/db/` | ~500 | DuckDB persistence |
| `infrastructure/resilience/` | ~800 | Retry, circuit breaker |
| `datalake/core/` | ~2,000 | Data management |
| `datalake/ingestion/` | ~1,500 | Data ingestion |
| `interface/api/` | ~3,000 | REST API |

### Optional — Could Be Simplified

| Component | Lines | Issue |
|-----------|------:|-------|
| `analytics/views/` | ~2,500 | Mini-framework for static SQL views |
| `application/services/production_readiness.py` | ~431 | 32-method checklist, could be data-driven |
| `brokers/services/` | ~1,200 | Repetitive try/finally pattern |
| `infrastructure/lifecycle/` | ~341 | Thread-per-stop pattern |
| `infrastructure/connection/` | ~700 | Broker-specific probes |
| `datalake/quality/` | ~1,000 | Data quality checks (verify usage) |

### Legacy — Retained for Historical Reasons (delete candidates)

| Component | Lines | Reason to Delete |
|-----------|------:|------------------|
| `domain/capability_manifest/` | 1,230 | Self-described as "architecture debt" |
| `domain/extensions/` (7 files) | 483 | Single-impl ABCs, should be inline |
| `domain/services/` | 350 | Pass-through wrappers |
| `domain/ports/` (redundant) | 350 | Superseded ports retained |
| `domain/providers/` | 129 | Zero consumers |
| `infrastructure/async_compat.py` | ~30 | Re-export shim |
| `infrastructure/broker_infrastructure.py` | ~20 | Re-export shim |
| 13 re-export shims across layers | ~200 | Old import paths |

### Redundant — Duplicates Existing Capability

| Component | Lines | Duplicates |
|-----------|------:|-----------|
| `brokers/common/backoff.py` | 26 | `infrastructure/resilience/backoff.py` |
| `brokers/common/streaming.py` | 45 | Broker-local implementations |
| `brokers/common/acl.py` | 42 | Inline in broker |
| `application/composer/gap_reconciler.py` | 204 | `factory.py` backfill |
| `analytics/scanner/scorer.py` | ~100 | Inline in scanners |
| `analytics/paper/` | 1,200 | `analytics/replay/` |
| `analytics/backtest/` | 1,200 | `analytics/replay/` |

### Dead — No Observable Runtime Value

| Component | Lines | Evidence |
|-----------|------:|----------|
| `infrastructure/observability/production_hooks.py` | 384 | Zero imports |
| `infrastructure/observability/_catalog.py` | 173 | Documentation as code |
| `infrastructure/resilience/error_codes.py` | 56 | Constants never imported |
| `application/observability.py:trace_operation` | 40 | No-op decorator, 28 call sites |
| `application/execution/trading_cache.py` | 70 | Zero consumers |
| `datalake/storage/interfaces.py` | 84 | 3 ABCs, zero implementations |
| `datalake/scanner_proxy.py` | 38 | Zero callers |
| `domain/error_messages.py` | 25 | Zero imports |
| `domain/simulation_position_meta.py` | 23 | Zero consumers |
| `domain/scanners/` | 57 | Zero consumers |
| `config/feature_flags.py` | 480 | Zero flag checks |
| `config/profiles/` | 183 | Never instantiated |
| 7 root-level test scripts | ~66 | All duplicates |
| 2 Jupyter notebooks | ~4,500 | Dead |
| 2 test output files | ~1,180 | Dead |

### Speculative — Built for Hypothetical Future

| Component | Lines | Evidence |
|-----------|------:|----------|
| `datalake/mcp/` | 220 | No integration with other modules |
| `plugins/exchanges/nse/` | 179 | Single exchange adapter |
| `interface/ui/utils/retry_handler.py` | 119 | Zero imports |
| `interface/ui/utils/timeout_handler.py` | 74 | Zero imports |
| `interface/ui/utils/error_formatter.py` | 87 | Zero imports |
| `tradex/gateway_extensions.py` | 66 | Duplicated elsewhere |
| `runtime/trading_runtime_factory.py` | 24 | Self-described as deprecated |

---

## 10. Complexity Hotspots (Ranked by Maintenance Cost)

| Rank | Component | Lines | Cost Type | Annual Maintenance Estimate |
|------|-----------|------:|-----------|---------------------------|
| 1 | `brokers/dhan/` + `brokers/upstox/` | 27,000 | High (2 parallel broker impls) | High |
| 2 | `analytics/replay/` + `paper/` + `backtest/` | 5,400 | High (triple simulation) | High |
| 3 | `analytics/views/` mini-framework | 2,500 | Medium (custom caching/materialization) | Medium |
| 4 | `infrastructure/` root files (23 files) | 16,793 | Medium (many small abstractions) | Medium |
| 5 | `application/oms/` (8+ submodules) | ~4,000 | Medium (god-object pattern) | Medium |
| 6 | `domain/ports/` (10+ files) | ~800 | Low (mostly static) | Low |
| 7 | `domain/capability_manifest/` | 1,230 | Low (dead code, but confuses navigation) | Low |
| 8 | `config/` overlap (schema + validator) | ~500 | Low (dual validation) | Low |
| 9 | `brokers/common/` (15+ files) | ~2,000 | Medium (stale abstractions) | Medium |
| 10 | `tests/` (965 files) | 144,789 | Medium (test maintenance burden) | High |

---

## 11. Simplification Roadmap

### Phase 0: Zero-Risk Cleanup (Day 1) — Save ~15,000 lines + 199 MB

**No behavior change. Pure deletion.**

| Step | Action | Components | Lines | Risk |
|------|--------|-----------|------:|------|
| 0.1 | Delete dead root files | 7 test scripts, 2 notebooks, 2 output files, x.py | ~6,380 | None |
| 0.2 | Delete dead runtime-dev/ | `runtime-dev/` (199 MB CSV dumps) | 0 lines | None |
| 0.3 | Delete dead domain files | `error_messages.py`, `simulation_position_meta.py`, `scanners/`, `sessions/trading_session.py` | ~164 | None |
| 0.4 | Delete dead infrastructure | `production_hooks.py`, `error_codes.py`, `_catalog.py` | ~613 | None |
| 0.5 | Delete dead interface utils | `retry_handler.py`, `timeout_handler.py`, `error_formatter.py` | ~280 | None |
| 0.6 | Delete dead datalake files | `storage/interfaces.py`, `scanner_proxy.py` | ~122 | None |
| 0.7 | Delete dead application files | `trading_cache.py`, deprecated re-export shims | ~85 | None |
| 0.8 | Delete feature_flags.py + profiles/ | Config scaffold with zero consumers | ~663 | None |
| 0.9 | Delete ARCHITECTURAL_AUDIT.md | Stale document | 0 lines | None |
| **Subtotal** | | | **~8,307** | **None** |

**Verification:** Run full test suite. Zero tests should fail.

### Phase 1: Re-export Shim Elimination (Day 1-2) — Save ~400 lines

| Step | Action | Components | Lines | Risk |
|------|--------|-----------|------:|------|
| 1.1 | Delete 15 re-export shims, update imports | `async_compat.py`, `broker_infrastructure.py`, `env_loader.py`, `environment_bootstrap.py`, `connection/errors.py`, `retry.py`, `duckdb_pool.py`, `broker_capabilities.py`, `models/__init__.py`, `types.py`, `futures/__init__.py`, `broker_registry.py`, `broker_facade.py`, `auth/__init__.py` | ~400 | Low |

**Verification:** Run import linter + full test suite. All imports resolve.

### Phase 2: Single-Implementation Interface Deletion (Day 2-3) — Save ~1,500 lines

| Step | Action | Components | Lines | Risk |
|------|--------|-----------|------:|------|
| 2.1 | Delete 7 unused protocols from `protocols.py` | Keep only `IReconciliationService` | ~180 | Low |
| 2.2 | Delete `RiskCheckPort` from order_validator.py | Inline the one call | ~5 | Low |
| 2.3 | Delete redundant domain ports | `broker_adapter.py`, `market_data.py`, `session_opener.py`, `correlation.py`, `broker_id.py` | ~160 | Low |
| 2.4 | Delete `providers/registry.py` | Zero consumers | ~129 | Low |
| 2.5 | Delete `ExecutionModeAdapter` ABC + `SimulatedOMSAdapter` | Deprecated | ~70 | Medium |
| 2.6 | Delete `di_scopes.py` request scope | Zero registrations | ~141 | Low |
| 2.7 | Simplify DI container | Remove transient scope | ~30 | Low |
| 2.8 | Delete 7 domain extension ABCs, inline as broker-specific | `extensions/super_order.py` etc. | ~483 | Medium |

**Verification:** Type checker + full test suite. Confirm no structural typing usage of deleted protocols.

### Phase 3: Indirection Chain Flattening (Day 3-5) — Save ~2,500 lines

| Step | Action | Components | Lines | Risk |
|------|--------|-----------|------:|------|
| 3.1 | Flatten Analytics facade | Delete `facade.py` + `analysis_methods.py`, expose engines via `cached_property` | ~550 | Medium |
| 3.2 | Delete domain pass-through services | `domain/services/` (5 classes) | ~350 | Medium |
| 3.3 | Merge OrderValidator into OrderManager | Eliminate validator duplication | ~178 | Medium |
| 3.4 | Extract generic broker service wrapper | Replace 9 try/finally files | ~200 | Medium |
| 3.5 | Delete `MarketDataComposer` pass-through | Direct coordinator calls | ~236 | Low |
| 3.6 | Delete no-op `trace_operation` decorator + 28 sites | Zero runtime value | ~120 | Low |
| 3.7 | Delete `capability_manifest/` | Self-described debt | ~1,230 | Low |

**Verification:** Full integration test suite. Verify all API endpoints still respond correctly.

### Phase 4: Duplicate Responsibility Elimination (Day 5-7) — Save ~1,500 lines

| Step | Action | Components | Lines | Risk |
|------|--------|-----------|------:|------|
| 4.1 | Consolidate exponential backoff | Keep `infrastructure/resilience/backoff.py`, delete 2 copies | ~70 | Low |
| 4.2 | Consolidate `snap_to_tick` | Keep `value_objects/price.py`, delete from `conventions.py` + `money.py` | ~120 | Low |
| 4.3 | Merge hand-rolled Prometheus with `prometheus_client` | `metrics/types.py` + `registry.py` + `prometheus.py` | ~500 | Medium |
| 4.4 | Unify `EventMetrics` double bookkeeping | Remove redundant dict in `event_metrics.py` | ~80 | Low |
| 4.5 | Merge `schema.py` + `validator.py` | Keep Pydantic, delete hand-rolled validator | ~200 | Low |
| 4.6 | Consolidate scanner scoring | Keep inline in scanners, delete `scorer.py` + `rules/` | ~300 | Medium |
| 4.7 | Delete `gap_reconciler.py`, use factory backfill | Duplicate gap-fill strategy | ~200 | Medium |

**Verification:** Run full test suite + manual smoke test of order flow.

### Phase 5: Triple Simulation Consolidation (Day 7-14) — Save ~2,400 lines

| Step | Action | Components | Lines | Risk |
|------|--------|-----------|------:|------|
| 5.1 | Designate `analytics/replay/` as canonical simulation engine | Document decision | 0 | None |
| 5.2 | Redirect `paper/` to use `replay/` engine | Refactor paper trading to delegate | ~600 | High |
| 5.3 | Redirect `backtest/` to use `replay/` engine | Refactor backtest to delegate | ~600 | High |
| 5.4 | Delete `analytics/scoring/__init__.py` re-export | Unused | ~17 | None |
| 5.5 | Flatten `views/` framework | Replace 5-class hierarchy with direct SQL execution | ~1,800 | High |

**Verification:** Full backtest replay, paper trading session, and view materialization tests.

### Phase 6: Analytics Framework Simplification (Day 14-21) — Save ~1,200 lines

| Step | Action | Components | Lines | Risk |
|------|--------|-----------|------:|------|
| 6.1 | Flatten `AnalyticsDataFetcher` + `AnalyticsAnalysisMethods` | Merge into Analytics class | ~200 | Medium |
| 6.2 | Replace `AnalyticsEngineFactory` with `cached_property` | 174 lines → ~20 lines | ~154 | Low |
| 6.3 | Move `analytics/shared/trade_types.py` to `domain/` | Domain types in wrong package | ~50 | Low |
| 6.4 | Delete strategy registry, keep strategies | Plugin system for 2-3 strategies | ~120 | Low |
| 6.5 | Delete `datalake/normalize.py` migration script | One-shot migration | ~228 | Low |
| 6.6 | Delete `datalake/adapters/analytics_provider.py` pass-through | Inline exchange param | ~168 | Medium |
| 6.7 | Simplify `production_readiness.py` | 32 methods → data-driven checklist | ~200 | Medium |

**Verification:** Full analytics test suite + dashboard smoke test.

### Phase 7: Test Suite Rationalization (Day 21-28) — Save ~4,000 lines + maintenance cost

| Step | Action | Components | Lines | Risk |
|------|--------|-----------|------:|------|
| 7.1 | Parametrize 66 architecture tests into 1 file | `tests/architecture/` | ~3,500 | Low |
| 7.2 | Delete fixture-of-fixture test | `test_fake_broker_gateway.py` | ~100 | None |
| 7.3 | Consolidate e2e/stability tests | 5 overlapping tests → 2 | ~300 | Low |

**Verification:** Full test suite passes. Coverage percentage maintained.

---

## Cumulative Impact

| Phase | Lines Saved | Risk | Duration |
|-------|------------|------|----------|
| Phase 0: Dead code | ~8,307 | None | Day 1 |
| Phase 1: Re-export shims | ~400 | Low | Day 1-2 |
| Phase 2: Single-impl interfaces | ~1,500 | Low-Medium | Day 2-3 |
| Phase 3: Indirection flattening | ~2,500 | Medium | Day 3-5 |
| Phase 4: Duplicate elimination | ~1,500 | Low-Medium | Day 5-7 |
| Phase 5: Simulation consolidation | ~2,400 | High | Day 7-14 |
| Phase 6: Analytics simplification | ~1,200 | Medium | Day 14-21 |
| Phase 7: Test rationalization | ~4,000 | Low | Day 21-28 |
| **Total** | **~21,807** | | **28 days** |

### Before / After

| Metric | Before | After | Reduction |
|--------|-------:|------:|-----------|
| Source lines | 158,211 | ~136,400 | -14% |
| Dead data | 199 MB | 0 | -100% |
| Source files | 1,151 | ~1,050 | -9% |
| Single-impl interfaces | 18 | 1 | -94% |
| Re-export shims | ~15 | 0 | -100% |
| Indirection chain depth (max) | 5 layers | 2 layers | -60% |
| Simulation engines | 3 | 1 | -67% |
| Root-level junk files | 13 | 0 | -100% |

---

## Answers to Success Criteria

### What is the smallest architecture that still satisfies all TradeXV2 requirements?

**Three layers, not five:**
1. **Domain** (~16,000 lines) — entities, events, value objects, enums, session, ports (minimal)
2. **Application + Infrastructure merged** (~28,000 lines) — OMS, execution, analytics, brokers, event bus, DB, resilience
3. **Interface** (~3,000 lines) — API + UI

The `datalake/` and `analytics/` merge naturally into application. The `config/` and `tradex/` become thin modules within infrastructure. The current 7-package structure (`domain`, `application`, `infrastructure`, `analytics`, `brokers`, `datalake`, `config`) can collapse to 3 without losing capability.

### Which abstractions genuinely provide long-term value?

- **`IReconciliationService`** — enables Dhan/Upstox polymorphism
- **`BrokerSession`** — unified broker interface
- **Event bus** — decoupled domain events
- **Domain entities and value objects** — core business language
- **Resilience layer** (retry, circuit breaker) — infrastructure concern with clear boundary

### Which components are accidental complexity?

- **All 18 single-implementation interfaces** in `protocols.py` and `ports/`
- **15 re-export shims** maintaining dead import paths
- **The `capability_manifest/` package** (self-described as debt)
- **The entire feature flags system** (zero consumers)
- **The profiles ABC hierarchy** (never instantiated)
- **The hand-rolled Prometheus client** (stdlib replacement exists)
- **The views mini-framework** (for static SQL)
- **The Analytics facade double indirection** (4 layers for delegation)
- **The `trace_operation` no-op decorator** (28 decorated call sites doing nothing)

### Which tests protect the business versus the implementation?

**Protect the business (keep):**
- Integration tests for order flow, position tracking, P&L
- E2E tests for full pipeline execution
- Chaos tests for resilience validation
- Component tests for domain logic

**Protect the implementation (consolidate or remove):**
- 66 architecture import-linter tests → 1 parametrized test
- Fixture-of-fixture tests → delete
- Overlapping stability tests → consolidate

### How can the codebase become significantly smaller while preserving behaviour?

Execute the 7-phase roadmap above. Phase 0 alone removes 8,307 lines with zero risk. By Phase 4, the codebase is ~15% smaller and dramatically simpler to navigate. Phases 5-7 require more careful refactoring but eliminate the biggest structural complexity (triple simulation, views framework, test sprawl).

**The end state: a codebase where every file is reachable from a clear business requirement, every abstraction has at least two implementations or a documented extension plan, and no indirection chain exceeds 2 layers.**
