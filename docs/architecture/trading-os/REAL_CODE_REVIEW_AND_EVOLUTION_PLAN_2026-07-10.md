# Trading OS Real-Code Review And Evolution Plan

**Date:** 2026-07-10  
**Scope:** Source-grounded runtime review plus the comprehensive architecture
review board scope from the 2026-07-10 prompt: architecture, quant readiness,
event design, code quality, frontend, broker integration, market data, testing,
reliability, security, performance, repository organization, and production
readiness.  
**Stance:** The target blueprint is direction. This document is the real-code
plan for evolving the existing tree toward it without a rewrite.

**Honesty note:** the first review pass was targeted at the Trading OS runtime
and money/data paths. It was not a line-by-line audit of every frontend,
analytics, broker, security, CI/CD, and infrastructure file. This update expands
the plan to match the requested full-platform review and marks which tracks
still require deeper evidence collection before final scoring.

## Executive Verdict

Trade_XV2 is not a greenfield mess. It already has several institutional-grade
parts:

- A real OMS spine with locking, idempotency, risk checks, event publishing, and
  trade de-duplication.
- A process-wide OMS context registry intended to keep CLI/API/SDK on one
  order book.
- Rich domain instruments and sessions that hide broker details behind ports.
- Broker capability models, extension registries, quota scheduling, historical
  federation, stream orchestration, readiness checks, and SQLite writer locks.

The problem is integration, not absence. The code has multiple good runtimes
living side by side:

- `tradex.connect` / `domain.universe.Session`
- `runtime.trading_runtime_factory.Runtime`
- `cli.services.BrokerService`
- `application.execution.ExecutionService`
- `application.composer.ExecutionComposer`
- direct instrument/provider subscription paths
- `application.streaming.StreamOrchestrator`

The production plan is therefore: **consolidate existing spines, delete or
demote duplicates, enforce the remaining boundaries with tests, and only then
fill missing runtime behavior.**

## Evidence Reviewed

Primary files inspected:

- `application/oms/order_manager.py`
- `application/oms/context.py`
- `application/oms/session_bridge.py`
- `application/oms/process_context.py`
- `application/oms/factory.py`
- `runtime/trading_runtime_factory.py`
- `tradex/session.py`
- `src/domain/universe.py`
- `src/domain/instruments/instrument.py`
- `src/domain/instruments/instrument_trading.py`
- `src/domain/instruments/instrument_market_data.py`
- `src/domain/instruments/instrument_streaming.py`
- `src/domain/ports/protocols.py`
- `infrastructure/providers/broker/broker_data_provider.py`
- `application/composer/market_data.py`
- `application/data/historical_coordinator.py`
- `application/streaming/orchestrator.py`
- `application/execution/execution_service.py`
- `application/composer/execution.py`
- `cli/services/broker_service.py`
- `cli/services/oms_bootstrap.py`
- `cli/services/cli_broker_facade.py`
- `api/routers/orders.py`
- `api/v2/domain_endpoints.py`
- `cli/commands/order_placement.py`
- `infrastructure/persistence/sqlite_order_store.py`
- `tests/architecture/test_phase2_oms_singleton.py`

Graphify was used first to orient around order execution, market data,
object-model wiring, OMS, strategy, and runtime composition.

## Comprehensive Review Board Scope

The requested review board is broader than the original runtime plan. Treat the
following as standing review lenses and ownership areas:

| Reviewer | Primary questions |
|----------|-------------------|
| Principal Software Engineer | Is the code understandable, cohesive, and cheap to change? |
| Staff Architect | Are boundaries, dependency direction, and runtime composition stable? |
| Quantitative Trading Architect | Can scanners, strategies, risk, portfolio, backtest, paper, and live share one model? |
| Low-Latency Systems Engineer | Are hot paths bounded, nonblocking, and instrumented? |
| Event-Driven Architecture Expert | Are events typed, versioned, idempotent, ordered where needed, and replayable? |
| Distributed Systems Expert | Are failure domains, split-brain risks, retries, locks, and recovery explicit? |
| Platform Reliability Engineer | Can operators diagnose, stop, recover, and safely resume trading? |
| QA/Test Automation Architect | Do tests prove behavior across unit, contract, integration, replay, chaos, and cert layers? |
| Security Architect | Are auth, secrets, authorization, audit, abuse prevention, and input validation sufficient? |
| Data Platform Architect | Are historical/tick/depth data quality, provenance, storage, and schemas governed? |
| Frontend Architect | Are UI state, websockets, component boundaries, and trader workflows robust? |
| DevOps/Cloud Architect | Can this be deployed, configured, monitored, rolled back, and backed up repeatably? |
| Performance Engineer | Are latency, throughput, memory, and websocket fan-out budgets known and tested? |

This document now separates:

- **Evidence-backed findings** from files already inspected.
- **Required audit tracks** that need deeper full-code review.
- **Production-readiness work** needed before real-money operation.

## Provisional Production Readiness Scorecard

Scores are provisional because the current pass did not exhaustively inspect
every subsystem. They are deliberately conservative for a real-money platform.

