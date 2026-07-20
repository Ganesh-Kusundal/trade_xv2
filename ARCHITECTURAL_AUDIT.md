# Trade_XV2 Deep Architectural Audit

**Date:** 2026-07-21
**Scope:** 1,111 source files, 1,010 test files, 54 scripts
**Method:** Multi-agent parallel analysis across 7 specialized agents

---

# PHASE 1 — Codebase Mapping

## 1.1 Module Inventory

| Module | Files | Layer | Stated Responsibility |
|--------|-------|-------|----------------------|
| `domain/` | 220 | Domain | Core business models, entities, value objects, ports (protocols), events, risk policies, enumerations |
| `brokers/` | 313 | Infrastructure | Broker integrations (Dhan 95, Upstox 126, Paper 9), shared transport, certification, diagnostics |
| `interface/` | 148 | Presentation | REST API (FastAPI, 53 files), TUI/CLI (Textual, 94 files) |
| `analytics/` | 115 | Application | Analytics engine: backtest, replay, paper, scanner, strategy, indicators, walk-forward |
| `infrastructure/` | 104 | Infrastructure | Event bus, observability, auth, resilience, persistence, security, metrics, gateway, providers |
| `application/` | 99 | Application | Use cases, OMS (45 files), execution engine, streaming, portfolio, trading orchestration |
| `datalake/` | 60 | Infrastructure | Market Data Lake: Parquet + DuckDB, ingestion, quality, research API, MCP server |
| `runtime/` | 28 | Composition | Composition root: factory, broker discovery, OMS composition, parity gate, service registry |
| `config/` | 11 | Config | Central configuration: schema, validation, environment profiles, defaults, endpoints |
| `tradex/` | 8 | Presentation | Public SDK: `tradex.connect()`, session management, broker registry |
| `plugins/` | 5 | Infrastructure | Exchange plugins (NSE calendar and adapter) |

**Layer Distribution:**

| Layer | Files | % of src |
|-------|-------|----------|
| Domain | 220 | 19.8% |
| Application | 99 | 8.9% |
| Infrastructure (brokers + infra + datalake + plugins) | 482 | 43.4% |
| Presentation (interface + tradex) | 156 | 14.0% |
| Config (config + runtime) | 39 | 3.5% |

## 1.2 Dependency Graph

### Coupling Metrics

| Module | Intra-Module | Cross-Module | Total | Coupling % |
|--------|-------------|-------------|-------|------------|
| `domain` | 451 | 0 | 451 | **0.0%** (clean) |
| `config` | 6 | 3 | 9 | 33.3% |
| `datalake` | 205 | 53 | 258 | 20.5% |
| `analytics` | 273 | 134 | 407 | 32.9% |
| `brokers` | 686 | 513 | 1199 | 42.8% |
| `interface` | 334 | 256 | 590 | 43.4% |
| `infrastructure` | 124 | 102 | 226 | 45.1% |
| `application` | 220 | 267 | 487 | **54.8%** |
| `runtime` | 30 | 140 | 170 | **82.4%** |
| `tradex` | 8 | 38 | 46 | **82.6%** |

### Hub Modules (High Fan-In)

| Module | Fan-In | Dependents |
|--------|--------|-----------|
| `domain` | 10 | ALL other 10 modules |
| `infrastructure` | 6 | analytics, brokers, datalake, interface, runtime, tradex |
| `runtime` | 6 | analytics, application, brokers, infrastructure, interface, tradex |

### Hub Sub-Modules (Critical Boundaries)

| Sub-Module | Fan-In | Significance |
|-----------|--------|-------------|
| `domain/ports` | 76 | **The single most critical boundary** |
| `domain/entities` | 45 | Core entity definitions |
| `domain/constants` | 33 | Shared constants |
| `domain/instruments` | 27 | Instrument model |
| `domain/exceptions` | 23 | Error hierarchy |
| `infrastructure/event_bus` | 14 | Event system |

### High Fan-Out (God Modules)

| Module | Fan-Out | Risk |
|--------|---------|------|
| `runtime` | 9 | Depends on everything except plugins |
| `interface` | 8 | Reaches into nearly every layer |
| `interface/ui` | 59 sub-modules | **Big ball of mud at presentation boundary** |
| `interface/api` | 49 sub-modules | Wide API surface |

### Circular Dependencies

| # | Cycle | Severity | Mechanism |
|---|-------|----------|-----------|
| 1 | **`application` <-> `runtime`** | **CRITICAL** | 2 app files import `runtime.production_config`; runtime has 37 imports into application |
| 2 | **`infrastructure` <-> `runtime`** | **HIGH** | `infrastructure/gateway/factory.py` imports `runtime.broker_builders` |
| 3 | **`brokers` <-> `infrastructure`** (via runtime) | **HIGH** | 111 edges brokers->infrastructure; cycle closes through runtime |
| 4 | **`analytics` <-> `application`** | **MEDIUM** | `analytics/paper/engine.py` and `analytics/replay/engine/bar_loop.py` import `application.trading.signal_coordinator` |
| 5 | **`runtime` <-> `tradex`** | **MEDIUM** | Bidirectional wiring |

### Cross-Layer Violations

| # | From | To | File | Severity |
|---|------|----|------|----------|
| 1 | `infrastructure` (L1) | `runtime` (L3) | `infrastructure/gateway/factory.py:124` | **HIGH** — reaches up 2 layers |

**Domain Purity: CLEAN** — Zero cross-module imports. Only stdlib and one library (pydantic in 2 files).

## 1.3 Shared Constants, Types, and Enums

### Critical Shared Elements

| Element | Defined In | Used In (count) | Status |
|---------|-----------|-----------------|--------|
| `ExchangeSegment` enum | `domain/exchange_segments.py` | 20+ files | Canonical but 4 incompatible string representations exist |
| `Side` enum | `domain/enums.py` | 50+ files | Canonical but `"BUY"`/`"SELL"` strings used in 15+ files |
| `DEFAULT_EXCHANGE` | `domain/constants/market.py` | 12 files | **Ignored by 30+ files** that hardcode `"NSE"` |
| `DEFAULT_LOOKBACK_DAYS` | `domain/constants/defaults.py` | 3 files | **Ignored by 12+ files** using magic numbers |
| `MAX_RETRY_ATTEMPTS` | `domain/constants/resilience.py` | 2 files | **Ignored by 7 files** using `max_retries=3` |
| `TimeService` | `infrastructure/time_service.py` AND `runtime/time_service.py` | 20+ files | **Duplicated** in two locations |
| `OrderIntent` | `domain/orders/intent.py` AND `domain/execution_contracts.py` | 10+ files | **Two distinct classes** with same name |
| `SessionStatus` | `domain/session_status.py` AND `domain/sessions/trading_session.py` | 15+ files | **Two distinct classes** with same name |
| `TradingSession` | `domain/market/exchange.py` AND `domain/sessions/trading_session.py` | 10+ files | **Two distinct classes** with same name |

---

# PHASE 2 — Shotgun Surgery Detection

## Pattern A: Scattered Constants

