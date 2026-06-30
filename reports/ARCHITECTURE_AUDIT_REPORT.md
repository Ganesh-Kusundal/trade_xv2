# TradeXV2 Stability Engineering & Architecture Audit Report

**Date:** June 30, 2026
**Scope:** Full codebase audit covering domain, brokers (Dhan + Upstox + Paper), infrastructure, application, API, datalake, analytics, frontend, and runtime layers.
**Methodology:** Source-code-only verification. Three parallel code-review perspectives (completeness, correctness, impact) merged with deep architectural tracing of every major execution flow.

---

## 1. Executive Summary

TradeXV2 is a Python-based quantitative trading platform with a **well-designed hexagonal core** but **critical stability gaps** that make it unsafe for production trading in its current state.

**Strengths:**
- Clean domain layer with frozen dataclasses, no dependency violations, and canonical state machines
- Comprehensive broker abstraction with 3 implementations behind a common ABC
- Event-driven architecture with dead-letter queues, correlation IDs, and replay capability
- Excellent replay/backtest infrastructure with golden dataset comparison
- Import-linter contracts enforce architectural boundaries

**Critical weaknesses:**
- API server cannot start (broken imports in global exception handler)
- API order placement bypasses OMS risk pipeline entirely (regulatory/financial risk)
- API order modify/cancel endpoints crash at runtime (wrong request types)
- RiskManager silently resets margin configuration on kill-switch toggle
- Multiple thread-safety violations in singleton initialization
- 25+ datalake shim files indicate incomplete migration creating dual-path confusion

**Bottom line:** The architectural intent is sound. The implementation has critical gaps in the API-to-OMS bridge, thread safety, and configuration management that must be resolved before any production deployment.

---

## 2. Overall Architecture Score: 68/100

| Dimension | Weight | Score | Weighted |
|-----------|--------|-------|----------|
| Layer separation | 15% | 82 | 12.3 |
| Broker abstraction | 15% | 65 | 9.8 |
| Domain model integrity | 15% | 80 | 12.0 |
| Event architecture | 10% | 75 | 7.5 |
| Configuration management | 10% | 50 | 5.0 |
| Error handling | 10% | 55 | 5.5 |
| Observability | 10% | 72 | 7.2 |
| Extensibility | 10% | 60 | 6.0 |
| Shim/debt burden | 5% | 40 | 2.0 |
| **Total** | **100%** | | **67.3 ≈ 68** |

---

## 3. Stability Score: 52/100

**Rationale:**
- API server non-startable due to ImportError (-15)
- API POST/PUT/DELETE order endpoints all crash at runtime (-15)
- RiskManager silently corrupts config on kill-switch toggle (-8)
- Thread-safety violations in SecretManager and FeatureFlags (-5)
- Hardcoded timezone offsets wrong 5 months/year (-3)
- AsyncEventBus silently drops critical trade events (-2)

**Positive factors:**
- OMS state machine is correctly implemented (+8)
- EventBus handler failures never swallowed (+5)
- Lifecycle management has timeout enforcement (+5)
- Atomic write patterns in datalake (+2)

---

## 4. Regression Risk Score: 62/100

**High-risk areas:**
- 25 datalake shim files with 12+ still imported by production code
- Deprecated `domain/status_normalizer.py` still importable
- `domain/models/__init__.py` re-exports all entities (dual import paths)
- Paper trading `OrderStatus` enum diverges from domain (PENDING vs OPEN)
- Two kill-switch event types (`KILL_SWITCH_FLIPPED` vs `KILL_SWITCH_TOGGLED`)
- Feature flags duplicated between `config/schema.py` and `config/feature_flags.py` with conflicting defaults

**Mitigating factors:**
- Import-linter contracts prevent cross-layer violations
- Architecture tests enforce exception hierarchy
- Golden dataset comparison for replay regression

---

## 5. Maintainability Score: 67/100

**Positive:**
- Consistent naming conventions across modules
- Frozen dataclasses enforce immutability
- Clear port/adapter separation in domain layer
- Comprehensive error hierarchy

**Negative:**
- 25 shim files + 3 top-level shims add cognitive overhead
- Two parallel logging systems (`logging.py` + `logging_config.py`)
- `ServiceContainer` fields all typed as `Any` (zero type safety in DI)
- `CommonBrokerGateway` Protocol exists but is unused (dead abstraction)
- Business logic embedded in API routers (scanner, portfolio, orders)

---

## 6. Modularity Score: 75/100

**Well-separated modules:**
- `domain/` — zero outward dependencies (verified via grep)
- `brokers/dhan/` and `brokers/upstox/` — mutually isolated (import-linter enforced)
- `infrastructure/` — no imports from `brokers/` or `application/`
- `analytics/` — no imports from broker-specific adapters