| Area | Score | Rationale |
|------|------:|-----------|
| Architecture | 6/10 | Strong pieces exist, but runtime composition and command surfaces are split. |
| Quant Design | 5/10 | Strategy/backtest/paper pieces exist; parity and portfolio/risk semantics need proof. |
| Code Quality | 5/10 | Good extraction in places, but duplicate spines and compatibility paths raise change cost. |
| Testing | 6/10 | Many tests exist, including architecture/chaos/e2e; need systematic coverage map and cert gates. |
| Reliability | 5/10 | OMS/recon/DLQ/locks exist; live startup and recovery invariants still need enforcement. |
| Scalability | 5/10 | Single-writer OMS is correct; market-data fan-out and multi-strategy capacity need budgets. |
| Security | 4/10 | Not enough evidence reviewed yet; real-money APIs need explicit security audit. |
| Performance | 4/10 | No complete latency/throughput/memory budget reviewed yet. |
| Maintainability | 5/10 | Domain ports help; duplicate runtime paths hurt. |
| Operational Readiness | 5/10 | Readiness/observability exist; runbooks, deployment, and incident drills need review. |

**Provisional overall readiness:** **5/10**. The platform has serious
foundations, but should not be treated as production-ready for unmanaged live
capital until the Phase 0-8 consolidation and the added full-platform audit
tracks below are complete.

## Top 20 Risks

1. Multiple runtime roots can construct subtly different system graphs.
2. Multiple public order command surfaces increase bypass and drift risk.
3. CLI live order path can omit `correlation_id` and fail before OMS admission.
4. API runtime factory appears to pass unsupported `event_bus` into
   `BrokerService`.
5. `Session.place` still contains raw `ExecutionProvider` fallback.
6. Market-data subscriptions have two ownership models.
7. Last quote/depth ownership is instrument-local in one path and runtime-owned
   in another.
8. Historical data contract allows DataFrame/domain-series ambiguity.
9. ExecutionComposer duplicates public order semantics.
10. Live/paper/replay parity is not yet guaranteed by one command service.
11. Broker-specific extension probing still exists in live API routes.
12. Event contracts and schema versioning need a full pass.
13. Recovery invariants are present but not proven across every composition path.
14. Strategy runtime can still be wired directly to lower-level OMS APIs.
15. Data quality gates for ticks, depth, OHLC, and out-of-order events need
    explicit certification.
16. Security posture has not been fully audited for real-money abuse cases.
17. Frontend websocket/state behavior has not been reviewed in this pass.
18. Performance budgets for hot paths are not yet documented or enforced.
19. Deployment/runbook/rollback practices are not yet tied to readiness gates.
20. Dirty worktree and broad ongoing changes make architecture regression easy
    unless CI gates are tightened.

## Top 20 Improvements

1. Create one `OrderCommandService` and migrate all order entry to it.
2. Create one `RuntimeHandle` registry for CLI/API/SDK.
3. Fix CLI correlation id immediately.
4. Fix API runtime factory/BrokerService construction mismatch.
5. Gate raw `ExecutionProvider` fallback behind test-only explicit opt-in.
6. Route production `Instrument.subscribe` through `StreamOrchestrator`.
7. Add central `QuoteCache` and `DepthCache`.
8. Make `HistoricalSeries` the canonical internal history type.
9. Reposition `ExecutionComposer` as internal routing/quota transport.
10. Convert paper into a first-class broker plugin behind the same runtime.
11. Add cross-surface order parity tests.
12. Add provider contract tests for history, quote, depth, subscribe, option
    chain.
13. Add broker contract/certification matrix for Dhan and Upstox.
14. Add event schema/version/idempotency audit and tests.
15. Add production-readiness gates for durable order store, event log,
    processed-trade repo, writer lock, reconciliation, and stream health.
16. Add frontend websocket/state review and test plan.
17. Add security threat model and abuse-case tests for order APIs.
18. Add performance budgets and benchmark gates.
19. Add deployment/runbook/backup/restore checklist.
20. Add architecture tests that reject reintroduced bypasses.

## Full-Platform Audit Tracks Still Required

The following tracks are now part of this plan, but require deeper evidence
collection than the initial runtime pass.

### A. Code Smell And Repository Organization Audit

Deliverable: `CODE_SMELL_REPORT.md`.

Review:

- Large files/classes/methods.
- Duplicate runtime/order/data abstractions.
- Cyclic imports and forbidden dependency directions.
- Dead compatibility shims.
- Primitive obsession in trading concepts.
- God services in CLI/API/runtime.

Method:

- Use graphify for dependency communities and affected paths.
- Use `rg --files`, line counts, import scans, and focused reads.
- Prefer deletion/demotion over new abstractions.

### B. Quant Platform Audit

Deliverable: `QUANT_PLATFORM_REVIEW.md`.

Review:

- Strategy lifecycle and multi-strategy scheduling.
- Scanner model and candidate ownership.
- Position sizing and portfolio/risk coupling.
- Live/paper/backtest/replay parity.
- PnL correctness, F&O multipliers, costs, slippage, partial fills.
- Walk-forward testing and optimization leakage risks.

Gate:

- Same signal/order scenario must run in paper and replay with equivalent
  lifecycle semantics.

### C. Event-Driven Design Audit

Deliverable: `EVENT_MODEL_REVIEW.md`.

Review:

