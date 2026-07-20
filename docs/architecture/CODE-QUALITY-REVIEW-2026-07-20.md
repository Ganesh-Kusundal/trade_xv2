# Code Quality Review — TradeXV2

**Date:** 2026-07-20  
**Scope:** `src/` (1,077 Python files, ~151k LOC)  
**Method:** `radon` CC/MI, `vulture` dead-code scan, `graphify` hub analysis, layer-scoped static review, targeted grep/AST  
**Authority cross-check:** [`docs/constitution/07-gap-analysis.md`](../constitution/07-gap-analysis.md) — overlaps cited as **G-P#-#**, not restated as new findings.

**Recent cleanup context:** Ponytail Waves 1–3 and REF-1..7 (2026-07-20) removed ~1,100+ lines of dead infra, CQRS packages, feature flags, and duplicate adapters. This review reflects **post-cleanup** state; several historical smells are already closed.

---

## Executive Summary

| Severity | Count | Theme |
|---|---|---|
| **Critical** | 4 | Kill-switch policy gap, HTTP transport duplication, EventBus god-class, broken DuckDB escape hatch |
| **High** | 22 | God classes/hubs, spine bypasses, triple composition roots, quality-path under-engineering |
| **Medium** | 28 | DRY violations, primitive obsession, shotgun surgery, over-engineering in views/scanner |
| **Low** | 12 | Dead imports, naming collisions, backward-compat shims |

**Top 10 fix-first (ranked by real-money / parity risk):**

1. Kill-switch missing on `cancel_order` — `order_lifecycle.py`
2. `DataLakeMarketDataProvider.query()` uses `:memory:` — silent empty/wrong results
3. Dhan dual rate limiting (`_throttle` + token bucket) — order stall risk
4. Unify placement through `place_order_spine` — `OrderPlacer` bypass
5. AsyncEventBus documented but not wired in API bootstrap — config/behavior drift
6. Capital-event classification split — async can drop ORDER events sync fsyncs
7. Extract shared broker HTTP transport — 3 parallel retry stacks
8. Unify triple composition roots (CLI/API/SDK) — `runtime.factory.build` only
9. `validate_parquet_file` / `completeness_pct` quality bugs — false health signals
10. Split `EventBus` (599 LOC, degree 231) — persistence/idempotency/alerting entangled

---

## Automated Metrics

### Cyclomatic Complexity (radon, rank D/E/F)

**61 functions** at rank D or worse. Worst offenders:

| Rank | CC | Location | Function |
|---|---|---|---|
| F | 66 | `src/tradex/session.py:62` | `open_session` |
| F | 62 | `src/interface/ui/main.py:133` | `main` |
| F | 47 | `src/brokers/dhan/symbol_validator.py:233` | `_validate_fo` |
| F | 44 | `src/datalake/quality/validation.py:48` | `validate_candles` |
| E | 40 | `src/analytics/replay/engine/bar_loop.py:44` | `run_single` |
| E | 39 | `src/analytics/replay/engine/bar_loop.py:236` | `run_multi_symbol` |
| E | 37 | `src/application/oms/_internal/risk_manager.py:212` | `check_order` |
| E | 36 | `src/brokers/dhan/api/http_client.py:428` | `_request` |

### Maintainability Index (radon)

No modules below MI 40. Large files remain structurally maintainable at file level; complexity is concentrated in **methods and coupling**, not raw LOC.

### Dead Code (vulture, confidence ≥ 80%)

**49 hits** (many false positives in generated protobuf). Actionable:

| File | Finding |
|---|---|
| `application/oms/_internal/kill_switch.py`, `risk_manager.py`, `risk_types.py` | Unused `DomainKillSwitch` / `DomainRiskResult` imports |
| `brokers/upstox/adapters/streaming_gateway.py:217` | Unreachable code after `return` |
| `brokers/upstox/mappers/domain_mapper.py:58` | Unused `_leg_greeks` import |
| `infrastructure/observability/audit.py:359` | Unused `ALERTING_RULES`, `FAILURE_TAXONOMY`, `METRICS_CATALOG` |
| `interface/api/routers/orders.py:20` | Unused `DomainOrderRequest` import |
| `tradex/session.py:54` | Unused `_session_recording_enabled` import |