**Concerns:**
- `application/composer/` creates a parallel order path that bypasses `application/oms/`
- `api/routers/scanner.py` duplicates `application/scanner/scanner_service.py` logic
- `datalake/__init__.py` imports through its own shim files instead of canonical paths

---

## 7. Coupling Score: 65/100

**Tight coupling points:**
- API routers directly construct broker-specific request types
- `ExecutionComposer` couples API layer to broker routing, bypassing OMS
- Both Dhan and Upstox gateways independently implement stream callback deduplication
- Idempotency cache implemented independently in both broker adapters
- Post-cancellation verification duplicated across all 3 gateways

**Loose coupling strengths:**
- Domain entities have no framework dependencies
- EventBus uses protocol-based subscription
- Broker adapters accessed only through common ABC

---

## 8. Cohesion Score: 70/100

**High cohesion:**
- `domain/entities/` — each file owns exactly one business concept
- `domain/constants/` — well-scoped constant groups
- `brokers/dhan/` adapters — single-responsibility per adapter
- `infrastructure/event_bus/` — focused event infrastructure

**Low cohesion:**
- `application/oms/` — OrderManager, PositionManager, RiskManager, PortfolioTracker, SquareOffService, ExtendedOrderService all in one package with tangled dependencies
- `api/routers/portfolio.py` — mixes PnL computation, portfolio summary, and square-off logic
- `datalake/gateway.py` — 22KB file combining read access, caching, and data transformation
- `brokers/common/gateway.py` — monolithic ABC with 320+ lines combining market data, trading, portfolio, instruments, streaming, and lifecycle

---

## 9. Testability Score: 76/100

**Strengths:**
- Protocol-based DI enables mocking
- Frozen dataclasses are trivially testable
- Replay engine supports deterministic testing
- Golden dataset comparison for regression testing
- Architecture tests enforce quality constraints

**Weaknesses:**
- `ServiceContainer` fields typed as `Any` — no compile-time verification of wiring
- Module-level singletons (`memory_cache`, `health_registry`) hard to isolate in tests
- `PortfolioTracker` tests pass because they use `MagicMock` which masks nonexistent method calls
- No contract tests verifying broker adapter compliance with `CommonBrokerGateway` Protocol

---

## 10. Replay Readiness Score: 82/100

**Strengths:**
- `UnifiedReplayOrchestrator` merges historical bars with domain events
- Deterministic replay guarantees: single time source, no side effects, idempotent pipelines
- Golden dataset comparison with floating-point tolerance
- `OmsBacktestAdapterPort` ensures paper/replay/live parity through same OMS path
- Indian market fees support (STT, transaction charges, stamp duty)
- Circular buffer for bounded memory during long replays

**Gaps:**
- Event persistence is best-effort (in-memory EventLog by default)
- No cross-process replay from previous crash
- `PersistentDeadLetterQueue` exists but standard `DeadLetterQueue` (in-memory) is default

---

## 11. Broker Abstraction Score: 63/100

**What works:**
- All 3 brokers implement `MarketDataGateway` ABC
- Capability registry pattern for runtime feature discovery
- Extension interfaces for broker-specific features (GTT, slice, super orders)
- Broker isolation enforced by import-linter (no Dhan↔Upstox imports)

**What doesn't:**
- `CommonBrokerGateway` Protocol (async, "universal port") implemented by NO broker
- Error policy divergence: Dhan raises `OrderError`, Upstox returns `OrderResponse.fail()`
- Only Dhan implements `ObservabilityProvider`
- Different max batch sizes (Dhan=1000, Upstox=10) not abstracted
- Plugin entry points in `pyproject.toml` are entirely commented out
- `MarketDataProvider` defined in 3 different places

---

## 12. Domain Model Health: 78/100

**Healthy:**
- All core entities are frozen dataclasses (immutability enforced)
- Canonical state machines for Order and Position lifecycles
- `InstrumentId` provides universal canonical identification
- `DataProvenance` tracks data lineage
- `GatewayResult[T]` monadic result for error handling
- No dependency violations (domain imports only from stdlib + internal)

**Unhealthy:**
- `Quote` vs `QuoteSnapshot` — dual quote models (QuoteSnapshot preferred but Quote widely used)
- `InstrumentRef` vs `InstrumentId` vs `Instrument` — three instrument identity types
- `analytics/paper/models.py` defines parallel Order/Trade/Position models
- `analytics/replay/models.py` defines SimulatedTrade/SimulatedPosition
- `KILL_SWITCH_FLIPPED` vs `KILL_SWITCH_TOGGLED` duplicate event types
- `RISK_FALLBACK_CAPITAL` (100K) vs `PHANTOM_CAPITAL_INR` (1M) — 10x discrepancy

---

## 13. Single Source of Truth (SSOT) Violations