- Event catalog, owner, producer, consumer.
- Event schema/versioning/upcasting.
- Ordering guarantees by aggregate.
- Idempotency keys.
- Replay and recovery boundaries.
- DLQ handling and poison message policy.

Gate:

- Money-state events must be typed, versioned, and replay-tested.

### D. Frontend Architecture Audit

Deliverable: `FRONTEND_REVIEW.md`.

Review:

- Component boundaries and duplication.
- State management model.
- WebSocket subscriptions and teardown.
- UI race conditions and flashing.
- Trading workflow ergonomics.
- Error, degraded, stale, reconnect, and safe-to-trade states.

Gate:

- Trader-facing screens must distinguish stale data, disconnected streams,
  rejected orders, disabled orders, and kill-switch state.

### E. Broker Integration Certification

Deliverable: `BROKER_CERTIFICATION_MATRIX.md`.

Review Dhan and Upstox:

- Place/modify/cancel.
- Order book/trade book.
- Positions/holdings/funds.
- Historical/quote/depth/option chain.
- Websocket connect/reconnect/resubscribe.
- Rate limits and retry classes.
- Capability truthfulness.

Gate:

- Each broker must pass the same contract suite; unsupported features must be
  explicit capabilities, not runtime surprises.

### F. Market Data Quality Audit

Deliverable: `MARKET_DATA_QUALITY_REVIEW.md`.

Review:

- Tick normalization.
- Duplicate/out-of-order ticks.
- Depth semantics and coalescing.
- OHLC aggregation and clock alignment.
- Gap detection.
- Provenance and data versioning.
- Storage layout and retention.

Gate:

- Every historical/streaming result has source, time, freshness, and degraded
  status.

### G. Testing Gap Analysis

Deliverable: `TESTING_GAP_ANALYSIS.md`.

Map tests by category:

- Unit.
- Contract.
- Integration.
- System/end-to-end.
- Replay determinism.
- Broker certification.
- Chaos/recovery.
- Performance/load.
- Security/API abuse.
- Frontend websocket/UI state.

Gate:

- No live-trading release without green certification scenarios and a documented
  skipped-test list.

### H. Reliability/SRE Audit

Deliverable: `RELIABILITY_ASSESSMENT.md`.

Review:

- Health/readiness/liveness.
- Kill switch behavior.
- Retry/circuit breaker policy.
- DLQ and alerting.
- Crash recovery.
- Broker outage and network partition procedures.
- Operator diagnostics and runbooks.

Gate:

- A simulated broker outage and process restart must have a rehearsed recovery
  path.

### I. Security Audit

Deliverable: `SECURITY_ASSESSMENT.md`.

Review:

- API auth/authz.
- Admin-only order operations.
- Secret loading and leakage.
- Audit trails.
- Input validation.
- SSRF/path/env injection risks.
- Trading abuse controls: symbol allowlists, order size, rate limits,
  dry-run/agent restrictions.

Gate:

- No unauthenticated or under-authorized route may place, modify, cancel, or
  disclose sensitive broker/account data.

### J. Performance And Capacity Audit

Deliverable: `PERFORMANCE_ASSESSMENT.md`.

Review:

- Order placement latency.
- Tick-to-cache and tick-to-strategy latency.
- Websocket fan-out capacity.
- Backtest throughput.
- Memory growth under subscriptions.
- Event bus handler latency.
- DB/write lock contention.

Gate:

- Define budgets before optimizing:
  - order admission p95/p99
  - tick fan-out p95/p99
  - max subscribed instruments per process
  - max strategies per process
  - replay bars/sec

### K. DevOps/Cloud/Operational Audit

Deliverable: `DEVOPS_CLOUD_REVIEW.md`.

Review:

- Environment profiles.
- Deployment topology.
- Backup/restore of OMS/event/log/data stores.
- Secrets management.
- Observability stack.
- Rollback plan.
- CI architecture gates.
- Scheduled market-day operations.

Gate:

- A fresh machine/process can be provisioned and brought to safe market-data
  mode without manual code edits.

## Current Architecture: What Is Actually There

### 1. Object Model

`src/domain/universe.py` already implements the intended product surface:

- `Session` binds provider, optional execution provider, optional OMS service,
  event bus, and status.
- `Universe` stamps instruments with those ports.
- `Session.place` prefers `OrderServicePort` and only falls back to raw
  `ExecutionProvider` for a documented legacy/test path.
- `InstrumentTradingMixin` places through `OrderServicePort` only.

Important source points:

- `Instrument._bind_session_ports` stamps `DataProvider`, `ExecutionProvider`,
  and `OrderServicePort`.
- `Session.place` checks orders-enabled status, prefers OMS, then falls back to
  execution provider.
- `InstrumentTradingMixin` refuses to trade without an OMS service.

Verdict: good spine. Keep it.

### 2. OMS / Money Path

`application/oms/order_manager.py` is a serious OMS, not a placeholder:

- `OmsOrderCommand` requires `correlation_id` outside pytest.
- `OrderManager.place_order` reserves idempotency, validates risk, submits via
  callback, records state, publishes events, and measures latency.
- Raw broker I/O happens outside the lock.
- Trade events go through `TradeRecorder` and the processed-trade repository.

`application/oms/context.py` wires:

- event bus
- order manager
- position manager
- risk manager
- reconciliation service
- DLQ monitor
- processed-trade cleanup
- daily PnL reset
- crash replay from event log

`application/oms/process_context.py` provides the process-wide singleton so
`tradex.connect`, CLI, and API can share one `TradingContext`.

Verdict: the OMS is the center of the production runtime. The plan should
protect it and remove bypass confusion.

### 3. Broker Runtime

The broker layer has evolved substantially:

- `BrokerService` owns lifecycle and bootstrap.
- `OmsBootstrap` constructs live risk manager, fail-closed capital function,
  TradingContext, event log, websocket services, reconciliation, and HTTP
  observability.
- `adapter_factory` lets brokers register data/execution adapters and
  extensions.
- Broker capabilities are modeled in `domain.capabilities`.

Verdict: good operational pieces exist, but ownership is split between
`BrokerService`, `runtime.trading_runtime_factory`, `runtime.session_infra`,
and `tradex.session`.

### 4. Market Data Runtime

There are two partially separate systems:

- The domain-object path:
  `Instrument.subscribe` -> `DataProvider.subscribe` ->
  `BrokerDataProvider.subscribe` -> `gateway.stream`.
- The platform path:
  `MarketDataComposer` -> `HistoricalDataCoordinator` and `StreamOrchestrator`.

`StreamOrchestrator` already has the better production semantics: session
health, reconnect, failover, nonblocking consumers, centralized lifecycle.

Verdict: converge instrument subscriptions and quote state onto the platform
market-data runtime. Do not create another market-data service.

### 5. Historical Data

The code already has:

- `InstrumentHistory` facade returning `HistoricalSeries`.
- `HistoryService` fallback normalization.
- `HistoricalDataCoordinator` for multi-broker chunk planning, quota gating,
  provenance, merge conflicts, and degraded results.

But `DataProvider.get_history` protocol says it returns domain bars, while
`BrokerDataProvider.get_history` returns `pd.DataFrame`. The facades compensate,
but the contract is still muddy.

Verdict: make `get_history_series` the primary contract and treat DataFrame as
export-only.

### 6. Execution Surfaces

There are too many order-entry facades:

- `domain.universe.Session.place`
- `InstrumentTradingMixin.buy/sell`
- `OmsOrderService`
- `ExecutionService`
- `ExecutionComposer`
- `CliBrokerFacade.place_order`
- API `/orders`
- API v2 domain endpoints
- CLI `place-order`

Most now route through OMS or try to, but the user-visible command surface is
still wider than necessary.

Verdict: keep one public order command surface. Everything else becomes an
adapter over it or gets deprecated.

## High-Priority Findings

### F1. CLI live order path can fail because it omits `correlation_id`

`OmsOrderCommand.__post_init__` raises outside pytest when `correlation_id` is
missing. `CliBrokerFacade.place_order` builds `OrderRequest` without one. Since
`OrderRequest` is an alias of `OmsOrderCommand`, real CLI live placement can
raise before risk/submit.

Evidence:

- `application/oms/order_manager.py:75-90`
- `cli/services/cli_broker_facade.py:160-168`

Plan:

- Generate `correlation_id=f"cli:{uuid.uuid4().hex[:12]}"` in
  `CliBrokerFacade.place_order`.
- Add a non-pytest-style unit test that clears `PYTEST_CURRENT_TEST` around the
  command construction or directly asserts the facade supplies a correlation id.

### F2. `TradingRuntimeFactory.build_for_api` appears to pass an unsupported
constructor arg to `BrokerService`

`TradingRuntimeFactory.build_for_api` calls `BrokerService(event_bus=event_bus)`.
The inspected `BrokerService.__init__` accepts only
`authorize_risk_fail_open`.

Evidence:

- `runtime/trading_runtime_factory.py:81-88`
- `cli/services/broker_service.py:67-80`

Plan:

- Either add `event_bus` injection to `BrokerService.__init__` and wire it
  through `OmsBootstrap`, or change API runtime composition to inject the bus
  elsewhere.
- Add a smoke test for `TradingRuntimeFactory.build_for_api(skip_parity_gate=True)`
  that does not touch live credentials.

### F3. Market data has two runtimes with different ownership models

Instrument subscriptions update each individual instrument's local state via
provider callbacks. Separately, `StreamOrchestrator` owns production stream
session lifecycle and health.

Evidence:

- `src/domain/instruments/instrument_streaming.py:48-97`
- `infrastructure/providers/broker/broker_data_provider.py:155-199`
- `application/streaming/orchestrator.py:1-27`
- `application/composer/market_data.py:101-133`

Risk:

- Duplicate subscriptions for the same instrument.
- No central last-quote owner.
- Reconnect/health semantics differ between instrument-created streams and
  orchestrator streams.

Plan:

- Introduce a `MarketDataRuntimeProvider` that implements `DataProvider` by
  delegating subscription and historical requests to `MarketDataComposer`.
- Keep `Instrument.subscribe` API unchanged; swap the provider implementation.
- Add a central quote/depth cache behind that provider.
- Then demote `BrokerDataProvider.subscribe` to legacy/test path.

### F4. Historical data contract is inconsistent

The protocol says `DataProvider.get_history` returns `list[HistoricalBar]`;
`BrokerDataProvider.get_history` returns `pd.DataFrame`.