### Graphify Hub Analysis

| Node | Degree | Role |
|---|---|---|
| `EventBus` | 231 | Infrastructure god-hub; brokers, OMS, replay, API all publish |
| `BrokerService` | 214 | Interface god-hub; bootstrap, OMS, orders, doctor |
| `OrderManager` | 212 | Application god-hub; risk, lifecycle, audit, idempotency |
| `FeaturePipeline` | 291 | Analytics computation hub (healthy size ~96 LOC; high fan-out) |
| `TradingOrchestrator` | 49 | Strategy→execution coordinator |

**Cyclic dependencies:** `graphify diagnose multigraph` reports 0 same-endpoint collapsed edges; no explicit import cycles detected at graph level. **Tight coupling** manifests as high-degree hubs and parallel wiring paths, not circular imports.

---

## Findings by Category

### 1. Code Smells

| ID | Severity | Files | Evidence | Recommendation |
|---|---|---|---|---|
| SM-01 | High | `src/application/oms/_internal/risk_manager.py` | `check_order` ~140 LOC, CC=37; 8+ concerns in one method | Extract ordered check pipeline; `check_order` orchestrates only |
| SM-02 | High | `src/application/oms/session_bridge.py` | `_execution_result_to_order` ~75 LOC duck-typing normalizer | Single broker-response adapter; bridge delegates |
| SM-03 | High | `src/infrastructure/gateway/factory.py` | `bootstrap_gateway()` ~175 LOC, 4 overlapping skip flags | `AuthProbePolicy` + staged pipeline |
| SM-04 | Medium | `src/application/execution/execution_engine.py` | `apply_mass_status` ~115 LOC with repeated getattr/heal | Split compare vs heal; reuse domain reconciliation |
| SM-05 | Medium | `src/infrastructure/resilience/retry_executor.py` | Duplicated retry loops; `NonRetryableError` passes stale exception (L133) | Unify `_attempt_once`; inject clock/backoff |
| SM-06 | Medium | `src/brokers/dhan/websocket/market_feed.py` | 50+ methods; 50+ property passthroughs to `_conn`/`_sub` | Finish facade extraction (<200 LOC target) |
| SM-07 | Low | `src/application/trading/order_placer.py` | `execution_engine` ctor param stored but never used | Remove or wire through spine |

### 2. God Classes / God Services