| Concept | Canonical Owner | Violation | Severity |
|---------|----------------|-----------|----------|
| **OrderStatus** | `domain.enums.OrderStatus` | `analytics.paper.models.OrderStatus` (PENDING vs OPEN, missing states) | Critical |
| **OrderSide/Side** | `domain.enums.Side` | `analytics.paper.models.OrderSide` (identical values, different class) | High |
| **Kill Switch Event** | `KILL_SWITCH_FLIPPED` | `KILL_SWITCH_TOGGLED` — semantically identical, different names | High |
| **MarketDataProvider** | `brokers.common.gateway_interfaces` | Also defined in `brokers.common.broker_port` and implicitly in `datalake` | High |
| **Instrument** | `domain.entities.instrument.Instrument` | `brokers.common.instruments.Instrument` (extended fields), `brokers.dhan.domain.Instrument` (typed enums) | Medium |
| **Fallback Capital** | Single constant needed | `RISK_FALLBACK_CAPITAL`=100K vs `PHANTOM_CAPITAL_INR`=1M | High |
| **Quote** | `domain.entities.market.Quote` | `QuoteSnapshot` adds provenance; docs say "prefer QuoteSnapshot" but Quote still widely used | Medium |
| **Smart Routing Flag** | Single config source | `FeatureFlags.SMART_ROUTING` (default False) vs `TradingConfig.smart_routing` (default True) | High |
| **Scanner Logic** | `application.scanner.ScannerService` | Duplicated inline in `api/routers/scanner.py` | Medium |
| **Exchange Normalization** | Single function | `_normalize_exchange()` in both Dhan and Upstox gateways | Low |

---

## 14. Duplication Report

### 14.1 Cross-Broker Duplication

| Logic | Dhan Location | Upstox Location | Paper Location | Recommendation |
|-------|--------------|-----------------|----------------|----------------|
| Post-cancel verification | `gateway.py:157-181` | `gateway.py:596-628` | `paper_gateway.py:260-289` | Extract to `BatchFetchMixin` or shared mixin |
| Correlation ID injection | `gateway.py:119-125` | `gateway.py:531-537` | N/A | Extract to common helper |
| Stream callback dedup | `gateway.py:548-595` | `stream_manager.py:86-109` | N/A | Extract to `StreamDeduplicator` in `brokers/common/` |
| Idempotency cache | `orders.py:63-99` | `orders/idempotency.py` | N/A | Both implement `IdempotencyCachePort` — consolidate to common |
| `history()` method | `gateway.py:410-430` | `gateway.py:252-289` | N/A | Nearly identical — extract to `BatchFetchMixin` |
| Instrument load logging | `connection.py:327-380` | `gateway.py:213-246` | N/A | Extract to common instrumentation mixin |
| Exchange normalization | `gateway.py:706-718` | `gateway.py:785-793` | N/A | Single function in `domain.symbols` |

### 14.2 Cross-Layer Duplication

| Logic | Locations | Recommendation |
|-------|-----------|----------------|
| PnL calculation | `api/routers/portfolio.py`, `application/oms/portfolio_tracker.py` | Consolidate in `PortfolioTracker` |
| Scanner construction | `api/routers/scanner.py:172-277`, `application/scanner/scanner_service.py` | Router must delegate to service |
| Logging setup | `infrastructure/logging.py`, `infrastructure/logging_config.py` | Merge into single module |
| Feature flag concepts | `config/schema.py`, `config/feature_flags.py` | Single source with one env var per flag |
| Shim re-exports | 25 datalake shims + 3 top-level shims | Complete migration, remove shims |

---

## 15. Hidden Assumption Report

| # | Assumption | Where | Risk | Evidence |
|---|-----------|-------|------|----------|
| 1 | Thread-local correlation IDs work in async contexts | `infrastructure/correlation.py` | Wrong correlation IDs under concurrent async handlers | Uses `threading.local()` but FastAPI is async — coroutines share threads |
| 2 | `StateMachine` callers provide external synchronization | `infrastructure/state_machine.py:66-68` | Race condition if callers forget | Documented as not thread-safe, but no enforcement |
| 3 | `FeatureFlags._initialize()` is called once | `config/feature_flags.py:80` | Partially initialized flags under concurrent startup | No lock around `_ensure_initialized()` |
| 4 | `SecretManager.get_instance()` is called sequentially | `infrastructure/security/secret_manager.py:172` | Two instances created, one silently discarded | No lock in singleton accessor |
| 5 | Events are never dropped | `infrastructure/async_event_bus.py:89-105` | Trade events lost under load → wrong positions | Bounded queue drops silently when full |
| 6 | Kill-switch toggle preserves all config fields | `application/oms/_internal/risk_manager.py:320-327` | Margin checks silently reset to defaults | Only 4 of 6 RiskConfig fields carried forward |
| 7 | API order path goes through OMS | `api/routers/orders.py:246-308` | Orders skip risk checks, idempotency, audit | Uses `ExecutionComposer` directly |
| 8 | US exchange TZ offsets are constant | `infrastructure/time_service.py:36-37` | Wrong local time 5 months/year during non-DST | Hardcoded EDT/BST, no DST handling |
| 9 | `OrderResponse` has `.order` attribute | `api/routers/orders.py:287-308` | Every API order placement returns HTTP 500 | `OrderResponse` is flat dataclass, no `.order` field |
| 10 | `ModifyOrderRequest` accepts `symbol`/`exchange` | `api/routers/orders.py:348-360` | Every API order modification returns HTTP 500 | `slots=True` dataclass rejects unknown kwargs |

