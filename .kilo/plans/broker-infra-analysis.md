# Broker Infrastructure Analysis Plan

## Goal
Produce a comprehensive analysis document of the **Trade_XV2** codebase, with primary focus on **broker infrastructure**, architecture, data flow, risks, and improvement opportunities. Deliverable: a structured Markdown report (e.g., `docs/analysis/broker-infra-analysis.md`).

---

## Phase 1 — Inventory & Ground Truth
Objective: Confirm and catalog all broker-related code, verify consistency, and understand every file's role.

### Tasks
1. **Directory Map** — Enumerate every file under `brokers/`, `datalake/`, `cli/commands/`, and `config/`.
   - Tool: `find` or `glob`
   - Output: File list with 1-line purpose annotation

2. **Domain Single-Source Verification** — Confirm ALL cross-boundary types originate in `brokers/common/core/domain.py/models.py/types.py/requests.py/reconciliation.py/constants.py`.
   - Tool: `grep` for imports from `brokers.dhan.domain.*`, `brokers.upstox.domain.*`, `brokers.paper.domain.*`
   - Validate: ruff rules (E, W, F, I, B, UP, G, N, RUF, S, C4, SIM, TID) define banned imports — locate and review those rules in config

3. **Gateway Contract Audit** — In `brokers/common/gateway.py`, extract the full `MarketDataGateway` ABC method list (~20 methods).
   - Verify Dhan's `BrokerGateway` and Upstox's `BrokerGateway` each implement every method.
   - Tool: `grep` for `class.*Gateway` and `def <method>` in each adapter file

4. **Circuit Breaker Map** — In `brokers/dhan/http_client.py`, extract the 3 category names, thresholds, and where they're invoked.
   - Verify other adapters (Upstox, Paper) don't skip resilience.

5. **Capability Registry Review** — In `brokers/upstox/`, find `Capability` enum and `_register_capability` calls. Document which capabilities each Upstox sub-module claims.

---

## Phase 2 — Deep Read: Core Broker Infra
Objective: Produce annotated summaries of every core infra module.

### Tasks
1. **Lifecycle (`brokers/common/lifecycle/`)**
   - Read `lifecycle/__init__.py`, `lifecycle/manager.py`, `lifecycle/protocol.py`
   - Document: `ManagedService` protocol methods, `LifecycleManager` start/stop ordering, drain semantics, `HealthState` transitions

2. **Event Bus (`brokers/common/event_bus/`)**
   - Read `event_bus/__init__.py`, `event_bus/bus.py`, `event_bus/dead_letter.py`, `event_bus/event_metrics.py`
   - Document: `EventType` enum completeness, pub/sub mechanics, thread-safety guarantees, dead-letter retry policy, idempotency via `ProcessedTradeRepository`

3. **OMS (`brokers/common/oms/`)**
   - Read `oms/context.py`, `oms/order_manager.py`, `oms/position_manager.py`, `oms/risk_manager.py`, `oms/factory.py`
   - Document: `TradingContext` composition, `OrderManager` idempotency key strategy, `PositionManager` TRADE_APPLIED subscription rationale, `RiskManager` check functions and their RLock scope, PnL reset schedule

4. **Resilience (`brokers/common/resilience/`)**
   - Read `resilience/circuit_breaker.py`, `resilience/rate_limiter.py`, `resilience/retry.py`
   - Document: CB state transitions, failure threshold defaults, token bucket params, retry backoff formula

5. **Auth (`brokers/common/auth/`)**
   - Read `auth/auth_manager.py`, `auth/token_state_store.py`
   - Document: TOTP vs JWT flows, token refresh atomicity, state persistence location

### Output
1 file: `docs/analysis/core-infra-deep-read.md`

---

## Phase 3 — Deep Read: Broker Adapters
Objective: Annotate Dhan and Upstox adapters at the sub-module level, plus the paper fallback.

### Tasks: Dhan (`brokers/dhan/`)
1. **Factory & Connection** — Read `dhan/factory.py`, `dhan/connection.py`.
   - Document: `BrokerFactory.create()` construction sequence (URL registry → SettingsLoader → AuthManager → HttpClient → Connection), 16 sub-adapters wiring, `DhanConnection` event-driven orchestration

2. **Token Refresh** — Read `dhan/token_scheduler.py`, `dhan/token_scheduler.py` callback chain.
   - Verify: On refresh, all receivers (HTTP client, market feed, order stream, depth_20, depth_200) are updated atomically; state written to `.env.local` and `runtime/dhan-token-state.json`