| ID | Severity | Files | Evidence | Recommendation |
|---|---|---|---|---|
| GC-01 | **Critical** | `src/infrastructure/event_bus/event_bus.py` | 599 LOC, 504L class, 24 methods, degree 231; owns publish, idempotency, persistence, DLQ, alerting thread | Split into composable collaborators; alerting via lifecycle only |
| GC-02 | High | `src/interface/ui/services/broker_service.py` | 539 LOC, 37 methods, degree 214; bootstrap + OMS + orders + readiness | Thin facade over `OmsBootstrap`, `MarketDataBootstrap`, `CliBrokerFacade` |
| GC-03 | High | `src/application/oms/order_manager.py` | 506 LOC, 397L class, 26 methods, degree 212; wires 8+ collaborators | Narrow public surface; expose ports not concrete managers |
| GC-04 | High | `src/application/oms/context/__init__.py` | `TradingContext` 446 LOC + mixins; bus, reconciliation, equity, replay, health | Move equity/PnL/replay to dedicated services |
| GC-05 | High | `src/brokers/dhan/streaming/connection.py` | 618 LOC, 54 methods; 15+ adapter registries, WS factories | Follow Upstox `_build_raw_clients` bundle pattern |
| GC-06 | High | `src/brokers/dhan/wire.py` vs `upstox/wire.py` | 544L vs 271L for same port; Dhan monolithic, Upstox delegated | Extract Dhan gateways mirroring Upstox layout |
| GC-07 | High | `src/datalake/gateway.py` | 497 LOC, 32 methods; history, batch, LTP, options, resampling | Split read paths behind narrow ports |
| GC-08 | Medium | `src/brokers/paper/paper_gateway.py` | 593 LOC, 40+ methods; 100-line inline `capabilities()` literal | Split `PaperCapabilities`; move stream stubs |
| GC-09 | Medium | `src/application/data/historical_coordinator.py` | 529 LOC; plan/fetch/fallback/merge/gap-fill in one class | Extract fetch vs merge orchestration |
| GC-10 | Medium | `src/analytics/facade.py` | 419 LOC, 38 methods | Domain-specific facades (`AnalyticsReplay`, `AnalyticsScanner`) |
| GC-11 | Medium | `src/datalake/ingestion/loader.py` | 501 LOC | Extract `ParquetMergeWriter`; loader orchestrates only |
| GC-12 | Medium | `src/analytics/replay/models.py` | 502 LOC, 15+ dataclasses in one module | Split config/session/runtime models |
| GC-13 | Medium | `src/infrastructure/event_bus/processed_trade_repository.py` | 437 LOC; singleton + hot/durable dedup + cleanup thread | Inject port; drop module singleton |
| GC-14 | Medium | `src/infrastructure/observability/alerting.py` | 598 LOC; rarely wired in production bootstrap | Wire at bootstrap or demote to optional module |

### 3. Large Methods

See **Automated Metrics** table. Additional layer-specific hotspots:

| File | Method | CC | Lines | Recommendation |
|---|---|---|---|---|
| `dhan/api/http_client.py` | `_request` | 36 | ~180 | Extract to shared `ResilientHttpTransport` |
| `upstox/auth/http.py` | `_execute_request` | 28 | ~125 | Same |
| `dhan/api/async_http_client.py` | `_request` | 34 | ~120 | Thin async wrapper over shared transport |
| `interface/ui/commands/market.py` | `show_option_chain` | C | ~140 | Extract rendering to `renderers.py` |
| `analytics/backtest/fast_backtest.py` | `_compute_metrics` | 26 | ~80 | Share with replay metrics path |

### 4. Dead Code

| ID | Severity | Files | Evidence | Recommendation |
|---|---|---|---|---|
| DC-01 | Medium | `dhan/resilience/retry_policies.py`, `upstox/auth/context.py` | `DhanRetryExecutorFactory` / `make_retry_executor` only used in tests; production HTTP uses inline retry | Wire factories or delete |
| DC-02 | Low | See vulture table above | 49 vulture hits | Triage imports; fix unreachable code in `streaming_gateway.py` |
| DC-03 | Low | `application/oms/context/__init__.py`, `session_bridge.py` | `run_reconciliation` shims, `build_paper_oms_service` alias | Deprecation ratchet |

**Already removed (Ponytail Waves 1–3):** FeatureFlags, CompositeDataProvider, CQRS packages, `broker_facade.py`, `event_bus_service.py`, `order_repository_adapter.py`, `execution_mode_adapter.py`, `api_readiness.py`, `data_validator.py`, and more — see `context/progress-tracker.md`.

### 5. Duplicate Code