---

## 16. Circular Dependency Report

**No circular import cycles detected.** Import-linter contracts enforce:
- `infrastructure` → not `brokers`, not `application`, not `analytics`
- `brokers.dhan` → not `brokers.upstox` (and vice versa)
- `analytics` → not `brokers.dhan`, not `brokers.upstox`, not `brokers.paper`
- `application` → not `brokers.dhan`, not `brokers.upstox`, not `brokers.paper`
- `api` → not `cli`
- `datalake` → not `cli`

**One borderline violation:**
- `domain/ports/event_publisher.py` contains `from infrastructure.event_bus import DomainEvent` — but this is inside a **docstring** (usage example), not actual code. No runtime violation.

**Self-referencing shims (not circular but wasteful):**
- `config/endpoints.py` imports from itself for backward compat
- `config/indices.py` imports from itself for backward compat

---

## 17. Layer Violation Report

**Domain layer:** CLEAN — zero outward dependency violations (verified via grep).

**Import-linter contracts:** 11 contracts defined, all enforcing correct layer direction.

**Violations found:**

| # | Violation | From | To | Severity |
|---|-----------|------|----|----------|
| 1 | API router contains business logic | `api/routers/scanner.py:172-277` | ~100 lines of scanner construction/execution | High |
| 2 | API router contains business logic | `api/routers/portfolio.py:191-280` | ~80 lines of PnL history computation | High |
| 3 | API router contains business logic | `api/routers/portfolio.py:111-188` | Portfolio metrics computed inline | Medium |
| 4 | API order endpoint bypasses application layer | `api/routers/orders.py:246-308` | Skips `OrderManager`, calls `ExecutionComposer` directly | Critical |
| 5 | WebSocket handler creates infrastructure in handler | `api/ws/replay.py:87` | `DataLakeGateway(root="market_data")` per session | Low |

---

## 18. Technical Debt Report