Evidence:

- `src/domain/ports/protocols.py:94-108`
- `infrastructure/providers/broker/broker_data_provider.py:104-121`

Plan:

- Make `get_history_series` required on production providers.
- Keep `get_history` as a compatibility/export method with documented
  DataFrame tolerance until removed.
- Add contract tests for every production `DataProvider`:
  `get_history_series -> HistoricalSeries`, `to_dataframe()` works,
  provenance populated.

### F5. `Session.place` still has a raw `ExecutionProvider` fallback

The fallback is documented as legacy/test-only, but it still exists in domain
runtime code.

Evidence:

- `src/domain/universe.py:349-370`

Risk:

- A non-test composition can create a `Session` with an execution provider and
  no OMS, then place orders outside OMS/risk.

Plan:

- Gate fallback behind explicit `allow_legacy_execution_fallback=True` on
  `Session`, default false.
- Update tests that need direct EP fallback to pass the flag.
- Add architecture test: live or normal session cannot place without
  `OrderServicePort`.

### F6. ExecutionComposer duplicates public order semantics

`ExecutionComposer` is OMS-aware and requires an order manager, but it exposes a
parallel async order API with routing/quota. CLI cancel/modify still use it
directly.

Evidence:

- `application/composer/execution.py:23-87`
- `cli/commands/order_placement.py:187-240`
- `api/routers/orders.py:352-430`

Plan:

- Reposition `ExecutionComposer` as transport/routing support only.
- Create one `OrderCommandService` public application service:
  `place`, `cancel`, `modify`.
- Internally it calls OMS first and uses composer only for broker routing/quota
  submit callbacks.
- Migrate API/CLI to `OrderCommandService`.
- Mark direct `ExecutionComposer.place_order` use outside tests as deprecated
  via architecture test.

### F7. Runtime composition is still split

`runtime.trading_runtime_factory` claims to be single composition root, but
`tradex.connect`, `BrokerService`, API v2 session wiring, and session infra also
bootstrap pieces.

Evidence:

- `runtime/trading_runtime_factory.py:1-5`
- `tradex/session.py:218-330`
- `api/v2/domain_endpoints.py:23-44`

Plan:

- Define `RuntimeHandle` as the one concrete process root.
- `tradex.connect` should first look for the active `RuntimeHandle`; if absent,
  it may build paper/session-only runtime, but live trade mode must require the
  handle.
- API startup and CLI startup both call the same factory.
- Domain API v2 gets session from `RuntimeHandle.session`, not a module global.

## Target Integration Shape

```text
RuntimeHandle
  - lifecycle
  - event_bus
  - broker_registry / capabilities
  - broker sessions
  - market_data_runtime
  - trading_context
  - order_command_service
  - domain_session
  - strategy_runtime
  - observability

User/CLI/API/Agent
  -> domain_session / order_command_service
  -> OrderIntent
  -> OMS OrderManager
  -> broker submit callback via ExecutionProvider / routed transport
  -> events
  -> position/risk/portfolio
```

No user-facing path should call broker gateway order methods directly.

## Extensive Implementation Plan

### Phase 0: Stop Money-Path Footguns

Goal: fix direct correctness issues before architecture work.

Tasks:

1. Fix CLI correlation id.
   - File: `cli/services/cli_broker_facade.py`
   - Add `uuid` import and `correlation_id=f"cli:{uuid.uuid4().hex[:12]}"`.
   - Test: `cli/tests/test_b7_oms_wireup.py` or new focused test.

2. Fix or remove unsupported API runtime event-bus injection.
   - Files: `runtime/trading_runtime_factory.py`,
     `cli/services/broker_service.py`.
   - Preferred: add optional `event_bus` to `BrokerService.__init__` and use it
     during TradingContext creation.
   - Test: runtime API factory smoke test.

3. Make legacy raw execution fallback explicit.
   - File: `src/domain/universe.py`
   - Add constructor flag `allow_legacy_execution_fallback=False`.
   - Fail closed if `order_service is None` and fallback not allowed.
   - Update tests that intentionally exercise fallback.

Exit criteria:

- CLI place path always supplies correlation id.
- API runtime factory can construct without TypeError.
- Architecture test proves no production order path uses raw EP fallback.

### Phase 1: One Public Order Command Surface

Goal: all CLI/API/SDK order operations use the same application service.

Create or promote:

- `application/trading/order_command_service.py`

Responsibilities:

- Accept domain `OrderIntent`, `ModifyOrderRequest`, cancel order id.
- Resolve order manager from `TradingContext`.
- Build submit/modify/cancel callbacks using execution provider or
  ExecutionComposer routing.
- Enforce correlation id.
- Return one `OrderResult` type.

Migration:

- `InstrumentTradingMixin` and `Session.place` continue using
  `OrderServicePort`; implementation becomes `OrderCommandService`.
- `OmsOrderService` can become a thin adapter or be renamed into the new
  service.
- API `/orders`, API v2 order endpoint, CLI place/cancel/modify all call this
  service.
- `ExecutionComposer.place_order` becomes internal transport helper or
  deprecated for direct callers.

Tests:

- `application/oms/tests/test_order_path_parity.py` expands to cover:
  SDK instrument buy, API place, CLI place, strategy order.