| ID | Severity | Files | Evidence | Recommendation |
|---|---|---|---|---|
| DP-01 | **Critical** | `dhan/api/http_client.py`, `dhan/api/async_http_client.py`, `upstox/auth/http.py` | Three full HTTP stacks: CB routing, rate buckets, 401 refresh, 429 retry; only shared node is `MultiBucketRateLimiter` | `brokers/common/ResilientHttpTransport` + broker endpoint policies |
| DP-02 | High | 6+ application modules | Independent `OrderRequest`→`OmsOrderCommand` mappers in `session_bridge`, `composer/execution`, `place_order_use_case`, `execution_planner`, `square_off`, `oms_backtest_adapter` | One canonical mapper module |
| DP-03 | High | `event_bus.py`, `async_event_bus.py` | Capital semantics: `_is_capital_event()` vs `CRITICAL_EVENT_TYPES`; async can drop events sync fsyncs | Single `domain/events/capital_events.py` canonical set |
| DP-04 | High | Dhan/Upstox WS stacks | Three reconnect models: `ReconnectingServiceMixin`, inline backoff in `MarketFeedConnection`, `UpstoxAutoReconnect` | Unify on `ReconnectingTransport` + shared backfill coordinator |
| DP-05 | High | `datalake/quality/` (4–5 modules), `mcp/tools.py`, `analytics/views/quality.py` | OHLC/gap/duplicate checks reimplemented in pandas, SQL, MCP, views | Single quality contract: ingest→validate, catalog→materialized, runtime→views |
| DP-06 | Medium | `analytics/pipeline/features.py`, `datalake/analytics/features.py`, `domain/indicators/` | Three RSI/ATV/VWAP implementations + SQL window functions | Domain indicators as single source; pipeline wraps domain |
| DP-07 | Medium | `credential_resolver.py`, `gateway/factory.py`, `broker_plugin.py` | Three env-path resolution sources | One resolver; gateway delegates |
| DP-08 | Medium | `providers/csv/csv_data_provider.py`, `providers/dataframe/dataframe_data_provider.py` | Identical `_NullSubscription` copy-paste | Shared helper in `providers/null/stubs.py` |
| DP-09 | Medium | `common/backoff.py`, `infrastructure/resilience/backoff.py` | Same exponential backoff algorithm, two modules | Single backoff module |
| DP-10 | Medium | `interface/api/routers/market.py`, `interface/api/routers/live/market.py` | Duplicated `_SessionState` class | Extract to `interface/api/session_state.py` |
| DP-11 | Low | `dhan/segments.py`, `upstox/instruments/segment_mapper.py`, `paper/segment_mapper.py` | Per-vendor segment maps (acceptable boundary) | Cross-broker contract tests in `common/contracts/` |

### 6. Shotgun Surgery

| ID | Severity | Files | Evidence | Recommendation |
|---|---|---|---|---|
| SS-01 | High | Order status + capabilities across brokers | Status/capability changes touch 3–4 files per broker | Capability YAML/JSON per broker; status registry + contract test |
| SS-02 | High | `place_order` path (22 files under `brokers/`) | Parallel Dhan/Upstox/Paper stacks + services layer | One `OrderPlacementPort`; CLI/services call port only |
| SS-03 | High | Kill-switch guards in 5+ places | `composer/execution`, `square_off_service`, `extended_order_service`, `order_lifecycle`, `trading_orchestrator` | Central `OrderMutationGuard` on OMS entry |
| SS-04 | Medium | Event-bus bootstrap | `build_production_event_bus` in bootstrap, broker_service, composition | Single `bootstrap_runtime()` wires sinks + bus once |
| SS-05 | Medium | Streaming handles | Dhan closures, Upstox `StreamingGateway`, `common/streaming.DepthStreamHandle` | One `StreamHandle` protocol |
| SS-06 | Medium | `cli/broker.py` (569 LOC, 25+ commands) | Broker-specific commands hard-coded | Capability-driven CLI via `get_capabilities` |

### 7. Primitive Obsession

| ID | Severity | Files | Evidence | Recommendation |
|---|---|---|---|---|
| PO-01 | Medium | `trading_orchestrator.py`, `order_manager.py`, `domain/ports/risk_manager.py` | Untyped `event.payload` dict parsing; `get_all_orders()` returns `list[dict]`; `check_order` typed `Any→Any` | Typed event DTOs; return `list[Order]`; strengthen port signatures |
| PO-02 | Medium | `runtime/factory.py` | `Runtime` dataclass holds 6+ `Any` bags | Typed fields on `Runtime` (protocols for OMS/observability) |
| PO-03 | Medium | `square_off_service.py`, `extended_order_service.py` | All deps typed as `Any` | Depend on `OrderServicePort` / `RiskManagerPort` |
| PO-04 | Low | String broker/mode branching in interface | ~30 string comparisons remain (see **G1** in architecture.md) | `BrokerId` enum at composition root only |