**[SMELL-A1]** Scattered Constants: Hardcoded `"NSE"` as default exchange
- **Files:** 30+ files across analytics/, brokers/, domain/, infrastructure/, interface/, datalake/, config/, tradex/
- **Symbol/Value:** `"NSE"` hardcoded in 68+ locations instead of importing `DEFAULT_EXCHANGE`
- **Key Offenders:** `analytics/replay/signal_processor.py` (6x), `analytics/paper/signal_processor.py` (6x), `domain/instruments/_specialized.py` (5x), `interface/ui/services/market_access.py` (5x), `brokers/session/broker_session.py` (6x)
- **Blast Radius:** 30+ files
- **Impact:** HIGH

**[SMELL-A2]** Scattered Constants: Hardcoded `"INTRADAY"` as default product type
- **Files:** 12+ files across brokers/, interface/, application/
- **Symbol/Value:** `"INTRADAY"` hardcoded in 14+ locations; no `DEFAULT_PRODUCT_TYPE` constant exists
- **Blast Radius:** 12+ files
- **Impact:** MEDIUM

**[SMELL-A3]** Scattered Constants: Hardcoded `lookback_days` magic numbers
- **Files:** 12+ files, 60+ occurrences
- **Symbol/Value:** `120` appears 32 times; `90` in ~15 places; `30` in ~10 places. `DEFAULT_LOOKBACK_DAYS` exists but is rarely imported.
- **Blast Radius:** 12+ files
- **Impact:** HIGH

**[SMELL-A4]** Scattered Constants: Hardcoded timeouts
- **Files:** 14+ files
- **Symbol/Value:** `timeout=5.0` (4 files), `timeout=10.0` (3 files), `timeout=30` (2 files), `timeout=60` (3 files). Canonical constants exist in `domain/constants/timeouts.py` but are not consistently used.
- **Blast Radius:** 14 files
- **Impact:** MEDIUM

**[SMELL-A5]** Scattered Constants: Hardcoded timeframe strings
- **Files:** 30+ files, 74+ occurrences
- **Symbol/Value:** `"1D"`, `"1m"`, `"5m"`, `"15m"`, `"1h"` used without a `Timeframe` enum. Multiple independent lookup tables define the same vocabulary.
- **Blast Radius:** 30+ files
- **Impact:** HIGH

**[SMELL-A6]** Scattered Constants: Hardcoded `"NIFTY"` benchmark symbol
- **Files:** 30+ files, 49+ occurrences
- **Symbol/Value:** `"NIFTY"` used as benchmark default with no `DEFAULT_BENCHMARK_SYMBOL` constant
- **Blast Radius:** 30+ files
- **Impact:** MEDIUM

**[SMELL-A7]** Scattered Constants: Hardcoded `max_retries=3`
- **Files:** 7 files
- **Symbol/Value:** `max_retries=3` literal despite `MAX_RETRY_ATTEMPTS=3` in `domain/constants/resilience.py`
- **Blast Radius:** 7 files
- **Impact:** MEDIUM

**[SMELL-A8]** Scattered Constants: Hardcoded CORS origins
- **Files:** 4 files
- **Symbol/Value:** `["http://localhost:5173"]` in 6+ locations
- **Blast Radius:** 4 files
- **Impact:** LOW

## Pattern B: Duplicated Logic

**[SMELL-B1]** Duplicated Logic: WebSocket Reconnection Loop
- **Files:** `brokers/dhan/websocket/connection.py`, `brokers/dhan/websocket/market_feed.py`, `brokers/dhan/websocket/order_stream.py`, `brokers/upstox/websocket/market_data_v3.py`, `brokers/upstox/websocket/portfolio_stream.py`
- **Symbol/Value:** Nearly identical reconnect loops with max_reconnect_attempts, exponential backoff, staleness detection, cooldown wait, admission control. Dhan (3 files) and Upstox (2 files) implement the same pattern.
- **Blast Radius:** 5
- **Impact:** HIGH

**[SMELL-B2]** Duplicated Logic: HTTP Client Retry with Token Refresh
- **Files:** `brokers/dhan/api/http_client.py`, `brokers/dhan/api/async_http_client.py`, `brokers/upstox/auth/http.py`
- **Symbol/Value:** HTTP retry handling 401 (token refresh), 429 (rate limit), 5xx (server error), broker-specific token errors. Sync and async Dhan clients are near-identical copies.
- **Blast Radius:** 3
- **Impact:** HIGH

**[SMELL-B3]** Duplicated Logic: TOTP Token Generation Client
- **Files:** `brokers/dhan/auth/totp_client.py`, `brokers/upstox/auth/totp_client.py`
- **Symbol/Value:** Identical TOTP client patterns: credential resolution, pyotp generation, HTTP POST, rate limit detection, cooldown guard
- **Blast Radius:** 2
- **Impact:** MEDIUM

**[SMELL-B4]** Duplicated Logic: Token Refresh Scheduler
- **Files:** `brokers/dhan/auth/token_scheduler.py`, `brokers/upstox/auth/totp_scheduler.py`
- **Symbol/Value:** Background daemon thread scheduler with start()/stop(), health(), refresh_now(), _do_refresh() with lock, token validity check, rate limit backoff
- **Blast Radius:** 2
- **Impact:** MEDIUM

**[SMELL-B5]** Duplicated Logic: Segment/Exchange Mapping
- **Files:** `brokers/dhan/segments.py`, `brokers/upstox/instruments/segment_mapper.py`, `brokers/paper/segment_mapper.py`
- **Symbol/Value:** Three separate mapping tables despite sharing the same canonical ExchangeSegment enum
- **Blast Radius:** 3
- **Impact:** MEDIUM

**[SMELL-B6]** Duplicated Logic: DataProvider Adapter Pattern
- **Files:** `brokers/dhan/data/data_provider.py`, `brokers/upstox/data_provider.py`, `brokers/paper/data_provider.py`
- **Symbol/Value:** Identical DataProvider port implementation structure with get_quote(), get_quotes_batch(), get_history(), subscribe(), unsubscribe(), _SubscriptionHandle inner class
- **Blast Radius:** 3
- **Impact:** MEDIUM

**[SMELL-B7]** Duplicated Logic: Order Validation
- **Files:** `brokers/dhan/execution/order_validator.py`, `brokers/common/order_validation.py`, `brokers/upstox/orders/order_command_adapter.py`
- **Symbol/Value:** Common module exists but Dhan maintains its own OrderValidator with derivative segment checks
- **Blast Radius:** 3
- **Impact:** MEDIUM

**[SMELL-B8]** Duplicated Logic: Margin Calculation Adapter
- **Files:** `brokers/dhan/portfolio/margin.py`, `brokers/paper/margin.py`, `brokers/common/oms/margin_provider.py`
- **Symbol/Value:** Three different margin API shapes: `MarginRequest->MarginResponse`, `calculate_margin(payload)->dict`, `calculate_margin_for_order->MarginResult`
- **Blast Radius:** 3
- **Impact:** MEDIUM

**[SMELL-B9]** Duplicated Logic: Parallel Simulation Models (Paper/Replay)
- **Files:** `analytics/replay/models.py`, `analytics/paper/models.py`, `analytics/replay/signal_processor.py`, `analytics/paper/signal_processor.py`, `analytics/replay/position_closer.py`, `analytics/paper/position_closer.py`
- **Symbol/Value:** ~1000 lines of near-identical dataclasses and logic. Paper and replay have parallel SignalProcessor, PositionCloser, Trade, Position classes.
- **Blast Radius:** ~10 files
- **Impact:** HIGH