- One test asserts all paths update the same `OrderManager` instance.
- Architecture grep test rejects direct gateway `.place_order(` outside
  adapters/tests.

Exit criteria:

- One order command service is the only public application order surface.
- `ExecutionComposer` is no longer imported by CLI command handlers except as
  injected transport inside the service.

### Phase 2: RuntimeHandle As Single Composition Root

Goal: replace scattered process roots with one runtime object.

Work:

- Expand `runtime.trading_runtime_factory.Runtime` into a real `RuntimeHandle`:
  - `domain_session`
  - `market_data`
  - `order_commands`
  - `trading_context`
  - `broker_infrastructure`
  - `lifecycle`
  - `readiness`
- Register this handle in a process registry, similar to `process_context`.
- Have `tradex.connect`:
  - return `RuntimeHandle.domain_session` when a handle exists;
  - build standalone paper runtime when broker is paper;
  - refuse live trade without the handle.
- Have FastAPI and CLI call the same factory.
- Remove API v2 module-global `set_session` in favor of dependency on the
  handle.

Files:

- `runtime/trading_runtime_factory.py`
- `runtime/process_runtime.py` new small registry
- `tradex/session.py`
- `api/deps.py`
- `api/v2/domain_endpoints.py`
- `cli/services/compose.py`

Tests:

- Runtime smoke tests for paper, market live-disabled, trade requires OMS.
- API and CLI both see the same `trading_context.order_manager`.
- `tradex.connect("dhan", mode="trade")` fails with a structured error when
  no runtime is registered.

Exit criteria:

- One runtime registry per process.
- `BrokerService` becomes a collaborator of the runtime, not the runtime itself.

### Phase 3: Converge Market Data Runtime

Goal: one owner for subscriptions, last quote, depth, reconnect, and history.

Work:

1. Implement `MarketDataRuntimeProvider`.
   - Implements `DataProvider`.
   - `get_quote` reads central quote cache, then broker snapshot.
   - `subscribe` delegates to `StreamOrchestrator`.
   - `get_history_series` delegates to `MarketDataComposer.fetch_historical`.
   - `get_depth` uses central depth cache/snapshot.

2. Add central caches:
   - `QuoteCache`
   - `DepthCache`
   - key: `InstrumentId`
   - owner: market data runtime only

3. Add consumer bridge:
   - `StreamConsumer` updates quote/depth caches.
   - Then calls instrument user callbacks.

4. Keep legacy provider direct subscription behind a compatibility flag.

Files:

- `application/market_data/runtime_provider.py` new
- `application/market_data/quote_cache.py` new
- `application/market_data/depth_cache.py` new
- `runtime/trading_runtime_factory.py`
- `tradex/session.py`
- `src/domain/instruments/instrument_streaming.py` minimal/no API change

Tests:

- One instrument subscription registers one orchestrator subscription.
- Two instruments for same id share central subscription.
- Reconnect replays interest set.
- `stock.quote` after stream tick reads latest cache.
- `stock.unsubscribe` removes consumer but only closes broker stream when last
  consumer leaves.

Exit criteria:

- `Instrument.subscribe` no longer talks directly to broker gateway stream in
  production runtime.
- Stream health is visible from runtime health.

### Phase 4: Normalize Historical Data Contract

Goal: `HistoricalSeries` is the canonical internal history type.

Work:

- Require `get_history_series` in production providers.
- Update `BrokerDataProvider` to implement `get_history_series` by normalizing
  `gateway.history` DataFrame into `HistoricalSeries`.
- Keep `get_history` as compatibility export or rename to `get_history_frame`.
- Route `InstrumentHistory._fetch` through `get_history_series` only in
  production providers.
- Add provenance requirements to provider contract tests.

Files:

- `src/domain/ports/protocols.py`
- `infrastructure/providers/broker/broker_data_provider.py`
- `brokers/paper/data_provider.py`
- `infrastructure/providers/*`
- `src/domain/candles/instrument_history.py`

Tests:

- Contract test for all `DataProvider`s:
  - `get_history_series` returns `HistoricalSeries`
  - `series.to_dataframe()` exports correctly
  - empty/degraded series is explicit, not silent `None`

Exit criteria:

- No production code assumes bare DataFrame as internal history representation.

### Phase 5: Broker Plugin Model Cleanup

Goal: adding a broker should not touch core runtime files.

Current good pieces:

- `infrastructure/adapter_factory.py` broker registration.
- `domain.capabilities` canonical model.
- Broker extensions.

Work:

- Move remaining broker-specific imports out of generic runtime paths where
  possible.
- Replace `_ensure_broker_registered` manual imports in `tradex/session.py`
  with plugin discovery or a tiny broker registry bootstrap.
- Define broker plugin contract:
  - build gateway/session
  - data adapter class
  - execution provider class
  - capabilities
  - env profile
  - contract test suite

Files:

- `infrastructure/broker_plugin.py`
- `tradex/session.py`
- `brokers/{dhan,upstox,paper}/__init__.py`
- `infrastructure/adapter_factory.py`

Tests:

- New fake broker plugin can register without editing core files.
- Capability descriptor boot validation fails on inconsistent capability claims.

Exit criteria:

- Adding broker code requires only a broker package and tests.