### 8. Feature Envy

| ID | Severity | Files | Evidence | Recommendation |
|---|---|---|---|---|
| FE-01 | Medium | `order_placer.py`, `extended_order_service.py` | `resolve_equity` walks `order_manager.risk_manager.capital_provider` | Inject `CapitalProviderPort` |
| FE-02 | Medium | `interface/ui/commands/market.py`, `market_handlers.py` | Commands reach through `broker_service.active_broker`, map quote fields manually | `MarketDataPresenter` + domain DTOs |
| FE-03 | Medium | `execution_engine.py` | Reimplements reconciliation compare instead of using `domain/reconciliation_engine.py` | Application heals; domain compares |
| FE-04 | Low | `analytics_sector.py` | Six near-identical `run_*` functions | Parameterized `run_sector_analysis(kind, args)` |

### 9. Cyclic Dependencies

No import-level cycles detected (`graphify diagnose multigraph`: 0 collapsed same-endpoint groups). **Implicit cycles** via global singletons:

| ID | Severity | Files | Evidence | Recommendation |
|---|---|---|---|---|
| CY-01 | High | `application/oms/process_context.py`, `session_bridge.py` | Module singleton `_registered` + `get_oms_context()`; `build_oms_service` branches on global state | Inject `TradingContext` explicitly; singleton for tests only |
| CY-02 | Medium | `infrastructure/gateway/factory.py` → `runtime/broker_builders.py` | Only infra→runtime import; lazy builder registration | Registration callback at startup instead of infra pulling runtime |

### 10. Tight Coupling

| ID | Severity | Files | Evidence | Recommendation |
|---|---|---|---|---|
| TC-01 | High | `interface/` → `brokers.*` (7 direct imports) | `broker_service.py`, `broker_ops.py`, `doctor/__init__.py`, `validate.py`, `benchmark.py`, `cli_broker_facade.py`, `market_access.py` | Route through runtime/tradex ports; architecture ratchet |
| TC-02 | High | Triple composition roots | CLI: `BrokerService._ensure_initialized`; API: `initialize_all_services`; SDK: `open_session` | Single `runtime.factory.build(mode=...)` |
| TC-03 | High | `dhan/api/http_client.py` | Dual rate limiting: legacy `_throttle()` + `MultiBucketRateLimiter` | Remove legacy path; one enforcement point |
| TC-04 | Medium | `deps.py`, `api/routers/live/extended.py` | `getattr(svc, "allow_live_orders")`, `getattr(svc, "broker_infrastructure")` | `BrokerServicePort` with explicit properties |
| TC-05 | Medium | `dhan/streaming/connection.py` | 20+ direct adapter imports; constructor changes ripple | DI registry: `{name: factory(client, resolver)}` |

### 11. SOLID Violations

| Principle | Severity | Files | Evidence | Recommendation |
|---|---|---|---|---|
| **SRP** | High | `EventBus`, `BrokerService`, `DataLakeGateway` | Multiple unrelated responsibilities per class (see God Classes) | Decompose per GC recommendations |
| **OCP** | Medium | `cli/broker.py`, capability flags | New broker features require CLI + wire + connection edits | Capability registry + discovery |
| **LSP** | Medium | `domain/ports/observability.py` vs `alerting.py` | `AlertingEnginePort.evaluate()` vs impl `evaluate_all()`; `EventMetricsPort.snapshot()` type mismatch | Align port to implementation or add adapter |
| **ISP** | Medium | `BrokerService` | 37 methods on one class; callers depend on full surface | Split interfaces by concern |
| **DIP** | High | `TradingOrchestrator`, `SquareOffService`, `deps.py` | Concrete `OrderManager`; `Any` deps; `SimpleNamespace` container | Protocol injection; typed `ServiceContainer` (**G-P2-1**) |

### 12. DRY Violations