## Pattern C: Cross-Module State Mutation

**[SMELL-C1]** Cross-Module State Mutation: DhanMarketFeed God Object Facade
- **Files:** `brokers/dhan/websocket/market_feed.py`
- **Symbol/Value:** 10+ property setters directly mutating private attributes of child components: `self._sub._instruments`, `self._sub._quote_callbacks`, `self._conn._thread`, `self._conn._disconnect_time`, etc.
- **Blast Radius:** 1 file (affects entire Dhan streaming subsystem)
- **Impact:** HIGH

**[SMELL-C2]** Cross-Module State Mutation: Orchestrator mutating TickRouter internals
- **Files:** `application/streaming/orchestrator.py`
- **Symbol/Value:** `self._tick_router._candle_aggregator = aggregator` — direct private attribute assignment
- **Blast Radius:** 2 files
- **Impact:** MEDIUM

**[SMELL-C3]** Cross-Module State Mutation: RiskManager mutating DailyPnlTracker
- **Files:** `application/oms/_internal/risk_manager.py`
- **Symbol/Value:** `self._daily_pnl_tracker._capital_provider = provider.get_available_balance`
- **Blast Radius:** 2 files
- **Impact:** MEDIUM

**[SMELL-C4]** Cross-Module State Mutation: ReplayEngine/PaperEngine mutating FeaturePipeline
- **Files:** `analytics/replay/engine/__init__.py`, `analytics/paper/bar_window.py`
- **Symbol/Value:** `self._pipeline.fail_closed = config.fail_closed_features` — external mutation of internal state
- **Blast Radius:** 3 files
- **Impact:** MEDIUM

**[SMELL-C5]** Cross-Module State Mutation: PaperGateway injecting into child collections
- **Files:** `brokers/paper/paper_gateway.py`
- **Symbol/Value:** `self._orders._orders = orders`, `self._orders._trades = trades`, `self._portfolio._holdings = holdings`
- **Blast Radius:** 2 files
- **Impact:** MEDIUM

**[SMELL-C6]** Cross-Module State Mutation: Dhan websocket token propagation via attribute writes
- **Files:** `brokers/dhan/websocket/connection.py`, `brokers/dhan/websocket/order_stream.py`
- **Symbol/Value:** `self._feed.access_token = access_token` — token refresh via direct SDK attribute writes
- **Blast Radius:** 3 files
- **Impact:** MEDIUM

**[SMELL-C7]** Cross-Module State Mutation: Session mutating Universe._broker_facade
- **Files:** `domain/session.py`
- **Symbol/Value:** `self._universe._broker_facade = BrokerFacade(broker_id, extensions)`
- **Blast Radius:** 2 files
- **Impact:** MEDIUM

## Pattern D: Implicit Coupling via Naming

**[SMELL-D1]** Implicit Coupling: String-keyed dicts as inter-module protocol
- **Files:** 30+ files across application/, brokers/, domain/, interface/, datalake/, analytics/
- **Symbol/Value:** Modules communicate via `dict` with string keys `"symbol"`, `"exchange"`, `"order_id"`, `"product_type"`. No shared schema or typed contract. Typos silently swallowed by `.get()` with defaults.
- **Blast Radius:** 30+ files
- **Impact:** HIGH

**[SMELL-D2]** Implicit Coupling: Multiple OrderIntent classes
- **Files:** `domain/orders/intent.py`, `domain/execution_contracts.py`
- **Symbol/Value:** Two distinct `OrderIntent` classes — pre-risk vs durable/persisted. Import confusion risk.
- **Blast Radius:** 2+ files
- **Impact:** MEDIUM

**[SMELL-D3]** Implicit Coupling: Multiple Signal/Candidate classes
- **Files:** `analytics/strategy/models.py`, `analytics/scanner/models.py`
- **Symbol/Value:** `Signal` (symbol, signal_type, confidence) vs `Candidate` (symbol, score, exchange, reasons). No shared protocol. Bridged by duck-typing with `getattr`.
- **Blast Radius:** 4+ files
- **Impact:** MEDIUM

**[SMELL-D4]** Implicit Coupling: Exchange segment string proliferation
- **Files:** 5+ core files, 15+ consumer files
- **Symbol/Value:** 4 incompatible string representations: `"NSE_EQ"`/`"NSE_FNO"` (domain constants), `"MCX_COMM"` (Dhan wire), `ExchangeSegment` enum, short codes `"NSE"`/`"BSE"`/`"NFO"`
- **Blast Radius:** 20+ files
- **Impact:** HIGH

## Pattern E: Fragmented Feature Ownership

**[SMELL-E1]** Fragmented Feature: Place Order — split across 21 files
- **Files:** application/execution/ (5 files), application/oms/ (1 file), brokers/dhan/ (3 files), brokers/upstox/ (3 files), interface/ui/ (2 files), brokers/services/ (1 file), brokers/session/ (1 file), interface/api/ (1 file), domain/ports/ (3 files)
- **Symbol/Value:** 4 distinct entry points: PlaceOrderUseCase, ExecutionEngine, CLI `place_order`, `brokers.services.orders.place_order`
- **Blast Radius:** 21 files
- **Impact:** HIGH

**[SMELL-E2]** Fragmented Feature: Bracket Order (Super/Forever/GTT) — split across 12 files
- **Files:** domain/extensions/ (5 files), application/oms/ (1 file), brokers/dhan/extensions/ (3 files), brokers/upstox/ (1 file), interface/ui/ (1 file), domain/capability_manifest/ (1 file)
- **Symbol/Value:** Each new extended order type requires touching 6+ files
- **Blast Radius:** 12 files
- **Impact:** HIGH

**[SMELL-E3]** Fragmented Feature: Get Positions — split across 10 files
- **Files:** domain/ports/, brokers/dhan/ (3 files), brokers/upstox/ (2 files), application/portfolio/, brokers/services/, brokers/session/
- **Symbol/Value:** 4 different code paths to obtain positions; no canonical path
- **Blast Radius:** 10 files
- **Impact:** HIGH

**[SMELL-E4]** Fragmented Feature: WebSocket Connect — split across 9 files
- **Files:** application/streaming/ (3 files), brokers/dhan/websocket/ (2 files), brokers/dhan/api/ (1 file), brokers/upstox/websocket/ (3 files)
- **Symbol/Value:** Connection flow traverses 4+ layers before reaching the actual socket
- **Blast Radius:** 9 files
- **Impact:** MEDIUM

**[SMELL-E5]** Fragmented Feature: Reconnect — split across 7 files
- **Files:** application/streaming/reconnect_controller.py, application/streaming/orchestrator.py, brokers/dhan/api/reconnecting_service.py, brokers/dhan/websocket/ (2 files), brokers/upstox/websocket/ (2 files)
- **Symbol/Value:** Dual reconnect layers (application + broker) create ambiguity about retry policy ownership
- **Blast Radius:** 7 files
- **Impact:** HIGH