### Phase 6: Recovery And Persistence Hardening

Goal: crash recovery is deterministic and audited.

Good current pieces:

- `SqliteOrderStore` has WAL and writer lock.
- `TradingContext` replays event log into OMS.
- Reconciliation placement gate exists.

Work:

- Verify every production `TradingContext` is built with:
  - `durable_order_store`
  - processed trade repository with durable path
  - event log
  - reconciliation service for live
- If any composition path omits those in live mode, fail startup.
- Add `RuntimeHealth` status:
  - writer lock held
  - reconciliation ready
  - event log active
  - processed trade repo durable
  - websocket health

Files:

- `cli/services/oms_bootstrap.py`
- `application/services/production_readiness.py`
- `runtime/production_config.py`
- `application/oms/context.py`

Tests:

- Kill/restart recovery test:
  - place order with fake broker ack
  - persist
  - rebuild runtime
  - order appears in OMS
  - placement blocked until reconciliation ready
- Duplicate trade replay does not double position.

Exit criteria:

- Live mode cannot start without durable money-state components.

### Phase 7: Strategy, Replay, And Paper Parity

Goal: live, paper, and replay share order/risk/portfolio semantics.

Current pieces:

- `analytics/strategy`
- `application/trading/trading_orchestrator.py`
- `application/execution/execution_mode_adapter.py`
- `analytics/replay`
- `brokers/paper`

Work:

- Make paper broker a real broker plugin behind same runtime handle.
- Ensure `ExecutionModeAdapter` is only mode-specific fill behavior, not a
  second order path.
- Make strategy runtime call `OrderCommandService`, not `OrderManager` directly.
- Make replay use `VirtualClock`, pinned data version, and same strategy
  evaluator path.

Tests:

- Same strategy signal in paper and replay creates equivalent order lifecycle.
- Backtest does not call live broker or gateway methods.
- Replay determinism golden: same input data + seed -> same trades/equity.

Exit criteria:

- Strategy code never imports broker modules or raw gateway types.

### Phase 8: Architecture Enforcement

Goal: prevent the codebase from drifting back.

Add/extend tests:

- No `gateway.place_order` outside broker adapters, transport submit helpers,
  and tests.
- No `brokers.*` imports in `domain`, `analytics`, or generic application
  modules.
- No direct construction of `OrderManager` in production entry points except
  runtime/OMS composition.
- No live `build_oms_service(... allow_unsafe_standalone=True ...)` outside
  tests.
- `DataProvider.get_history_series` contract required.
- `Instrument.subscribe` production provider goes through market data runtime.

Tools:

- Keep grep-style architecture tests first. Do not add heavy architecture
  frameworks unless grep tests become unmaintainable.

Exit criteria:

- CI rejects new bypasses.

### Phase 9: Full Code Smell And Dependency Audit

Goal: complete the code-quality portion of the review board prompt with exact
files, severity, and refactoring actions.

Work:

- Generate module/file inventory by bounded context.
- Rank largest files/classes/functions.
- Identify duplicate services and compatibility shims.
- Identify forbidden imports and dependency cycles.
- Identify dead or unowned code paths.
- Produce a severity-ranked code smell report.

Tests/gates:

- Architecture tests for forbidden dependencies.
- Deletion candidates must have either no references or a deprecation path.

Exit criteria:

- `CODE_SMELL_REPORT.md` exists with exact files/modules and ranked actions.

### Phase 10: Frontend, API, And Trader Workflow Review

Goal: cover the frontend review requested by the board prompt.

Work:

- Inventory frontend/app directories, widgets, websocket consumers, and API
  state flows.
- Review component duplication, state ownership, hook usage, reconnect/stale
  handling, and UI-safe trading states.
- Ensure the UI distinguishes market-data-only mode, trade mode, kill switch,
  stale data, broker disconnected, order rejected, and reconciling.
- Propose shared component/hook structure only where duplication is real.

Tests/gates:

- Frontend smoke tests for websocket reconnect, stale quote display, order
  failure display, and disabled-order states.
- API contract tests for every UI trading workflow.

Exit criteria:

- `FRONTEND_REVIEW.md` exists and every trading workflow has an explicit UI
  state model.

### Phase 11: Security And Abuse-Case Review

Goal: treat this as real money, not a demo API.

Work:

- Review auth/authz on every API route that reads account data or changes
  orders.
- Review secret loading and accidental logging.
- Review input validation at all broker/API/agent boundaries.
- Add order-abuse controls: max notional, max quantity, symbol allowlists,
  strategy/agent rate limits, and dry-run restrictions.
- Ensure audit logs include actor, source, correlation id, and order id.

Tests/gates:

- Security tests for unauthenticated and under-authorized place/modify/cancel.
- Fuzz-ish input tests for symbol, exchange, quantity, price, dates, and paths.
- Secret leakage scan in logs/config outputs.

Exit criteria:

- `SECURITY_ASSESSMENT.md` exists and all P0/P1 API trading risks are fixed or
  blocked by feature gates.

### Phase 12: Performance, Load, And Capacity Program

Goal: define and enforce budgets before tuning.

Work:

- Define budgets for order admission, broker submit, tick fan-out,
  quote-cache update, strategy evaluation, backtest throughput, and memory.