3. **HTTP Client** — Read `dhan/http_client.py`.
   - Document: 3 CB categories, retry hook, token refresh interceptor, URL resolution (local vs sandbox vs live)

4. **WebSocket Services** — Read `dhan/websocket.py`, `dhan/depth_20.py`, `dhan/depth_200.py`.
   - Document: `DhanMarketFeed` topic subscription model, `DhanOrderStream`, `PollingMarketFeed` fallback, depth feed differences (20 vs 200), `ManagedService` lifecycle integration

5. **Sub-Adapters** — Read `dhan/orders.py`, `dhan/market_data.py`, `dhan/historical.py`, `dhan/portfolio.py`, `dhan/margin.py`, `dhan/options.py`, `dhan/futures.py`, `dhan/alerts.py`, `dhan/super_orders.py`, `dhan/forever_orders.py`, `dhan/conditional_triggers.py`.
   - For each: document Dhan API endpoint mapped, request/response shape, capability claim, error handling

6. **Symbol Resolution & Instruments** — Read `dhan/resolver.py`, `dhan/loader.py`, `dhan/segments.py`.
   - Document: exchange→segment mapping, instrument cache lifecycle, search algorithm

7. **Reconciliation** — Read `dhan/reconciliation.py`.
   - Document: drift detection algorithm, periodicity, event types published

### Tasks: Upstox (`brokers/upstox/`)
1. **Central Broker** — Read `upstox/broker.py`.
   - Document: ~25 REST client instantiations, adapter wiring, `Capability` registration pattern

2. **Gateway** — Read `upstox/gateway.py`.
   - Document: `UpstoxBrokerGateway` implements `MarketDataGateway`, method dispatch logic

3. **WebSocket** — Read `upstox/websocket/` (multiplexer, decoder, authorizer, limits, reconnect).
   - Document: v3 binary protocol decoding, subscription limits (Plus plan aware), auto-reconnect strategy

4. **Orders & GTT** — Read `upstox/orders/order_client.py`, `upstox/orders/order_command/`, `upstox/orders/gtt.py`, `upstox/orders/slice.py`.
   - Document: idempotency cache, GTT trigger model, slice order batching

5. **Extended Capabilities** — Read `upstox/extended.py`.
   - Document: Broker-specific extras exposed

### Tasks: Paper (`brokers/paper/`)
1. Read `paper/mock_broker.py`, `paper/paper_gateway.py`, `paper/paper_orders.py`, `paper/paper_portfolio.py`, `paper/paper_market_data.py`.
   - Document: simulation fidelity, state isolation, how it's used in strategy testing

### Output
2 files: `docs/analysis/dhan-adapter-deep-read.md`, `docs/analysis/upstox-adapter-deep-read.md`

---

## Phase 4 — Data Flow & Integration

### Tasks
1. **Order Placement Trace** — Manually trace a full order placement from CLI to broker execution and confirmation.
   - Start: `cli/commands/orders.py` (or equivalent) → `cli/services/broker_service.py` → `cli/services/oms_service.py` → `brokers/common/oms/order_manager.py` → `brokers/common/oms/risk_manager.py` → `brokers/dhan/orders.py` (or Upstox) → event bus → position tracking
   - Document: exact function names at each hop, exception paths, event types emitted

2. **Market Data Trace** — Trace quote/ltp/depth request from CLI to broker response.
   - Start: CLI → DataLakeGateway (cached) vs BrokerGateway (live) routing
   - Document: intelligent gateway fallback logic (`brokers/common/intelligent_gateway.py`)

3. **Token Refresh Broadcast** — Trace how a single token refresh propagates all components.

4. **Reconciliation Trace** — Trace periodic reconciliation loop.

5. **Data Lake Write Path** — Trace how live market data is normalized and written to Parquet.
   - `datalake/io.py` → `datalake/normalize.py` → `datalake/schema.py`
   - Document: hive partition layout, PyArrow schema validation, WAL journaling

### Output
1 file: `docs/analysis/data-flow-traces.md`

---

## Phase 5 — Risk, Resilience, Failure Modes

### Tasks
1. **Circuit Breaker Failure Matrix** — For each CB category (read/write/admin), document:
   - Threshold and timeout defaults
   - What happens when CB opens (fallback, error propagation, user notification)
   - Recovery path (half-open → closed)