**[SMELL-E6]** Fragmented Feature: Margin Calculation — split across 7 files
- **Files:** domain/ports/margin_provider.py, brokers/dhan/portfolio/margin.py, brokers/paper/margin.py, brokers/common/oms/margin_provider.py, brokers/dhan/extended.py, brokers/upstox/extras.py, interface/ui/commands/extended_orders.py
- **Symbol/Value:** Three incompatible margin API signatures plus direct CLI bypass
- **Blast Radius:** 7 files
- **Impact:** HIGH

## Pattern F: Parallel Inheritance / Mirrored Hierarchies

**[SMELL-F1]** Parallel Hierarchy: Wire Adapter
- **Files:** `brokers/common/wire_base.py`, `brokers/dhan/wire.py` (555 lines), `brokers/upstox/wire.py` (341 lines)
- **Symbol/Value:** Adding a new broker requires implementing ~15 methods with little reuse from base
- **Blast Radius:** 3 files
- **Impact:** HIGH

**[SMELL-F2]** Parallel Hierarchy: Connection God-Object
- **Files:** `brokers/dhan/streaming/connection.py`, `brokers/upstox/broker.py`
- **Symbol/Value:** Parallel god-objects (~300+ lines each) serving as wiring hubs. Different names (`*Connection` vs `*Broker`) for identical roles.
- **Blast Radius:** 2 files
- **Impact:** MEDIUM

**[SMELL-F3]** Parallel Hierarchy: Extended Capabilities
- **Files:** `brokers/dhan/extended.py`, `brokers/dhan/extended_orders.py`, `brokers/dhan/extended_positions.py`, `brokers/dhan/extended_data.py`, `brokers/upstox/extras.py`, `brokers/upstox/common_extensions.py`
- **Symbol/Value:** Dhan splits into 4 classes; Upstox uses 1 monolithic class. No shared protocol.
- **Blast Radius:** 6 files
- **Impact:** HIGH

**[SMELL-F4]** Parallel Hierarchy: Order Adapter
- **Files:** `brokers/dhan/execution/orders.py`, `brokers/dhan/execution/order_placement.py`, `brokers/dhan/execution/order_cancellation.py`, `brokers/upstox/adapters/order_gateway.py`, `brokers/upstox/orders/order_command_adapter.py`, `brokers/upstox/orders/order_client.py`, `brokers/dhan/adapters/order_gateway.py`
- **Symbol/Value:** Structurally different decompositions with no common interface
- **Blast Radius:** 7 files
- **Impact:** HIGH

**[SMELL-F5]** Parallel Hierarchy: Extension Registration
- **Files:** 8 files across brokers/dhan/extensions/ and brokers/upstox/extensions/
- **Symbol/Value:** Extension system is broker-siloed; cross-broker patterns cannot be expressed
- **Blast Radius:** 8 files
- **Impact:** MEDIUM

## Pattern G: Inconsistent Abstraction Levels

**[SMELL-G1]** CLI reaches raw broker internals while REST API uses domain abstractions
- **Files:** `interface/ui/commands/extended_orders.py`, `interface/api/routers/orders.py`, `brokers/services/orders.py`
- **Symbol/Value:** Same operation (place extended order) uses 3 different abstraction levels. CLI gets raw dicts; API gets domain objects.
- **Blast Radius:** 4 files
- **Impact:** HIGH

**[SMELL-G2]** Mixed dict and typed-object returns across margin APIs
- **Files:** `brokers/dhan/portfolio/margin.py`, `brokers/common/oms/margin_provider.py`, `domain/ports/margin_provider.py`
- **Symbol/Value:** Three return types: `MarginRequest->MarginResponse`, `calculate_margin(payload)->dict`, `calculate_margin_for_order->MarginResult`
- **Blast Radius:** 4 files
- **Impact:** HIGH

**[SMELL-G3]** GatewayExecutionProvider uses getattr duck-typing while wire adapters use protocols
- **Files:** `infrastructure/gateway/execution.py`, `domain/ports/protocols.py`, `brokers/dhan/wire.py`, `brokers/upstox/wire.py`
- **Symbol/Value:** Triple-fallback duck-typing (`getattr(gateway, 'get_orderbook', None)` / `getattr(gateway, 'get_order_book', None)`) coexists with typed Protocol implementations
- **Blast Radius:** 5 files
- **Impact:** MEDIUM

**[SMELL-G4]** Legacy protocols coexist with domain ports
- **Files:** `brokers/common/api/__init__.py`, `domain/ports/protocols.py`, `domain/ports/broker_gateway.py`
- **Symbol/Value:** Two parallel port/protocol hierarchies; legacy marked deprecated but still importable and in use
- **Blast Radius:** 4+ files
- **Impact:** MEDIUM

## Pattern H: Missing/Bypassed Abstractions (Law of Demeter)

**[SMELL-H1]** CLI extended_orders.py — massive LoD violations
- **Files:** `interface/ui/commands/extended_orders.py`
- **Symbol/Value:** 11+ three-level chains through private attributes: `gw._broker.gtt.place_forever_order()`, `gw._conn.margin.calculate()`, `gw._broker.exit_all.exit_all()`, etc. 320+ lines of violations.
- **Blast Radius:** 1 file (320+ lines)
- **Impact:** HIGH

**[SMELL-H2]** DhanExtendedCapabilities — systematic LoD violations
- **Files:** `brokers/dhan/extended.py`, `brokers/dhan/extended_orders.py`, `brokers/dhan/extended_positions.py`, `brokers/dhan/extended_data.py`
- **Symbol/Value:** Every method is a 2-level chain `self._conn.<adapter>.<method>()`. Thin pass-throughs adding no behavior.
- **Blast Radius:** 4 files
- **Impact:** MEDIUM

**[SMELL-H3]** CliBrokerFacade reaches through private _trading_context
- **Files:** `interface/ui/services/cli_broker_facade.py`
- **Symbol/Value:** `self._svc._trading_context.order_manager` — 2-level chain through two private attributes
- **Blast Radius:** 1 file
- **Impact:** HIGH

**[SMELL-H4]** DhanWireAdapter / UpstoxWireAdapter thin delegation
- **Files:** `brokers/dhan/wire.py` (555 lines), `brokers/upstox/wire.py` (341 lines)
- **Symbol/Value:** Wire adapters are pure routing tables with no error handling, logging, or transformation at the wire level
- **Blast Radius:** 2 files
- **Impact:** MEDIUM

## Pattern: Inconsistent Coding Standards

**[SMELL-S1]** Import path inconsistency
- **Files:** ~100+ files
- **Symbol/Value:** Three import styles coexist: `from domain import Side`, `from domain.types import Side`, `from domain.enums import Side`
- **Blast Radius:** 100+ files
- **Impact:** MEDIUM

**[SMELL-S2]** Stringly-typed domain concepts
- **Files:** 15+ files in analytics/
- **Symbol/Value:** `"BUY"`/`"SELL"` strings used instead of `Side` enum; `"LONG"`/`"SHORT"` instead of `PositionSide`
- **Blast Radius:** 15+ files
- **Impact:** MEDIUM

**[SMELL-S3]** dict[str, Any] pervasive
- **Files:** 50+ occurrences across analytics/, runtime/, domain/
- **Symbol/Value:** Typed models exist but are bypassed in favor of untyped dicts
- **Blast Radius:** 50+ locations
- **Impact:** MEDIUM