- Add repeatable benchmark commands.
- Add websocket fan-out load test.
- Add memory leak regression for long-running subscriptions.
- Add DB/event-log write contention test.

Tests/gates:

- Nightly benchmark report.
- Release gate fails on material regression in money or stream hot paths.

Exit criteria:

- `PERFORMANCE_ASSESSMENT.md` exists with baseline numbers and capacity limits.

### Phase 13: Operational Certification And Runbooks

Goal: make production behavior operationally boring.

Work:

- Write safe-start, safe-stop, kill-switch, broker outage, stale data,
  reconciliation drift, token expiry, and restore runbooks.
- Define backup/restore for OMS store, event log, processed trade ledger, and
  data lake.
- Define deployment profiles: paper, market-data live, live-trade.
- Tie readiness gates to runbook state.

Tests/gates:

- Process restart drill.
- Broker disconnect drill.
- Token expiry drill.
- Restore-from-backup drill in paper/sandbox mode.

Exit criteria:

- `RELIABILITY_ASSESSMENT.md` and `DEVOPS_CLOUD_REVIEW.md` exist.
- Operators can recover paper/sandbox runtime from documented steps.

### Phase 14: Final Production Readiness Board

Goal: produce the deliverables requested by the expert-board prompt.

Deliverables:

1. `EXECUTIVE_SUMMARY.md`
2. `ARCHITECTURE_REVIEW_REPORT.md`
3. `QUANT_PLATFORM_REVIEW.md`
4. `CODE_SMELL_REPORT.md`
5. `TESTING_GAP_ANALYSIS.md`
6. `RELIABILITY_ASSESSMENT.md`
7. `SECURITY_ASSESSMENT.md`
8. `PERFORMANCE_ASSESSMENT.md`
9. `REFACTORING_ROADMAP.md`
10. `PRODUCTION_READINESS_SCORECARD.md`
11. `PRIORITIZED_ACTION_PLAN.md`

Exit criteria:

- Scorecard is evidence-backed, not aspirational.
- Top 20 risks and top 20 improvements are linked to code/docs/tests.
- Quick wins, 1-4 week improvements, and 1-6 month strategy are separated.

## Proposed Delivery Order

1. Phase 0: correctness fixes.
2. Phase 1: one order command surface.
3. Phase 2: RuntimeHandle registry and shared session.
4. Phase 3: market-data runtime convergence.
5. Phase 4: history contract cleanup.
6. Phase 5: broker plugin cleanup.
7. Phase 6: recovery hardening.
8. Phase 7: strategy/paper/replay parity.
9. Phase 8: architecture enforcement stays active throughout.
10. Phase 9: full code smell and dependency audit.
11. Phase 10: frontend/API/trader workflow review.
12. Phase 11: security and abuse-case review.
13. Phase 12: performance/load/capacity program.
14. Phase 13: operational certification and runbooks.
15. Phase 14: final production readiness board.

## What Not To Build Yet

- No microservices.
- No Kafka/event sourcing rewrite.
- No new broker abstraction if `adapter_factory` + plugin registration covers
  it.
- No new market-data runtime; use `StreamOrchestrator` and
  `HistoricalDataCoordinator`.
- No new order manager; harden the existing OMS.
- No broad package move until command and runtime ownership are stable.

## First Implementation Slice

Smallest high-value slice:

1. Fix CLI correlation id.
2. Fix API runtime factory event-bus injection mismatch.
3. Add architecture test for no raw `Session.place` execution fallback unless
   explicitly allowed.
4. Add `OrderCommandService` as an adapter over existing `OmsOrderService`
   without deleting old call sites.
5. Migrate one API place path and one CLI place path to it.
6. Create a review-output folder and stub the eleven board deliverables so each
   future audit finding has a home.

This gives immediate correctness and starts consolidation without a risky
rewrite.

## Time-Horizon Plan

### Quick Wins: 1-2 Days

- Fix CLI correlation id.
- Fix API runtime factory/BrokerService constructor mismatch.
- Add raw-execution fallback architecture test.
- Add direct gateway order-call architecture test.
- Add README links to the board deliverables.
- Add scorecard stub with provisional/current scores.

### Medium-Term: 1-4 Weeks

- Implement `OrderCommandService`.
- Consolidate API/CLI/SDK place/cancel/modify onto it.
- Introduce `RuntimeHandle` registry.
- Route production subscriptions through `StreamOrchestrator`.
- Normalize `get_history_series` contracts.
- Build broker certification matrix for Dhan/Upstox/paper.
- Complete testing gap analysis.
- Complete security review of order/account APIs.

### Long-Term: 1-6 Months

- Complete market-data runtime convergence.
- Complete live/paper/replay parity.
- Add performance budgets and nightly capacity tests.
- Add operational runbooks and restore drills.
- Mature plugin system so future brokers/strategies/indicators require no core
  edits.
- Re-score production readiness with evidence.

## Review Summary

The codebase is closer to the target architecture than the first-principles
blueprint alone suggests. The institutional move is not to invent architecture;
it is to make the existing architecture singular:

- one runtime handle
- one OMS
- one public order command service
- one market-data runtime
- one canonical history type
- one broker plugin contract
- one set of architecture tests that keep it that way
- one production readiness board that scores the full platform honestly