| # | Debt Item | Location | Effort to Fix | Impact |
|---|-----------|----------|---------------|--------|
| 1 | 25 datalake shim files | `datalake/*.py` root | Medium (migrate all importers) | High (dual-path confusion) |
| 2 | 3 top-level shim files | `endpoints.py`, `indices.py`, `secrets_manager.py` | Medium (10+ importers each) | High (root-level pollution) |
| 3 | Unused `CommonBrokerGateway` Protocol | `brokers/common/broker_port.py` | Low (remove or implement) | Medium (false abstraction) |
| 4 | Commented-out plugin entry points | `pyproject.toml:40-44` | Low (implement or remove) | Low (misleading) |
| 5 | Deprecated `status_normalizer.py` | `domain/status_normalizer.py` | Low (remove shim) | Low (confusion) |
| 6 | `datalake/store/` empty package | `datalake/store/` | Low (remove) | Low (clutter) |
| 7 | Two parallel logging systems | `infrastructure/logging.py` + `logging_config.py` | Medium (merge) | Medium (confusion) |
| 8 | `Any`-typed ServiceContainer | `api/deps.py:31-85` | Medium (add proper types) | Medium (no type safety) |
| 9 | Broken global exception handler | `infrastructure/global_exception_handler.py` | Low (fix imports) | Critical (server won't start) |
| 10 | Dead `PaperOMSAdapter`/`ReplayOMSAdapter` | `application/execution/execution_mode_adapter.py:77-78` | Low (remove) | Low (confusion) |
| 11 | `normalize.py` one-shot migration script in datalake root | `datalake/normalize.py` | Low (move to scripts/) | Low |
| 12 | Non-functional PnL in tradebook | `api/routers/orders.py:177` | Medium (implement PnL) | High (misleading data) |

**Total estimated debt items:** 12 high-priority, 8 medium-priority, 10+ low-priority

---

## 19. Architecture Smells

| # | Smell | Location | Why It Matters |
|---|-------|----------|----------------|
| 1 | **Two broker abstraction hierarchies** | `MarketDataGateway` (sync ABC) + `CommonBrokerGateway` (async Protocol) | Neither broker implements the "target" Protocol; adapter bridges them. New developers don't know which to implement. |
| 2 | **API layer is the composition root** | `api/routers/orders.py` decides whether to use OMS or ExecutionComposer | Composition decisions belong in the runtime/bootstrap layer, not in HTTP handlers. |
| 3 | **Feature flags have two sources of truth** | `config/feature_flags.py` + `config/schema.py` | Same feature, two env vars, different defaults. Operators cannot predict system behavior. |
| 4 | **Broker-specific behavior leaks through `.extended`** | Both gateways expose `.extended` returning different types | Callers must know the concrete broker type to use extended features. Violates abstraction. |
| 5 | **Synchronous OMS in async API** | `OrderManager` is sync, FastAPI is async | The sync/async boundary creates impedance mismatch and prevents async broker I/O. |
| 6 | **Datalake facade imports through its own shims** | `datalake/__init__.py` | The "new" canonical path goes through the "old" shim layer. Migration is incomplete. |
| 7 | **Risk config is frozen but recreated incompletely** | `risk_manager.py:320-327` | Frozen dataclass is good, but recreation loses fields — defeats the purpose of immutability. |

---

## 20. Code Smells

| # | Smell | Location | Type |
|---|-------|----------|------|
| 1 | Unreachable return statement | `risk_manager.py:200` | Dead code |
| 2 | `pnl = 0.0` hardcoded with TODO comment | `orders.py:177` | Incomplete implementation |
| 3 | `ThreadPoolExecutor(max_workers=1)` created per-call | `trading_orchestrator.py:249` | Resource waste |
| 4 | `DataLakeGateway()` created inside WS handler | `ws/replay.py:87` | Per-request infrastructure creation |
| 5 | Module-level mutable `_stream_tasks` dict | `ws/replay.py:18` | Global mutable state |
| 6 | `ExtendedOrderService` uses `Any` for all constructor params | `extended_order_service.py` | Type erasure |
| 7 | `RiskManagerPort.check_order()` accepts `Any`, returns `Any` | `domain/ports/risk_manager.py` | Defeats Protocol purpose |
| 8 | `api/schemas.py` Trade uses `transaction_type` instead of `side` | `api/schemas.py` | Naming inconsistency with domain |
| 9 | `f"{view_name}"` in SQL queries | `scanner.py:83`, `strategy.py:48-76` | SQL injection pattern (even if currently safe) |
| 10 | `lifecycle.py` is misnamed — it's a factory, not lifecycle management | `api/lifecycle.py` | Misleading module name |

---

## 21. Performance Risks

| # | Risk | Location | Impact | Severity |
|---|------|----------|--------|----------|
| 1 | `ThreadPoolExecutor` created per feature-fetch call | `trading_orchestrator.py:249` | Thread creation overhead on every scan cycle; threads are expensive in Python | High |
| 2 | `DataLakeGateway` created per WebSocket replay session | `ws/replay.py:87` | DuckDB connection + catalog load per client connection | Medium |
| 3 | `get_order_repository()` creates new adapter per HTTP request | `api/deps.py:246-249` | Minor overhead per request | Low |
| 4 | `BatchFetchMixin` doesn't respect broker max batch sizes | Dhan=1000, Upstox=10 | Upstox requests may exceed API limits | Medium |
| 5 | Synchronous EventBus.publish() in async handlers | `event_bus.py` | Blocks event loop during handler dispatch | Medium |
| 6 | `_DOMAIN_TYPES` dict grows unboundedly | `event_log.py:31` | Minor memory leak over long-running processes | Low |
| 7 | No connection pooling for broker HTTP clients | `DhanHttpClient`, Upstox equivalent | Connection setup overhead per request | Medium |
| 8 | Per-metric `Lock` in metrics system | `infrastructure/metrics/` | Lock contention under high-frequency metric updates | Low |

---

## 22. Concurrency Risks

| # | Risk | Location | Type | Severity |
|---|------|----------|------|----------|
| 1 | `SecretManager.get_instance()` — no lock | `secret_manager.py:172` | Race condition in singleton creation | High |
| 2 | `FeatureFlags._ensure_initialized()` — no lock | `feature_flags.py:80` | Race condition; partially initialized dict readable | High |
| 3 | Thread-local correlation IDs in async context | `correlation.py:15` | Wrong correlation IDs across coroutines | High |
| 4 | `StateMachine` not thread-safe | `state_machine.py:66-68` | Race if callers forget external sync | Medium |
| 5 | `_DOMAIN_TYPES` mutable global dict | `event_log.py:31` | Concurrent registration race (mitigated by GIL) | Low |
| 6 | AsyncEventBus drops events silently | `async_event_bus.py:89-105` | Data loss under load; no backpressure | High |
| 7 | LifecycleManager uses daemon threads for stop() | `lifecycle.py:267-319` | Non-deterministic shutdown; data loss on SIGTERM | Medium |
| 8 | `EventBus._subscribers_lock` is `Lock` not `RLock` | `event_bus.py:188` | Deadlock if handler re-subscribes during publish | Low (documented) |

**No deadlock risks detected** — lock ordering is clean, no nested lock acquisition in production code.

---

## 23. Production Risks

| # | Risk | Impact | Likelihood | Severity |
|---|------|--------|------------|----------|
| 1 | **API server cannot start** — broken imports in `global_exception_handler.py` | Complete platform outage | Certain (on every deploy) | **P0 — BLOCKER** |
| 2 | **API orders bypass risk pipeline** — no pre-trade validation | Regulatory violation; unlimited loss potential | Certain (every API order) | **P0 — BLOCKER** |
| 3 | **API POST/PUT/DELETE orders crash** — wrong attribute access | All order management via API non-functional | Certain | **P0 — BLOCKER** |
| 4 | **Kill-switch toggle resets margin config** | Margin checks silently re-enabled/disabled after toggle | On every kill-switch toggle | **P0 — CRITICAL** |
| 5 | **AUTH_MODE defaults to "none"** | Unauthenticated API accessible in production | Likely (missing env var) | **P0 — CRITICAL** |
| 6 | **Hardcoded TZ offsets wrong 5 months/year** | Incorrect exchange-local time calculations | Certain (twice yearly) | **P1 — HIGH** |
| 7 | **AsyncEventBus drops trade events** | Position tracking fails silently under load | Under high throughput | **P1 — HIGH** |
| 8 | **Correlation IDs lost in async context** | Impossible to trace orders through system | Under concurrent load | **P1 — HIGH** |
| 9 | **PortfolioTracker calls nonexistent method** | Portfolio endpoints crash at runtime | Certain (on every call) | **P1 — HIGH** |
| 10 | **Feature flag config drift** | Unpredictable feature behavior | On configuration change | **P2 — MEDIUM** |

---

## 24. Prioritized Fix Plan

### Phase 0 — Emergency (Blocks Production) — Est. 2-3 days

| # | Fix | File(s) | Risk if Skipped |
|---|-----|---------|-----------------|
| 0.1 | Fix broken imports in `global_exception_handler.py` | `infrastructure/global_exception_handler.py` | API server won't start |
| 0.2 | Fix `POST /orders` — map `OrderResponse` fields directly, route through `OrderManager` | `api/routers/orders.py` | Orders crash + skip risk |
| 0.3 | Fix `PUT /orders/{id}` — use correct `ModifyOrderRequest` fields | `api/routers/orders.py` | Modify crashes |
| 0.4 | Fix `DELETE /orders/{id}` — same `result.order` crash | `api/routers/orders.py` | Cancel crashes |
| 0.5 | Fix `RiskManager.set_kill_switch()` — preserve all config fields | `application/oms/_internal/risk_manager.py` | Margin config corruption |
| 0.6 | Change `AUTH_MODE` default to `"api_key"` | `api/auth.py` | Unauthenticated production API |

### Phase 1 — Critical Stability — Est. 3-5 days

| # | Fix | File(s) |
|---|-----|---------|
| 1.1 | Add lock to `SecretManager.get_instance()` | `infrastructure/security/secret_manager.py` |
| 1.2 | Add lock to `FeatureFlags._ensure_initialized()` | `config/feature_flags.py` |
| 1.3 | Replace `threading.local()` with `contextvars.ContextVar` for correlation IDs | `infrastructure/correlation.py` |
| 1.4 | Fix `PortfolioTracker.get_positions()` — use correct method name | `application/oms/portfolio_tracker.py` |
| 1.5 | Fix `PortfolioTracker.on_trade_applied()` — compare `Side` enum not string | `application/oms/portfolio_tracker.py` |
| 1.6 | Fix `SquareOffService._get_submit_fn()` — use correct attribute | `application/oms/square_off_service.py` |
| 1.7 | Remove unreachable return in risk_manager | `application/oms/_internal/risk_manager.py:200` |
| 1.8 | Implement priority-based event dropping in AsyncEventBus | `infrastructure/async_event_bus.py` |
| 1.9 | Fix hardcoded exchange TZ offsets — use `zoneinfo` | `infrastructure/time_service.py` |

### Phase 2 — SSOT Consolidation — Est. 5-7 days

| # | Fix | File(s) |
|---|-----|---------|
| 2.1 | Consolidate `analytics.paper.models.OrderStatus` → use `domain.enums.OrderStatus` | `analytics/paper/models.py` |
| 2.2 | Remove `KILL_SWITCH_TOGGLED`, use `KILL_SWITCH_FLIPPED` everywhere | `domain/events/types.py`, `application/oms/extended_order_service.py` |
| 2.3 | Consolidate `RISK_FALLBACK_CAPITAL` and `PHANTOM_CAPITAL_INR` | `domain/constants/defaults.py`, `domain/constants/risk.py` |
| 2.4 | Consolidate feature flags — single source, one env var per flag | `config/feature_flags.py`, `config/schema.py` |
| 2.5 | Extract shared broker logic: post-cancel verification, correlation ID injection, stream dedup | `brokers/common/` new mixins |
| 2.6 | Route scanner API through `ScannerService` — remove duplicated logic | `api/routers/scanner.py` |
| 2.7 | Implement actual PnL calculation in tradebook endpoint | `api/routers/orders.py` |

### Phase 3 — Architecture Cleanup — Est. 7-10 days

| # | Fix | File(s) |
|---|-----|---------|
| 3.1 | Complete datalake shim migration — update all importers, remove shims | `datalake/*.py` (25 files) |
| 3.2 | Remove top-level shim files (`endpoints.py`, `indices.py`, `secrets_manager.py`) | Project root |
| 3.3 | Decide fate of `CommonBrokerGateway` Protocol — implement or remove | `brokers/common/broker_port.py` |
| 3.4 | Merge parallel logging systems | `infrastructure/logging.py` + `logging_config.py` |
| 3.5 | Type `ServiceContainer` fields properly | `api/deps.py` |
| 3.6 | Remove deprecated `status_normalizer.py` | `domain/status_normalizer.py` |
| 3.7 | Remove empty `datalake/store/` package | `datalake/store/` |
| 3.8 | Remove dead `PaperOMSAdapter`/`ReplayOMSAdapter` | `application/execution/execution_mode_adapter.py` |
| 3.9 | Move `datalake/normalize.py` to `scripts/` | `datalake/normalize.py` |

---

## 25. Migration Plan

### 25.1 API-to-OMS Migration (Phase 0)

**Current:** `POST /orders` → `ExecutionComposer.place_order()` → broker directly
**Target:** `POST /orders` → `OrderManager.place_order()` → `submit_fn` → `ExecutionComposer` → broker

Steps:
1. Add `submit_fn` parameter support to `OrderManager.place_order()`
2. Create `GatewaySubmitFn` that wraps `ExecutionComposer` as a submit function
3. Update `POST /orders` to use `OrderManager` with the gateway submit function
4. Verify risk checks, idempotency, events, and position tracking all engage
5. Add integration test: place order via API → verify risk check occurred → verify event published → verify position updated

### 25.2 Datalake Shim Migration (Phase 3)

**Current:** 25 shim files in `datalake/` root re-exporting from subpackages
**Target:** All importers use canonical paths (`datalake.core.io`, `datalake.storage.catalog`, etc.)

Steps:
1. Run `scripts/migrate_shim_imports.py` to auto-update known importers
2. Manually update remaining 12 production importers
3. Update `datalake/__init__.py` to import from canonical paths
4. Add import-linter contract forbidding `datalake.<shim>` imports
5. Remove shim files one batch at a time (verify no breakage after each batch)
6. Remove top-level shims after updating their 10+ importers each

### 25.3 Broker Abstraction Unification (Phase 3)

**Current:** Two parallel hierarchies (`MarketDataGateway` ABC + `CommonBrokerGateway` Protocol)
**Target:** Single abstraction layer

Steps:
1. Audit which methods are actually used by consumers
2. If async is needed: migrate `MarketDataGateway` to async, rename to replace `CommonBrokerGateway`
3. If sync is sufficient: remove `CommonBrokerGateway` Protocol entirely
4. Extract shared logic (cancel verification, correlation ID, stream dedup) into `brokers/common/mixins.py`
5. Add contract tests verifying all brokers implement the chosen abstraction

---

## 26. Regression Prevention Strategy

### 26.1 Architectural Guardrails

| Guard | Implementation | Prevents |
|-------|---------------|----------|
| Import-linter contracts | Already in `.import-linter.ini` — add contracts for shim removal | Layer violations |
| Architecture tests | `tests/architecture/` — add test for `OrderResponse` attribute access | API-OMS mismatch |
| Exception hierarchy test | Already exists — extend to verify `global_exception_handler.py` imports | Broken imports |
| Thread-safety audit | Add test verifying all singletons use locks | Race conditions |
| SSOT enforcement | Add test verifying one `OrderStatus` enum, one kill-switch event | Duplication |

### 26.2 Contract Tests

| Contract | Test | Validates |
|----------|------|-----------|
| API order flow | Integration test: API → OMS → broker → event → position | End-to-end order path |
| Broker abstraction | Test all 3 gateways implement same interface methods | Broker parity |
| Risk pipeline | Test kill-switch toggle preserves all config fields | Config integrity |
| Event delivery | Test `TRADE_APPLIED` never dropped under load | Position accuracy |
| Correlation ID | Test correlation ID propagation through async handlers | Traceability |

### 26.3 Replay-Based Regression

| Scenario | Golden Dataset | Detects |
|----------|---------------|---------|
| Order placement via API | Record API request → replay → verify same OrderResponse | API contract drift |
| Kill-switch toggle during active session | Record toggle → replay → verify margin config unchanged | Config corruption |
| High-throughput event processing | Record 10K events → replay → verify all TRADE_APPLIED delivered | Event loss |

---

## 27. Architecture Fitness Checklist

| Principle | Status | Evidence |
|-----------|--------|----------|
| **SOLID — SRP** | Partial | Domain entities are single-purpose; API routers mix concerns |
| **SOLID — OCP** | Partial | Extension interfaces allow broker-specific features; but adding broker requires modifying core |
| **SOLID — LSP** | Weak | Dhan and Upstox have different error policies (raise vs return) |
| **SOLID — ISP** | Good | Narrow port interfaces (`OrderCommand`, `PortfolioProvider`, etc.) |
| **SOLID — DIP** | Good | Domain depends on ports, not implementations |
| **DDD** | Good | Rich domain model with frozen entities, state machines, value objects |
| **Hexagonal** | Good | Clean port/adapter separation; domain has zero outward deps |
| **Ports & Adapters** | Good | Well-defined ports in `domain/ports/`; adapters in `brokers/` |
| **Event-Driven** | Partial | EventBus exists but in-memory; no cross-process persistence guarantee |
| **Dependency Inversion** | Good | High-level modules don't depend on low-level modules |
| **Composition over Inheritance** | Partial | `MarketDataGateway` uses multiple inheritance from 8 interfaces |
| **Immutable Domain Events** | Good | Frozen dataclasses for all domain entities |
| **Explicit Dependencies** | Partial | `ServiceContainer` uses `Any` types; constructor injection is good |
| **CQRS** | N/A | Not applicable at current scale |
| **Config as Code** | Weak | Hardcoded values throughout; feature flags duplicated |

---

## 28. CI/CD Quality Gates

### Recommended Gates (in addition to existing)

| Gate | Tool | Blocks | Current Status |
|------|------|--------|----------------|
| Import-linter | `lint-imports` | Layer violations | Exists |
| Bare except detection | Architecture test | Code quality | Exists |
| Exception hierarchy validation | Architecture test | Error handling | Exists |
| **Import smoke test** | `python -c "import api.main"` | Broken imports | **MISSING — would catch P0 #1** |
| **API contract test** | Integration test | API-OMS mismatch | **MISSING — would catch P0 #2-4** |
| **Thread-safety lint** | Custom test | Race conditions | **MISSING — would catch Phase 1 items** |
| **SSOT uniqueness test** | Custom test | Duplicate models/events | **MISSING — would catch Phase 2 items** |
| Ruff linting | `ruff check` | Code smells | Exists |
| Type checking | `mypy` | Type errors | Exists (partial) |
| Test suite | `pytest` | Regressions | Exists |

### Immediate CI Addition

```yaml
# .github/workflows/quality-gates.yml
- name: Smoke test — all top-level imports
  run: |
    python -c "from infrastructure.global_exception_handler import setup_exception_handlers"
    python -c "from api.main import app"
    python -c "from application.oms.order_manager import OrderManager"
    python -c "from application.oms.risk_manager import RiskManager"

- name: SSOT uniqueness — one OrderStatus, one kill-switch event
  run: python scripts/check_ssot_uniqueness.py

- name: Thread-safety — all singletons use locks
  run: python scripts/check_singleton_safety.py
```

---

## 29. Long-term Evolution Roadmap

### Quarter 1: Stabilize (Months 1-3)
- Execute Phase 0 + Phase 1 fixes
- Add all CI quality gates
- Achieve 80%+ test coverage on `application/oms/` and `api/routers/`
- Document all public API contracts with OpenAPI schemas

### Quarter 2: Consolidate (Months 4-6)
- Execute Phase 2 (SSOT consolidation)
- Complete datalake shim migration
- Unify broker abstraction (remove dead Protocol or implement it)
- Migrate correlation IDs to `contextvars`
- Implement priority-based event delivery

### Quarter 3: Strengthen (Months 7-9)
- Execute Phase 3 (architecture cleanup)
- Add contract tests for all broker adapters
- Implement persistent event store (SQLite WAL or equivalent)
- Add chaos testing suite (network partitions, broker disconnects, event loss)
- Performance profiling and optimization (thread pool reuse, connection pooling)

### Quarter 4: Evolve (Months 10-12)
- Async OMS for true async order execution path
- Plugin-based broker discovery (implement the entry-point system)
- Multi-broker order routing with automatic failover
- Real-time reconciliation engine
- Production deployment with canary releases and automated rollback

### North Star Metrics
| Metric | Current | Target |
|--------|---------|--------|
| Architecture Score | 68 | 85+ |
| Stability Score | 52 | 90+ |
| Test Coverage (OMS) | ~60% | 90%+ |
| P0 Bugs | 6 | 0 |
| Shim Files | 28 | 0 |
| SSOT Violations | 10 | 0 |
| Mean Time to Detect | Unknown | < 5 min |
| Deployment Frequency | Ad hoc | Daily (automated) |

---

*End of Audit Report*