**[SMELL-S4]** Status mapper side-effect at import
- **Files:** `brokers/dhan/status_mapper.py`
- **Symbol/Value:** Registers with StatusMapperRegistry at import time; importing a module changes global state
- **Blast Radius:** 1 file
- **Impact:** MEDIUM

**[SMELL-S5]** domain/__init__.py mega-facade (146 lines)
- **Files:** `domain/__init__.py`, `domain/types.py`
- **Symbol/Value:** Dual facade re-exporting from 14+ submodules; encourages `from domain import X` hiding submodule dependencies
- **Blast Radius:** 2 files + all consumers
- **Impact:** MEDIUM

---

# PHASE 3 — Root Cause Classification

## RC-1: Missing Shared Vocabulary Layer (11 findings)

> The codebase lacks a single, canonical set of domain types, enums, and value objects. Parallel definitions coexist across layers.

| Finding | Evidence | Impact |
|---------|----------|--------|
| Dual OrderIntent | `domain/orders/intent.py` vs `domain/execution_contracts.py` | Consumers cannot know which OrderIntent a function expects |
| Triple TradingSession | `domain/market/exchange.py`, `domain/sessions/trading_session.py`, `analytics/replay/models.py` | Name collision forces verbose qualified imports |
| Dual SessionStatus | `domain/session_status.py` vs `domain/sessions/trading_session.py` | Same name, different semantics |
| Dual TimeService | `infrastructure/time_service.py` vs `runtime/time_service.py` | Violates single-source-of-truth |
| Multiple MarketDataProvider Protocols | `analytics/core/providers.py` vs `brokers/common/api/__init__.py` | Overlapping contracts defined independently |
| Parallel Simulation Models | `analytics/replay/models.py` vs `analytics/paper/models.py` (~1000 lines) | Bug fixes must be applied twice |
| Parallel Signal Processors | `analytics/replay/signal_processor.py` vs `analytics/paper/signal_processor.py` | Code duplication; divergent behavior risk |
| Parallel Position Closers | `analytics/replay/position_closer.py` vs `analytics/paper/position_closer.py` | Code duplication; divergent behavior risk |
| PositionSide enum not elevated | Exists only in `analytics/paper/models.py`, not in domain | Analytics owns a domain concept |
| Analytics trade types tripled | `analytics/shared/trade_types.py` parallel to both replay and paper | Third copy of simulation types |
| CandidateDTO/SignalDTO shadow analytics | `domain/models/trading.py` mirrors `analytics/scanner/models.py` | Domain contains DTOs shadowing analytics types |

## RC-2: Missing Service/Use-Case Layer (6 findings)

> Business logic that should live in a dedicated application service is scattered across analytics, infrastructure, and broker layers.

| Finding | Evidence | Impact |
|---------|----------|--------|
| Trading costs in domain | `domain/trading_costs.py` (243 lines) | Domain contains fee-calculation logic |
| Fill pipeline in domain | `domain/simulation_fill_pipeline.py` | Domain reaches into simulation orchestration |
| Portfolio projection in domain | `domain/portfolio_projection.py` | Domain contains application-level projection |
| Reconciliation engine in domain | `domain/reconciliation_engine.py` | Domain contains orchestration logic |
| Mutable global resolver | `application/ports.py` (48 lines) | Application uses global mutable state |
| Config duplication | `config/schema.py` vs `interface/api/config.py` (35 Config classes across 25 files) | No single configuration authority |

## RC-3: Missing Domain Model (5 findings)

> Core domain concepts are expressed as primitives or buried in infrastructure/analytics code.

| Finding | Evidence | Impact |
|---------|----------|--------|
| No Money/Quantity value objects enforced | Analytics uses raw `float` and `Decimal` without wrapping | Type safety bypassed |
| dict[str, Any] pervasive | 50+ occurrences across analytics, runtime, domain | Loss of type safety |
| No domain-level Instrument aggregate | Instrument concepts scattered across 3+ locations | Each layer constructs its own representation |
| Exception hierarchy split | `domain/exceptions.py` vs `domain/errors.py` + infrastructure re-exports | Two parallel hierarchies |
| No domain event bus contract enforced | Events are ad-hoc despite EventBusPort protocol | Domain events not first-class |

## RC-4: Boundary Violations (7 findings)

> Layer boundaries are violated or circumvented through workarounds.

| Finding | Evidence | Impact |
|---------|----------|--------|
| Infrastructure re-exports to domain | `infrastructure/resilience/errors.py` re-exports from `domain.errors` | Circular dependency smell |
| Hardcoded "NSE" (30+ occurrences) | Analytics/application hardcode broker-specific defaults | Bypasses domain.Exchange enum |
| String "BUY"/"SELL" instead of Side enum | Analytics uses strings (8+ occurrences) | Defeats type checking |
| Broker __getattr__ reach-through | `brokers/dhan/domain.py` (365 lines) | Hides import structure |
| Status mapper side-effect at import | `brokers/dhan/status_mapper.py` registers at import time | Test isolation compromised |
| domain/__init__.py mega-facade | 146 lines re-exporting from 14+ submodules | Hides internal structure |
| domain/types.py secondary facade | 44 lines re-exporting overlapping types | Second level of indirection |

## RC-5: Premature File Splitting (4 findings)

> Files split into sub-modules without clear ownership model.

| Finding | Evidence | Impact |
|---------|----------|--------|
| domain/constants/ over-split | `__init__.py` (256 lines) both facade and dumping ground | Incomplete split |
| domain/ too many single-concept files | 8 small files (29-243 lines) at domain root | Flat root with no aggregation |
| Dual facade (domain/__init__.py + domain/types.py) | Two re-export facades for overlapping types | Import ambiguity |
| Exception files split across domain | 3 files for one exception hierarchy | Unclear which to import from |

## RC-6: Absent/Inconsistent Coding Standards (6 findings)

> Existing coding standards not uniformly enforced.

| Finding | Evidence | Impact |
|---------|----------|--------|
| Import path inconsistency | Three import styles coexist for same type | Same type imported three ways |
| Type aliases obscure origin | `OrderSide = Side`, `DomainSide = Side` | IDE navigation breaks |
| mypy only in ERROR mode on clean modules | Non-clean modules excluded | Type errors never caught |
| No banned-import rules for analytics | Analytics can import concrete broker types | Analytics drifts from domain vocabulary |
| File LOC limit not enforced on existing files | Many existing files exceed limit | Grandfathered-in oversized files |
| No contract preventing analytics duplication | No contract between analytics sub-packages | Structural duplication undetected |

---

# PHASE 4 — Refactoring Plan

## Dependency Graph

```
REF-1 (exceptions)  ──────────────────────────────────────┐
REF-2 (PositionSide) ────────────────────────────────────┐│
REF-3 (hardcoded NSE) ──────────────────────────────────┐││
REF-4 (OrderIntent) ───────────────────────────────────┐│││
REF-6 (session renames) ──────────────────────────────┐││││
REF-7 (TimeService) ─────────────────────────────────││││││
REF-8 (Config consolidation) ────────────────────────│││││││
                                                      │││││││
REF-5 (simulation consolidation) ← REF-2, REF-4      │││││││
                                                      │││││││
REF-9 (canonical imports) ← REF-1, REF-2, REF-4, REF-6│││││
                                                      │││││
REF-10 (orchestration out of domain) ← REF-5         │││││
                                                      ││││
REF-11 (typed models) ← REF-5                        ││││
                                                      │││
REF-12 (getattr removal) ─── independent             │││
                                                      ││
REF-13 (flatten constants) ← REF-6, REF-10          ││
                                                      │
REF-14 (duplication guardrail) ← REF-5               │
                                                      │
REF-15 (mypy expansion) ← REF-2, REF-11 ────────────┘
```