2. **Kill-Switch Behavior** — Read `brokers/common/oms/risk_manager.py` kill-switch implementation.
   - Document: atomic flip semantics, who can flip (event handler vs external), market data feed behavior when kill-switch is active

3. **Idempotency Under Concurrency** — Read `event_bus/processed_trade_repository.py`.
   - Document: unique key composition, SQLite locking, cleanup thread

4. **Token Refresh Atomicity** — Analyze the broadcast chain in `dhan/connection.py`.
   - Identify: any race condition where old token is used during broadcast gap? Is `update_token()` thread-safe?

5. **Memory / Thread Leaks** — Audit `LifecycleManager.close()` for all registered services.
   - Are background threads joined? Are WebSocket connections closed? Is there a drain timeout?

### Output
1 file: `docs/analysis/risk-and-failure-modes.md`

---

## Phase 6 — Configuration & Secrets Audit

### Tasks
1. **Env Var Inventory** — Scan all Python files for `os.environ.get`, `os.getenv`, `.env.local`, `.env`, `config`.
   - Document: every env var, which broker uses it, default behavior

2. **Secrets Storage Review** — Review `config/dhan-pin.txt`, `config/dhan-totp-secret.txt`, `runtime/dhan-token-state.json`, `.env.local`.
   - Note: gitignored, plaintext. Flag as risk.

3. **Dual-Loading Conflict** — Dhan uses `.properties` files; CLI uses `.env.local`. Are they kept in sync automatically? Where?

4. **Endpoint Registry** — Read `config/endpoints.py`.
   - Document: all REST + WS URLs, how environment (local/sandbox/live) is selected

### Output
1 file: `docs/analysis/configuration-and-secrets-audit.md`

---

## Phase 7 — Test Coverage & Gaps

### Tasks
1. **Coverage Map by Module** — Read `pyproject.toml` coverage config and existing test files.
   - For each major module under `brokers/`, `datalake/`, `cli/`, list: existing tests, what's covered, what's NOT covered

2. **Chaos Tests Review** — Read `tests/chaos/` (10 tests).
   - Document: failure modes tested, which adapter's failure modes are MISSING

3. **Architecture Tests Review** — Read `tests/architecture/`.
   - Verify: test enforcement of single-source domain, gateway ABC compliance, no scattered dotenv

4. **Integration Tests Review** — Read `tests/integration/`.
   - Document: what integrations exist (event replay, kill-switch, reconciliation, gateway contract)

### Output
1 file: `docs/analysis/test-coverage-and-gaps.md`

---

## Phase 8 — Improvement Recommendations

### Tasks
1. **Technical Debt**
   - Document: TODO/FIXME/HACK comments found across broker code
   - Flag: config dual-loading inconsistency, plaintext secrets, missing type hints in adapters

2. **Scalability**
   - Identify: synchronous gateway facade in a multi-threaded context; are there blocking calls that could be async?
   - Upstox v2 vs v3 client fragmentation

3. **Observability**
   - Catalog: existing metrics (EventMetrics, HttpObservabilityServer), what's missing for production (traces, structured logging, correlation ID propagation to HTTP headers)

4. **Resilience Enhancements**
   - Suggest: Kafka/Redis-backed `DeadLetterQueue` for multi-instance, exponential backoff tuning by HTTP status code, CB half-open sleep scheduler

5. **Security**
   - Suggest: secrets vault integration, token encryption at rest, mTLS for broker API calls

### Output
1 file: `docs/analysis/improvement-recommendations.md`

---

## Deliverable Assembly

1. Merge all Phase outputs into one master document: `docs/analysis/broker-infra-analysis.md`
2. Executive summary (1 page): architecture overview, top 3 strengths, top 5 risks, top 5 recommendations
3. Per-section diagrams (text/Mermaid): ordering flow, event bus topology, token refresh broadcast, reconciliation loop
4. Glossary of domain types from `brokers/common/core/`

---

## Validation & Review
- Re-run `ruff check` and `mypy` from `pyproject.toml` to ensure no regressions during analysis (read-only, no edits)
- Cross-reference all findings against actual source code to avoid stale assumptions
- Flag any discrepancies between `MarketDataGateway` ABC methods and adapter implementations

---

## Open Questions for User
1. Should the analysis be formatted as an ADR-style technical brief or a standard engineering report?
2. Should metrics/observability gaps include a proposed Prometheus / OpenTelemetry instrumentation plan?
3. Should security recommendations focus only on local-run concerns, or also cover any API server exposure?