Consolidated in **Duplicate Code** (DP-01 through DP-11) and **Shotgun Surgery** (SS-01 through SS-06). Highest-impact DRY fixes:

1. HTTP transport (DP-01)
2. Order command mappers (DP-02)
3. Quality validation semantics (DP-05)
4. Feature/indicator implementations (DP-06)
5. CLI analytics arg parsing (13 files with hand-rolled loops; `parse_common_args` exists but unused outside `analytics_utils.py`)

### 13. Over-Engineering

| ID | Severity | Files | Evidence | Recommendation |
|---|---|---|---|---|
| OE-01 | Medium | `src/analytics/views/` (~1.9k LOC, 12 modules) | Layered view stack parallel to Python FeaturePipeline scanners | Pick one scanner path: SQL views **or** Python pipeline |
| OE-02 | Medium | 12+ `Upstox*Client` classes | 54-line clients that only wrap `get_json(url)` | Collapse to endpoint table + one client |
| OE-03 | Low | `observability/alerting.py` (598 LOC) | In-process glob-matching alerts rarely wired in production | Wire or demote |
| OE-04 | Low | `analytics/views/cache_manager.py`, `validator.py`, `ViewRegistry` | View infrastructure for batch path while Python scanners exist for replay | Document ownership; deprecate redundant path |

### 14. Under-Engineering

| ID | Severity | Files | Evidence | Recommendation |
|---|---|---|---|---|
| UE-01 | **Critical** | `datalake/adapters/analytics_provider.py` | `query()` uses `duckdb.connect(":memory:")` — cannot see catalog; docstring admits broken (**G-P2-3**) | Route through read pool or `DataCatalog.query()` |
| UE-02 | High | `datalake/quality/validation.py` | `validate_parquet_file()` returns `valid_rows=len(df)` even when dirty | Return `ValidationAudit`; delegate to `DataQualityEngine` |
| UE-03 | High | `datalake/quality/engine.py` | `completeness_pct` only when `gap_days > 0`; zero-gap symbols report 0.0% | Default 100.0 when no gaps |
| UE-04 | High | `runtime/api_compose.py` | Doc claims AsyncEventBus; `create_api_event_bus()` returns sync `EventBus`; `ResilienceConfig.max_async_bus_queue` never consumed | Wire AsyncEventBus or delete unused config |
| UE-05 | High | `application/oms/_internal/risk_manager.py` | Instrument lookup failure skips tick validation (fail-open) | Fail closed when limit order + price > 0 |
| UE-06 | Medium | `place_order_use_case.py`, `oms_backtest_adapter.py` | Spine optional when `_target` unset; test `submit_fn` bypasses spine (**G-P0-3** partial) | Require `ExecutionTarget`; spine always |
| UE-07 | Medium | `datalake/ingestion/loader.py` | `validate_candles` called twice on same frame | Validate once at write boundary |
| UE-08 | Medium | `datalake/quality/health_check.py` | Standalone script with raw connect; not wired to CI gate | Fold into `DataQualityMonitor.run_checks()` |
| UE-09 | Medium | `analytics/backtest/fast_backtest.py` | Look-ahead bias: features on full dataset; inline fills diverge from replay OMS (**G-P2-2**) | Research-only gate; never wire to order paths |

---

## Cross-Reference: Known Gap Analysis (not re-derived)