**Parallelizable Waves:**
- **Wave 1** (no dependencies): REF-1, REF-2, REF-3, REF-4, REF-6, REF-7, REF-8, REF-12
- **Wave 2** (after Wave 1): REF-5, REF-9
- **Wave 3** (after Wave 2): REF-10, REF-11, REF-13, REF-14
- **Ongoing**: REF-15

---

### REF-1: Unify Exception Hierarchy

| Field | Value |
|-------|-------|
| **Root Cause** | RC-3 (Missing Domain Model) |
| **Findings** | F21, F23, F33 |
| **Action** | Merge `domain/exceptions.py` and `domain/errors.py` into single `domain/exceptions.py`. Remove `infrastructure/resilience/errors.py` re-exports. |
| **From** | `domain/exceptions.py`, `domain/errors.py`, `infrastructure/resilience/errors.py` |
| **To** | `domain/exceptions.py` (single file, unified hierarchy) |
| **Touches** | `domain/__init__.py`, `domain/errors.py` (becomes thin re-export then removed), `infrastructure/resilience/errors.py` (deleted), all files importing from `domain.errors` |
| **Test Strategy** | Unit tests for exception hierarchy. Grep-based test to verify no direct imports from `domain.errors`. Import-linter contract. |
| **Sequencing** | Must complete before REF-9. |

### REF-2: Elevate PositionSide to Domain Enums

| Field | Value |
|-------|-------|
| **Root Cause** | RC-1 (Missing Shared Vocabulary Layer) |
| **Findings** | F9, F25 |
| **Action** | Move `PositionSide` from `analytics/paper/models.py` to `domain/enums.py`. Replace all `"BUY"`/`"SELL"`/`"LONG"`/`"SHORT"` strings with enum values. |
| **From** | `analytics/paper/models.py`, string literals across analytics/ |
| **To** | `domain/enums.py`, typed usage everywhere |
| **Touches** | `domain/enums.py`, `analytics/paper/models.py`, `analytics/paper/signal_processor.py`, `analytics/paper/position_closer.py`, `analytics/replay/signal_processor.py`, `analytics/replay/position_closer.py`, `analytics/backtest/fast_backtest.py`, `analytics/strategy/models.py` |
| **Test Strategy** | mypy strict pass. Ruff rule banning string literals. |
| **Sequencing** | Should complete before REF-5. |

### REF-3: Eliminate Hardcoded "NSE" Defaults

| Field | Value |
|-------|-------|
| **Root Cause** | RC-4 (Boundary Violations) |
| **Findings** | F24 |
| **Action** | Replace all `exchange: str = "NSE"` with `exchange: Exchange = Exchange.NSE`. In analytics providers, require explicit exchange parameter. Add ruff banned-api rule. |
| **From** | 30+ locations across analytics/, application/, config/, tradex/ |
| **To** | `domain/market_enums.py` Exchange enum used as default |
| **Touches** | 13+ files (see Phase 2 SMELL-A1) |
| **Test Strategy** | Ruff custom check for `"NSE"` string literal in function signatures. |
| **Sequencing** | Independent; should complete before REF-9. |

### REF-4: Consolidate OrderIntent Types

| Field | Value |
|-------|-------|
| **Root Cause** | RC-1 (Missing Shared Vocabulary Layer) |
| **Findings** | F1 |
| **Action** | Rename `domain/orders/intent.py:OrderIntent` to `OrderCommand` (pre-risk, ephemeral). Keep `domain/execution_contracts.py:OrderIntent` as durable. |
| **From** | `domain/orders/intent.py` (OrderIntent) |
| **To** | `domain/orders/intent.py` (OrderCommand) |
| **Touches** | `domain/orders/intent.py`, `domain/orders/__init__.py`, all consumers |
| **Test Strategy** | mypy pass. Rename is compile-time safe. |
| **Sequencing** | Should complete before REF-5. |

### REF-5: Consolidate Simulation Models (Paper/Replay)

| Field | Value |
|-------|-------|
| **Root Cause** | RC-1 (Missing Shared Vocabulary Layer) |
| **Findings** | F6, F7, F8, F10 |
| **Action** | Create `analytics/simulation/` with shared base classes: models.py (SimTrade, SimPosition), signal_processor.py, position_closer.py. Paper and replay become thin adapters. |
| **From** | `analytics/paper/models.py`, `analytics/paper/signal_processor.py`, `analytics/paper/position_closer.py`, `analytics/replay/models.py`, `analytics/replay/signal_processor.py`, `analytics/replay/position_closer.py`, `analytics/shared/trade_types.py` |
| **To** | `analytics/simulation/models.py`, `analytics/simulation/signal_processor.py`, `analytics/simulation/position_closer.py` |
| **Touches** | ~10 files in analytics/paper/ and analytics/replay/, `analytics/shared/trade_types.py` (deleted) |
| **Test Strategy** | Golden dataset parity tests. Property-based tests for paper/replay identity. Import-linter contract. |
| **Sequencing** | Depends on REF-2, REF-4. Highest-effort task. |

### REF-6: Rename Conflicting Session/TradingSession Types

| Field | Value |
|-------|-------|
| **Root Cause** | RC-1 (Missing Shared Vocabulary Layer) |
| **Findings** | F2, F3 |
| **Action** | Rename `domain/market/exchange.py:TradingSession` to `MarketHours`. Rename `domain/session_status.py:SessionStatus` to `ConnectivityStatus`. |
| **From** | `domain/market/exchange.py`, `domain/session_status.py` |
| **To** | `domain/market/exchange.py` (MarketHours), `domain/session_status.py` (ConnectivityStatus) |
| **Touches** | `domain/market/exchange.py`, `domain/session_status.py`, `domain/__init__.py`, all consumers |
| **Test Strategy** | mypy pass. Grep-based test for old names. |
| **Sequencing** | Independent. |

### REF-7: Unify TimeService

| Field | Value |
|-------|-------|
| **Root Cause** | RC-1 (Missing Shared Vocabulary Layer) |
| **Findings** | F4 |
| **Action** | Merge `runtime/time_service.py` clocks into `infrastructure/time_service.py`. Single TimeService. |
| **From** | `runtime/time_service.py`, `infrastructure/time_service.py` |
| **To** | `infrastructure/time_service.py` (single) |
| **Touches** | `runtime/time_service.py` (deleted), `infrastructure/time_service.py`, all test files using FakeClock |
| **Test Strategy** | Unit tests for both clock implementations. |
| **Sequencing** | Independent. |

### REF-8: Consolidate Config Classes

| Field | Value |
|-------|-------|
| **Root Cause** | RC-2 (Missing Service/Use-Case Layer) |
| **Findings** | F17 |
| **Action** | Merge `interface/api/config.py:APIConfig` into `config/schema.py:AppConfig`. Audit all 35 Config dataclasses. |
| **From** | `interface/api/config.py`, 35 scattered Config dataclasses |
| **To** | `config/schema.py` (AppConfig as single root) |
| **Touches** | `config/schema.py`, `interface/api/config.py` (deleted), all Config class definitions |
| **Test Strategy** | Config validation tests. Integration test for API startup. |
| **Sequencing** | Independent. |

### REF-9: Establish Canonical Import Paths

| Field | Value |
|-------|-------|
| **Root Cause** | RC-6 (Absent/Inconsistent Coding Standards) |
| **Findings** | F34, F35, F28, F29, F32 |
| **Action** | Define canonical import paths. Deprecate `domain/__init__.py` mega-facade and `domain/types.py`. Remove type aliases. Add ruff rules. |
| **From** | `domain/__init__.py` (146 lines), `domain/types.py` (44 lines), alias definitions |
| **To** | Direct submodule imports everywhere |
| **Touches** | ~100+ files using facade imports or aliases |
| **Test Strategy** | Ruff custom rule. Import-linter contract. mypy strict. |
| **Sequencing** | Must complete AFTER REF-1, REF-2, REF-4, REF-6. |

### REF-10: Move Orchestration Logic Out of Domain

| Field | Value |
|-------|-------|
| **Root Cause** | RC-2 (Missing Service/Use-Case Layer) |
| **Findings** | F12, F13, F14, F15 |
| **Action** | Create `application/services/` use-case modules: trading_costs_service.py, simulation_orchestrator.py, reconciliation_service.py. |
| **From** | `domain/trading_costs.py`, `domain/simulation_fill_pipeline.py`, `domain/simulation_position_meta.py`, `domain/portfolio_projection.py`, `domain/reconciliation_engine.py` |
| **To** | `application/services/trading_costs_service.py`, `application/services/simulation_orchestrator.py`, `application/services/reconciliation_service.py` |
| **Touches** | 5 domain files, `application/services/` (new files), all consumers |
| **Test Strategy** | Unit tests for each service. Import-linter: domain must not import from application. |
| **Sequencing** | Depends on REF-5. |

### REF-11: Eliminate dict[str, Any] in Favor of Typed Models

| Field | Value |
|-------|-------|
| **Root Cause** | RC-3 (Missing Domain Model) |
| **Findings** | F19 |
| **Action** | Replace `dict[str, Any]` with typed dataclasses/Pydantic models. Add mypy strict to cleaned modules. |
| **From** | 50+ locations with `dict[str, Any]` |
| **To** | Typed dataclasses/Pydantic models |
| **Touches** | `analytics/replay/models.py`, `analytics/core/models.py`, `domain/extensions/`, `domain/backtest/models.py`, `runtime/` files |
| **Test Strategy** | mypy strict per-module rollout. |
| **Sequencing** | Incremental; after REF-1 through REF-5 stabilize types. |

### REF-12: Remove Broker __getattr__ Reach-Throughs

| Field | Value |
|-------|-------|
| **Root Cause** | RC-4 (Boundary Violations) |
| **Findings** | F26 |
| **Action** | Replace `__getattr__` re-exports in `brokers/dhan/domain.py` with explicit imports. |
| **From** | `brokers/dhan/domain.py` |
| **To** | Explicit imports from defining submodules |
| **Touches** | `brokers/dhan/domain.py`, all consumers |
| **Test Strategy** | Ruff rule banning `__getattr__` for re-exports. |
| **Sequencing** | Independent. |

### REF-13: Flatten Domain Constants Package

| Field | Value |
|-------|-------|
| **Root Cause** | RC-5 (Premature File Splitting) |
| **Findings** | F30, F31 |
| **Action** | Move remaining constants from `domain/constants/__init__.py` into submodules. Consolidate small domain-root files into sub-packages. |
| **From** | `domain/constants/__init__.py`, scattered small files at domain root |
| **To** | Clean sub-packages: `domain/simulation/`, `domain/reconciliation/`, `domain/sessions/` |
| **Touches** | `domain/constants/`, new sub-packages, `domain/__init__.py` |
| **Test Strategy** | Import-linter contracts. mypy pass. |
| **Sequencing** | Depends on REF-6, REF-10. |

### REF-14: Add Analytics Duplication Guardrail

| Field | Value |
|-------|-------|
| **Root Cause** | RC-6 (Absent/Inconsistent Coding Standards) |
| **Findings** | F39, F37 |
| **Action** | Import-linter contract preventing paper/replay cross-imports. Ruff banned-api for broker types in analytics. CI duplication check. |
| **From** | No existing guardrail |
| **To** | Import-linter + ruff + CI duplication check |
| **Touches** | `pyproject.toml`, `.pre-commit-config.yaml` |
| **Test Strategy** | Import-linter test suite. CI verification. |
| **Sequencing** | Depends on REF-5. |

### REF-15: Expand mypy Strict Coverage

| Field | Value |
|-------|-------|
| **Root Cause** | RC-6 (Absent/Inconsistent Coding Standards) |
| **Findings** | F36, F38 |
| **Action** | Create growing mypy strict-mode allowlist. Enforce file LOC limit on all files. |
| **From** | mypy ERROR-mode on clean modules only |
| **To** | mypy strict on all modules (gradual) |
| **Touches** | `pyproject.toml`, `.pre-commit-config.yaml` |
| **Test Strategy** | CI mypy strict on allowlisted modules. Allowlist only grows. |
| **Sequencing** | Ongoing; starts after REF-2 and REF-11. |

---

# PHASE 5 — Structural Recommendations

## 5.1 Proposed Directory Structure