| Gap ID | Topic | This Review Adds |
|---|---|---|
| G-P0-1 | ExecutionTarget protocol | Class-level spine bypass evidence in `OrderPlacer`, optional spine in use case |
| G-P0-2 | Mode string branching | 7 remaining `mode ==` sites outside runtime |
| G-P0-3 | Multiple place_order surfaces | 6+ duplicate order mappers; paper_orders bypass |
| G-P1-1 | Clock purity | Domain `coverage_from_bars` still uses `datetime.now()` |
| G-P1-4 | Paper orders legacy bypass | Confirmed in under-engineering |
| G-P1-6 | RuntimeMode vs ExecutionTargetKind | Triple composition root divergence |
| G-P2-1 | deps.py untyped getters | Stale doc references `infrastructure.di.container` (doesn't exist) |
| G-P2-2 | Dual backtest engines | FastBacktest look-ahead + inline fill divergence |
| G-P2-3 | DuckDB drift sites | Broken `:memory:` query + quality path fragmentation |
| G-P2-4 | Session `.buy()` helpers | Not re-audited (out of scope) |
| G-P2-5 | Interface→brokers imports | 7 direct imports enumerated |

---

## Positive Observations

- **Domain purity holds:** no `domain/` imports from application/infrastructure/brokers.
- **Recent cleanup effective:** Ponytail Waves removed significant dead code, unified event bus, collapsed CQRS.
- **Spine exists:** `place_order_spine` used by `ExecutionEngine`, composer, use case — wiring gaps remain, not absence of design.
- **Architecture ratchets active:** duckdb single-connection test, place_order path inventory, clock purity tests.
- **Upstox decomposition pattern:** gateway extraction in `upstox/adapters/` is the target state for Dhan.
- **OrderManager decomposition real:** `OrderValidator`, `OrderLifecycle`, `TradeRecorder`, `IdempotencyGuard` are extracted, not just commented.

---

## Refactoring Roadmap (Minimal but Correct)

### Phase A — Money-safety (1–2 weeks)

1. Add kill-switch guard to `cancel_order` (match `modify_order` policy)
2. Fix `DataLakeMarketDataProvider.query()` pool routing
3. Remove Dhan dual rate limiting
4. Unify capital-event classification for sync/async event bus
5. Fail-closed tick validation in `RiskManager`

### Phase B — Zero-parity spine (2–3 weeks)

1. Route `OrderPlacer` through `ExecutionEngine` / spine
2. Canonical order mapper module
3. Single RISK event publisher (validator vs orchestrator)
4. Wire or delete AsyncEventBus path
5. Require `ExecutionTarget` on all placement paths

### Phase C — Hub decomposition (3–4 weeks)

1. Split `EventBus` responsibilities
2. Thin `BrokerService` to lifecycle facade
3. Extract Dhan gateways (mirror Upstox)
4. Shared `ResilientHttpTransport` for brokers
5. Unify composition on `runtime.factory.build`

### Phase D — Analytics/data quality (2–3 weeks)

1. G-P2-3 pool consolidation (delete ratchet exemptions)
2. Unify quality semantics (`validate_candles` / engine / views)
3. Pick one scanner stack (SQL vs Python)
4. Domain indicators as single feature source
5. Decompose `DataLakeGateway`, `HistoricalDataLoader`

### Phase E — Interface cleanup (1–2 weeks)

1. Typed `ServiceContainer` (**G-P2-1**)
2. Registry-only CLI dispatch in `main.py`
3. Adopt `parse_common_args` across analytics commands
4. Eliminate direct `brokers.*` imports in interface
5. Extract market command renderers

---

## Appendix: Largest Files (LOC)

| File | LOC |
|---|---|
| `brokers/dhan/websocket/market_feed.py` | 638 |
| `brokers/dhan/api/http_client.py` | 631 |
| `brokers/dhan/streaming/connection.py` | 618 |
| `infrastructure/event_bus/event_bus.py` | 599 |
| `infrastructure/observability/alerting.py` | 598 |
| `brokers/paper/paper_gateway.py` | 593 |
| `brokers/upstox/websocket/market_data_v3.py` | 572 |
| `brokers/cli/broker.py` | 569 |
| `brokers/dhan/websocket/connection.py` | 566 |
| `application/trading/trading_orchestrator.py` | 556 |
| `interface/ui/commands/market.py` | 549 |
| `brokers/dhan/wire.py` | 544 |
| `interface/ui/services/broker_service.py` | 539 |

---

*Generated by static analysis pass. No source code modified. Re-run after major refactors: `radon cc src -s -a`, `vulture src --min-confidence 80`, `graphify update .`*