```
src/
├── domain/
│   ├── __init__.py                    # Minimal: version only, no re-exports
│   ├── entities/
│   │   ├── order.py                   # Order, OrderRequest, ModifyOrderRequest
│   │   ├── position.py                # Position, PositionState
│   │   ├── trade.py                   # Trade
│   │   └── instrument.py              # Instrument aggregate root (NEW)
│   ├── enums.py                       # Side, OrderStatus, ProductType, OrderType, PositionSide
│   ├── market_enums.py                # Exchange, ExchangeSegment, InstrumentType, OptionType
│   ├── exceptions.py                  # Unified exception hierarchy (REF-1)
│   ├── value_objects.py               # Money, Quantity (enforce usage)
│   ├── ports/
│   │   ├── protocols.py               # DataProvider, ExecutionProvider
│   │   ├── broker_gateway.py          # OrderTransportPort, BrokerStreamHandle
│   │   └── event_publisher.py         # EventBusPort
│   ├── events/
│   │   └── types.py                   # DomainEvent base
│   ├── constants/
│   │   ├── __init__.py                # Pure re-export facade only
│   │   ├── auth.py, defaults.py, exchanges.py, market.py
│   │   ├── oms.py                     # NEW: moved from __init__.py
│   │   ├── reconciliation.py          # NEW: moved from __init__.py
│   │   ├── observability.py, resilience.py, risk.py, segments.py, timeouts.py
│   ├── sessions/
│   │   ├── trading_session.py         # TradingSession, SessionStatus (canonical)
│   │   └── connectivity.py            # ConnectivityStatus (renamed, REF-6)
│   ├── market/
│   │   └── exchange.py                # Exchange entity, MarketHours (renamed, REF-6)
│   ├── execution_contracts.py         # OrderIntent (durable)
│   ├── orders/
│   │   ├── intent.py                  # OrderCommand (renamed, REF-4)
│   │   └── requests.py
│   ├── status_mapper.py
│   └── extensions/                    # Typed payloads (REF-11)
│
├── application/
│   ├── services/
│   │   ├── trading_costs_service.py   # NEW (REF-10)
│   │   ├── simulation_orchestrator.py # NEW (REF-10)
│   │   ├── reconciliation_service.py  # NEW (REF-10)
│   │   ├── instrument_registry.py
│   │   └── download_engine.py
│   ├── oms/                           # Order management
│   ├── composer/
│   └── ports.py                       # Consider deprecation
│
├── infrastructure/
│   ├── time_service.py                # Single TimeService (REF-7)
│   ├── event_bus/
│   ├── resilience/
│   └── security/
│
├── brokers/
│   ├── common/
│   │   ├── order_validation.py
│   │   └── api/
│   ├── dhan/
│   │   ├── domain.py                  # Explicit imports only (REF-12)
│   │   └── ...
│   └── upstox/
│
├── analytics/
│   ├── simulation/                    # NEW: shared simulation layer (REF-5)
│   │   ├── models.py                  # SimTrade, SimPosition, SimSession
│   │   ├── signal_processor.py        # Single SignalProcessor
│   │   └── position_closer.py         # Single PositionCloser
│   ├── paper/
│   │   └── adapter.py                 # Thin adapter configuring simulation/
│   ├── replay/
│   │   └── adapter.py                 # Thin adapter configuring simulation/
│   ├── backtest/, strategy/, scanner/, views/, walk_forward/, intraday/, core/
│
├── interface/
│   ├── api/
│   │   └── ...                        # config.py DELETED (REF-8)
│   └── ui/
│
├── config/
│   └── schema.py                      # AppConfig: single root (REF-8)
│
├── runtime/                           # No TimeService (moved, REF-7)
├── datalake/
└── tradex/
```

## 5.2 Boundary Rules

| Rule ID | Rule | Enforced By | Root Cause |
|---------|------|-------------|------------|
| **B-1** | `domain/` must not import from `application/`, `infrastructure/`, `brokers/`, `analytics/`, `interface/` | import-linter (existing) | RC-4 |
| **B-2** | `infrastructure/` must not import from `brokers/`, `analytics/`, `interface/` | import-linter (existing) | RC-4 |
| **B-3** | `analytics/paper/` must not import from `analytics/replay/` and vice versa; both import from `analytics/simulation/` | import-linter (NEW) | RC-1, RC-6 |
| **B-4** | `application/` must not import concrete broker modules; uses domain ports only | import-linter (existing) | RC-4 |
| **B-5** | `interface/` must not import from `brokers/` directly | import-linter (existing) | RC-4 |
| **B-6** | `runtime/` is the ONLY layer permitted to import concrete broker modules | import-linter (existing) | RC-4 |
| **B-7** | No module may use `__getattr__` for re-exports | ruff custom rule | RC-4 |
| **B-8** | All domain types imported from owning submodule, never from `domain` or `domain.types` facade | ruff banned-api | RC-6 |
| **B-9** | String literals `"NSE"`, `"BUY"`, `"SELL"` banned in function signatures; use domain enums | ruff banned-api | RC-4, RC-6 |
| **B-10** | `dict[str, Any]` banned in new code; typed models required | mypy strict + ruff | RC-3 |

## 5.3 Checkable Coding Standards

| # | Standard | Check Mechanism | Finding Addressed |
|---|----------|----------------|-------------------|
| **CS-1** | Canonical import paths: always from owning submodule, never facade. No type aliases. | ruff banned-api + import-linter | F34, F35 |
| **CS-2** | No stringly-typed domain concepts: Exchange, Side, PositionSide always use enums. | ruff banned-api | F24, F25 |
| **CS-3** | Single exception hierarchy: all from `domain.exceptions`. No parallel hierarchies. | import-linter + grep test | F21, F23 |
| **CS-4** | No import-time side effects: registration in `runtime/composition.py` only. | Custom AST checker | F27 |
| **CS-5** | Typed models over dict[str, Any]: dataclasses/Pydantic for known shapes. | mypy strict + ruff | F19 |
| **CS-6** | Single definition rule: each type defined exactly once. CI name-similarity check. | Custom CI check | F1-F11 |
| **CS-7** | File size limit (ADR-011): enforced on ALL files, no grandfathering. | check-file-loc hook | F38 |
| **CS-8** | Composition root exclusivity: only `runtime/` instantiates concrete broker classes. | import-linter + mypy | F16 |

## 5.4 Guardrails to Prevent Recurrence

| Guardrail | Implementation | Prevents |
|-----------|---------------|----------|
| **G-1** | Import-linter contract suite: expand from 13 to ~18 contracts | New boundary violations |
| **G-2** | Ruff banned-api expansion: `"NSE"` default, `"BUY"`/`"SELL"`, `__getattr__`, `dict[str, Any]`, facade imports | RC-4 and RC-6 at commit time |
| **G-3** | mypy strict allowlist: only grows, new modules must start strict | Gradual type error elimination |
| **G-4** | Duplication detection CI: nightly AST similarity between analytics sub-packages | RC-1 parallel model duplication |
| **G-5** | Pre-commit architecture fitness function: no `__getattr__` re-exports, no string defaults, unified exceptions, no `dict[str, Any]` in new code | All root causes |
| **G-6** | ADR-required structural changes: new module/Config/facade requires ADR | RC-5, RC-2 |
| **G-7** | Name collision registry: CI fails if new type name has >0.8 similarity to existing | RC-1 duplicate definitions |
| **G-8** | Zero-parity verification: golden dataset tests on every PR touching simulation/paper/replay | RC-1 simulation divergence |

---

## Summary Statistics

| Metric | Count |
|--------|-------|
| Total Phase 2 findings | **66** |
| HIGH impact findings | **24** |
| MEDIUM impact findings | **35** |
| LOW impact findings | **7** |
| Root cause categories | **6** |
| Refactoring tasks | **15** |
| Boundary rules | **10** |
| Coding standards | **8** |
| Guardrails | **8** |
| Files affected by HIGH impact findings | **200+** |

## Traceability Matrix

| Root Cause | Findings | Refactoring Tasks | Guardrails |
|------------|----------|-------------------|------------|
| RC-1: Missing shared vocabulary | F1-F11 | REF-2, REF-4, REF-5, REF-6, REF-7 | G-4, G-6, G-7, G-8 |
| RC-2: Missing service/use-case layer | F12-F17 | REF-8, REF-10 | G-6 |
| RC-3: Missing domain model | F18-F22 | REF-1, REF-11 | G-3, G-5 |
| RC-4: Boundary violations | F23-F29 | REF-3, REF-12 | G-1, G-2, G-5 |
| RC-5: Premature file splitting | F30-F33 | REF-13 | G-6 |
| RC-6: Absent/inconsistent standards | F34-F39 | REF-9, REF-14, REF-15 | G-1, G-2, G-3, G-5 |
