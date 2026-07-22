# TradeXV2 — Unified Implementation Specification

> **Single source of truth** for reimplementing TradeX as a NautilusTrader-style algorithmic trading framework.
> Synthesized from goal.md and specs 00–15. References the numbered specs for deep-dive contracts.

---

## Table of Contents

1. [Product Vision](#1-product-vision)
2. [Core Architecture](#2-core-architecture)
3. [Domain Model](#3-domain-model)
4. [Message Bus and Lifecycle](#4-message-bus-and-lifecycle)
5. [Execution Engine and OMS](#5-execution-engine-and-oms)
6. [Strategy and Analytics](#6-strategy-and-analytics)
7. [Broker Adapter Framework](#7-broker-adapter-framework)
8. [Data Infrastructure](#8-data-infrastructure)
9. [Risk and Safety](#9-risk-and-safety)
10. [Observability and Operations](#10-observability-and-operations)
11. [Configuration and Developer Experience](#11-configuration-and-developer-experience)
12. [Testing and Quality](#12-testing-and-quality)
13. [Deployment](#13-deployment)
14. [Data Flow Diagrams](#14-data-flow-diagrams)
15. [Implementation Phases](#15-implementation-phases)
16. [Framework Contract](#16-framework-contract)
17. [Capability Coverage](#17-capability-coverage)

---

## 1. Product Vision

### 1.1 What We Build

TradeX is a **professional, event-driven algorithmic trading platform** for Indian exchanges (NSE/BSE/MCX), reimplemented under [NautilusTrader](https://nautilustrader.io/) engine patterns:

- Message-driven core (MessageBus spine)
- Clock + Cache + deterministic replay
- Venue adapters via entry points
- **Research-to-live parity** — same engine across Replay, Backtest, Paper, and Live

### 1.2 Framework vs Application

| Application | Framework (Nautilus-style) |
|-------------|------------------------------|
| User code calls the system | Engine calls user code (strategies, scanners) |
| Separate backtest and live code | Research-to-live parity: same engine, different FillSource |
| Observability bolted on | MessageBus is the observability spine |
| Hard-coded venue logic | Venue adapters via entry points |

### 1.3 Nautilus Alignment

| NautilusTrader | TradeX Equivalent |
|----------------|-------------------|
| TradingNode | TradingNode — configure, start, stop, run |
| MessageBus | MessageBus — typed publish/subscribe |
| Clock | SystemClock / FakeClock — nanosecond UTC |
| Cache | TradingCache — orders, positions, quotes |
| Actors / Strategies | Strategy protocol + StrategyEngine |
| Venue Adapters | BrokerAdapter plugins (Dhan, Upstox, Paper) |
| Event-sourced replay | ReplayEngine + durable MessageLog |
| Research-to-live parity | Same ExecutionEngine across four modes |
| Portfolio | PositionManager + PortfolioModel |

### 1.4 Adaptations from NautilusTrader

| NautilusTrader | TradeX Adaptation | Reason |
|----------------|-------------------|--------|
| Rust/Cython core | Pure Python | Team size, iteration speed |
| Multi-asset global venues | NSE/BSE/MCX only | Product focus |
| Custom storage engine | DuckDB + Parquet | Analytics fit, zero ops overhead |
| Library-only | Click CLI + FastAPI + TUI + MCP | Analytics-first product |
| FIX protocol | REST + WebSocket (broker SDKs) | Indian broker APIs |
| Generic risk | Indian market rules (STT, margins, circuit limits) | Domain accuracy |

### 1.5 Immutable Research Pipeline

```
Market Data → FeaturePipeline → Indicators → Strategies → Signals
  → PortfolioModel → RiskGate → OMS → ExecutionEngine → ExecutionTarget
```

This pipeline is identical across all four modes. Only DataSource, Clock, and FillSource differ at composition time.

### 1.6 Goals (Measurable)

| Goal | Measure |
|------|---------|
| Four-mode parity | Same ExecutionEngine FSM in Replay/Backtest/Paper/Live |
| No bypass paths | Zero alternate order-placement paths outside ExecutionEngine |
| Full capability coverage | 147/147 capabilities in coverage ledger marked COVERED |
| Broker module size | ~50 focused plugin files (Gateway→Connection→Sub-Adapters) |
| No god classes | Max dependency degree ≤ 50 per class (architecture test) |
| MessageBus central | All inter-component traffic via typed bus |
| Standard lifecycle | Every component: initialize → start → stop → reset |
| Analytics-first CLI | Top-level commands organized by research questions |
| Broker agnosticism | New venue via plugin only; application unchanged |
| Deterministic replay | Message log replay → identical cache state |
| Real-money safety | RiskGate + IdempotencyGuard on every order path |
| Layer boundaries | Six-layer import contracts enforced in CI |
| Test coverage | 85%+ overall; architecture tests 300+ |

---

## 2. Core Architecture

### 2.1 System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  INTERFACE LAYER  (Presentation — no broker imports)            │
│  CLI · TUI · FastAPI · WebSocket · MCP                          │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  RUNTIME LAYER  (Composition Root — ONLY layer touching         │
│  concrete brokers/plugins)                                       │
│  TradingNode · ComponentRegistry · ComponentFactory ·           │
│  LifecycleManager · ConfigManager · MessageBus                  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  APPLICATION LAYER  (Use-cases — NO infra/runtime/broker imports)│
│  OMS · ExecutionEngine · StrategyEngine · DataEngine · Analytics│
│  TradingContext · TradingOrchestrator                           │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  INFRASTRUCTURE LAYER  (Adapters — implements domain ports)     │
│  MessageBus impl · Idempotency · Auth · IO · Resilience ·         │
│  Observability · Broker plugins · Datalake                      │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  DOMAIN LAYER  (Entities, ports, events — imports NOTHING inward)│
│  entities/ · value_objects/ · events/ · commands/ · ports/ ·      │
│  services/ · policies/                                          │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  SHARED LAYER  (Cross-cutting utilities — no business logic)    │
│  logging/ · config/ · types/ · errors/ · messaging/             │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Dependency Rule

```
interface/      ──▶  runtime/       (composition root ONLY touches concretes)
runtime/         ──▶  infrastructure/ + application/ + plugins/
infrastructure/  ──▶  domain/ + shared/ + application ports
application/     ──▶  domain/ + shared/
shared/          ──▶  stdlib only
domain/          ──▶  (NOTHING inward — stdlib + itself only)
plugins/         ──▶  domain/ + shared/  (discovered by runtime)
```

### 2.3 Import-Linter Contracts (CI-Enforced)

| Contract | Rule |
|----------|------|
| Domain purity | domain may not import application, infrastructure, runtime, interface |
| Application isolation | application may not import infrastructure, runtime, interface |
| Infrastructure scope | infrastructure may not import runtime or interface |
| Interface routing | interface may not import infrastructure directly — via runtime |
| Broker independence | dhan, upstox, paper plugins are mutually independent |

### 2.4 Enforced Invariants

1. **Domain purity** — domain may not import application, infrastructure, runtime, brokers, or interface
2. **Application isolation** — application may not import infrastructure, runtime, brokers, or interface
3. **Runtime exclusivity** — runtime is the ONLY layer permitted concrete broker/plugin imports
4. **Strategy isolation** — strategies/scanners must not reach into OMS/execution directly
5. **Trading without strategies** — OMS + execution must be usable with zero strategies loaded
6. **Broker selection once** — active broker resolved at startup via enum, never string branching

### 2.5 Stack Table

| Layer | Technology | Role |
|-------|------------|------|
| Interface | Click, Textual, FastAPI, WebSocket, MCP | User interaction surfaces |
| Runtime | Python composition root | Wire components, discover plugins |
| Application | Pure Python use-cases | OMS, execution, strategy, analytics, TradingContext |
| Infrastructure | Python adapters + plugins | Message bus, auth, IO, brokers, datalake |
| Domain | Python dataclasses, Protocols | Entities, ports, events, policies |
| Shared | structlog, Pydantic helpers | Logging, config, types, errors |
| Storage | Parquet, DuckDB | Historical data, analytics |
| Observability | OpenTelemetry, Prometheus | Tracing, metrics export |

### 2.6 Storage Model

| Store | Format | Owner | Purpose |
|-------|--------|-------|---------|
| Historical bars | Parquet | Datalake | Canonical OHLCV |
| Analytics | DuckDB | Datalake | SQL views, aggregations |
| Instrument master | Parquet + resolver | Broker plugin + domain ports | Symbol resolution |
| Token persistence | JSON/state file | Per-broker auth | OAuth/TOTP tokens |
| Idempotency ledger | In-memory + optional persistence | Infrastructure | Order deduplication |
| Quote snapshots | TradingCache (in-memory) | Application | Live market state |
| Message log | Durable event store | MessageBus | Deterministic ReplayEngine |
| Corporate actions | Parquet | Datalake | Adjustment for backtest/replay |

### 2.7 Performance Architecture

| Target | Specification |
|--------|---------------|
| Order processing latency | Sub-millisecond for local risk + routing (excludes venue RTT) |
| Message dispatch | Zero-copy: immutable frozen dataclasses passed by reference |
| Market data throughput | Batch publishing to reduce bus traffic |
| Historical data | Columnar storage (Parquet/Arrow); vectorized reads |
| I/O model | Async for WebSocket, HTTP, and file operations |

**Key Performance Patterns:**
1. **Immutable messages** — No defensive copying; handlers must not mutate
2. **Batch processing** — QuoteBatch, BarBatch messages reduce dispatch overhead
3. **Async I/O** — WebSocket and HTTP in async tasks; CPU-bound work in thread pool
4. **Object pooling** — Optional pool for high-frequency message types in hot path
5. **Columnar data** — Parquet/Arrow for historical; avoid row-by-row Python loops
6. **Priority queues** — Order commands prioritized over market data in MessageBus

---

## 3. Domain Model

> Full specification: [02-domain-model.md](02-domain-model.md)

### 3.1 Purpose

The domain layer is the innermost ring of Clean Architecture. Pure business logic: entities, value objects, events, commands, ports, services, and policies. Imports nothing from outer layers.

### 3.2 Domain Package Structure

| Sub-package | Contents |
|-------------|----------|
| `entities/` | Order, Position, Trade, Quote, Bar, MarketDepth, OptionChain, Instrument |
| `value_objects/` | Money, Price, Quantity, InstrumentId, CorrelationId, TimeFrame |
| `events/` | DomainEvent, OrderPlaced, OrderFilled, PositionChanged, RiskBreached |
| `commands/` | PlaceOrderCommand, CancelOrderCommand, ModifyOrderCommand |
| `ports/` | BrokerAdapterPort, FillSourcePort, EventBusPort, DataCatalogPort, RiskEnginePort |
| `services/` | PricingService, FeeCalculator (STT, brokerage), InstrumentRegistry |
| `policies/` | SourceSelectionPolicy, RoutingPolicy |

### 3.3 Core Entities

| Entity | Key Fields | Responsibility |
|--------|------------|----------------|
| Order | order_id, instrument_id, side, quantity, price, status, correlation_id | Order lifecycle state |
| Position | instrument_id, quantity, avg_price, realized_pnl, unrealized_pnl | Position tracking |
| Quote | instrument_id, bid, ask, bid_size, ask_size, timestamp | Market snapshot |
| Bar | instrument_id, OHLCV, timeframe, timestamp | Aggregated market data |
| MarketDepth | instrument_id, bids, asks, timestamp | Order book snapshot |
| OptionChain | underlying_id, strikes, expiries, greeks | Options analytics input |
| Instrument | instrument_id, symbol, exchange, asset_class, type | Canonical instrument definition |
| Account | account_id, balance, margin, equity | Account state |
| Trade | trade_id, order_id, instrument_id, price, quantity, side | Executed fill |

### 3.4 Order State Machine

```
PENDING → SUBMITTED → PARTIALLY_FILLED → FILLED
                   → CANCELLED
                   → REJECTED
                   → UNKNOWN (ambiguous network; resolved by reconciliation)
```

Illegal transitions fail fast. UNKNOWN is never invented as REJECTED.

### 3.5 Value Objects

All value objects are immutable (frozen dataclasses):

| Value Object | Fields | Notes |
|--------------|--------|-------|
| InstrumentId | value: str | Canonical identifier |
| OrderId | value: str | Venue or internal ID |
| AccountId | value: str | Trading account |
| StrategyId | value: str | Strategy instance |
| ComponentId | value: str | Framework component |
| Money | amount: Decimal, currency: Currency | Decimal-based, no float |
| Price | value: Decimal | Tick-size aware |
| Quantity | value: Decimal | Lot-size aware |
| CorrelationId | value: UUID | Mandatory on order intents |
| TimeFrame | value: str | e.g. 1m, 5m, 1d |

### 3.6 Enumerations

| Enum | Values |
|------|--------|
| OrderSide | BUY, SELL |
| OrderType | MARKET, LIMIT, STOP, STOP_LIMIT |
| OrderStatus | PENDING, SUBMITTED, PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED, UNKNOWN |
| TimeInForce | DAY, IOC, GTC |
| Environment | REPLAY, BACKTEST, PAPER, LIVE |
| ExecutionTargetKind | REPLAY, SIMULATED, PAPER, BROKER |
| BrokerId | DHAN, UPSTOX, PAPER |
| ExchangeId | NSE, BSE, MCX |
| AssetClass | EQUITY, DERIVATIVE, COMMODITY, CURRENCY |
| InstrumentType | EQUITY, FUTURE, OPTION, INDEX |
| OptionType | CALL, PUT |
| SignalDirection | BUY, SELL, NEUTRAL |
| RiskLevel | INFO, WARNING, CRITICAL |
| DriftSeverity | LOW, MEDIUM, HIGH |

### 3.7 Message Hierarchy

All framework messages inherit from a base Message:

```python
@dataclass(frozen=True)
class Message:
    timestamp: Timestamp      # UTC, nanosecond precision
    correlation_id: UUID | None = None
    source: ComponentId | None = None
```

| Category | Messages |
|----------|----------|
| Data | Quote, Trade, Bar, OrderBook, Tick |
| Order | OrderCommand, OrderPlaced, OrderFilled, OrderCancelled, OrderRejected, OrderModified |
| Portfolio | PositionUpdated, AccountUpdated, PnLUpdated |
| Risk | RiskCheckResult, RiskRejected, RiskAlert, AutoFlattenOrder |
| System | Startup, Shutdown, ComponentHealth, ReconciliationDrift, ReconciliationCompleted, BrokerDisconnected, BrokerReconnected, ReplayStarted, ReplayCompleted, FeatureComputed |
| Analytics | SignalGenerated, ScanCompleted, BacktestCompleted, RankingUpdated |

### 3.8 Port Protocols

```python
class Strategy(Protocol):
    strategy_id: StrategyId
    def on_start(self, event: StartEvent) -> None: ...
    def on_stop(self, event: StopEvent) -> None: ...
    def on_quote(self, quote: Quote) -> None: ...
    def on_bar(self, bar: Bar) -> None: ...
    def on_fill(self, fill: OrderFilled) -> None: ...
    def on_event(self, event: Message) -> None: ...

class BrokerAdapter(Protocol):
    # Composes: MarketDataPort, ExecutionPort, StreamingPort, DataProvider, ExecutionProvider
    def submit_order(self, command: OrderCommand) -> OrderId: ...
    def cancel_order(self, order_id: OrderId) -> None: ...
    def get_quote(self, instrument_id: InstrumentId) -> Quote: ...
    def mass_status(self) -> BrokerSnapshot: ...

class FillSource(Protocol):
    def submit(self, command: OrderCommand) -> OrderResult: ...
    def cancel(self, order_id: OrderId) -> CancelResult: ...
    def modify(self, order_id: OrderId, command: OrderCommand) -> ModifyResult: ...

class RiskModel(Protocol):
    def check_order(self, command: OrderCommand, context: RiskContext) -> RiskCheckResult: ...
    def check_position(self, position: Position, context: RiskContext) -> RiskCheckResult: ...
    def check_account(self, account: Account, context: RiskContext) -> RiskCheckResult: ...

class PortfolioModel(Protocol):
    def rebalance(self, signals: list[Signal], context: PortfolioContext) -> list[OrderCommand]: ...
    def optimize(self, signals: list[Signal], context: PortfolioContext) -> list[OrderCommand]: ...

class Clock(Protocol):
    def now(self) -> Timestamp: ...
    def advance(self, delta: timedelta) -> None: ...  # FakeClock only

class EventBusPort(Protocol):
    def subscribe(self, msg_type: type, handler: Callable) -> Subscription: ...
    def publish(self, message: Message) -> None: ...
```

### 3.9 Component Lifecycle Base

```python
class ComponentState(Enum):
    UNINITIALIZED = "UNINITIALIZED"
    INITIALIZED   = "INITIALIZED"
    RUNNING       = "RUNNING"
    STOPPED       = "STOPPED"
    ERROR         = "ERROR"

class Component(ABC):
    component_id: ComponentId
    state: ComponentState

    def initialize(self) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def reset(self) -> None: ...
    def health_check(self) -> ComponentHealth: ...
```

Valid transitions: UNINITIALIZED → INITIALIZED → RUNNING → STOPPED; RUNNING → ERROR; STOPPED → INITIALIZED (reset). Invalid transitions raise LifecycleError.

### 3.10 Domain Invariants

1. All messages are immutable (frozen dataclasses)
2. Money and Price use Decimal, never float
3. Timestamps are UTC with nanosecond precision
4. correlation_id is mandatory on OrderCommand
5. Order FSM transitions are validated before cache update
6. ReconciliationEngine has zero side effects
7. Wire identifiers never appear in domain entities
8. ExecutionTargetKind resolved once at composition; never changed at runtime
9. Feature values computed before strategy callbacks (pipeline ordering)

---

## 4. Message Bus and Lifecycle

> Full specification: [03-message-bus-and-lifecycle.md](03-message-bus-and-lifecycle.md)

### 4.1 MessageBus — The Spinal Cord

Every component publishes and subscribes to messages through it. No direct method calls between subsystems.

```
┌──────────────────────────────────────────────────────────────┐
│                        MessageBus                            │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │  Sync       │  │  Async       │  │  Dead Letter       │  │
│  │  Dispatcher │  │  Dispatcher  │  │  Queue (DLQ)       │  │
│  └──────┬──────┘  └──────┬───────┘  └────────┬───────────┘  │
│         └────────────────┼────────────────────┘              │
│                    Subscriber Registry                        │
│                    MessageBusMetrics                          │
└──────────────────────────────────────────────────────────────┘
```

**Principles:**
- Zero-copy: messages are frozen dataclasses (immutable)
- Async by default: subscribers run in separate threads/async tasks
- Backpressure: queue size limits prevent memory exhaustion
- Replay: optional message log enables backtesting
- Single instance: one MessageBus per runtime
- Typed dispatch: handlers registered by message type

**Interface:**
```python
class MessageBus:
    def subscribe(self, msg_type: type, handler: MessageHandler) -> Subscription: ...
    def unsubscribe(self, subscription: Subscription) -> None: ...
    def publish(self, message: Message) -> None: ...
    async def run(self) -> None: ...
    def stop(self) -> None: ...
    def replay(self, start: Timestamp, end: Timestamp) -> None: ...
```

### 4.2 Message Routing

```python
class MessageRouter:
    def route(self, msg_type: type, *, instrument=None, strategy=None, account=None) -> RouteBuilder: ...
    def wire(self, msg_type: type, handler: MessageHandler, *, instrument=None, strategy=None) -> None: ...
```

| Route | Target |
|-------|--------|
| All OrderCommand | ExecutionEngine.on_order_command |
| OrderFilled for RELIANCE | strategy_1.on_fill |
| OrderFilled for TCS | strategy_2.on_fill |
| All Bar | all registered strategies.on_bar |
| All RiskRejected | audit sink + operator alert |

### 4.3 Component Lifecycle

```
initialize(config) → start() → [running: process messages] → stop() → reset()
```

**Startup Order:**
1. ConfigManager → 2. MessageBus → 3. TradingCache → 4. DataEngine → 5. RiskEngine → 6. ExecutionEngine → 7. StrategyEngine → 8. BrokerAdapter (via composition root) → 9. ReconciliationEngine

**Shutdown Order:** Reverse of startup. BrokerAdapter stops first; MessageBus stops last.

### 4.4 Message Log (Core — Not Optional)

The durable event log is core infrastructure for deterministic replay:

```python
class MessageLog(Protocol):
    def append(self, message: Message) -> None: ...
    def read(self, start: Timestamp, end: Timestamp) -> Iterator[Message]: ...
    def read_session(self, session_id: SessionId) -> Iterator[Message]: ...
    def clear(self) -> None: ...
```

Every published message is persisted when replay mode is enabled. ReplayEngine reads the log and republishes through the same MessageBus and ExecutionEngine used in live.

### 4.5 Dead-Letter Queue

Messages that fail handler processing go to a DLQ with handler identity and exception. Operator can inspect, retry, or discard via CLI/API.

### 4.6 Invariants

1. Single MessageBus instance per runtime
2. All inter-component communication via publish/subscribe
3. Messages are immutable; handlers must not mutate
4. Component.start() registers subscriptions; stop() cancels them
5. LifecycleManager.start_all() only after all initialize() succeed
6. stop_all() runs in reverse registration order
7. Replay uses identical handlers as live (four-mode parity)
8. Durable event log append before dispatch when replay enabled
9. Order commands published on priority queue above market data

---

## 5. Execution Engine and OMS

> Full specification: [04-execution-and-oms.md](04-execution-and-oms.md)

### 5.1 Purpose

The ExecutionEngine is the framework's heart. It owns order lifecycle, position tracking, and risk enforcement. Zero-parity is structural: the engine does not know if it runs against a simulator or a live broker.

### 5.2 OMS Components

| Component | Responsibility |
|-----------|----------------|
| OrderManager | Order FSM, idempotency, cache upsert |
| PositionManager | Position projection from fills, PnL |
| RiskManager | Pre-trade RiskGate, capital alignment |
| ReconciliationEngine | Compare local vs broker snapshot (pure domain) |
| TradingCache | Authoritative in-memory state (Nautilus Cache equivalent) |
| ExecutionEngine | Orchestrates order path, fill processing |
| TradingOrchestrator | Multi-strategy session coordination |
| ProcessedTradeRepository | Fill dedup by trade_id |

### 5.3 Four-Mode Parity Contract

| Mode | FillSource | Clock | ExecutionEngine Code |
|------|------------|-------|---------------------|
| REPLAY | Engine replay from MessageLog | FakeClock | Identical |
| BACKTEST | SimulatedFillSource | FakeClock | Identical |
| PAPER | PaperFillSource | SystemClock | Identical |
| LIVE | BrokerFillSource | SystemClock | Identical |

Only FillSource, Clock, and DataSource differ at composition time.

### 5.4 Forbidden: Bypass Paths

**Explicitly forbidden:**
- Alternate OMS adapter that places orders outside ExecutionEngine
- Direct BrokerAdapter calls from strategies or scanners
- Second order FSM with different transition rules
- Mode-specific RiskEngine or OrderManager implementations

Architecture tests must fail if any bypass path exists.

### 5.5 Order Flow (The Spine)

```
Orchestrator → OrderServicePort.place(intent, correlation_id)
  → IdempotencyGuard.check_and_reserve
  → RiskEngine.check_order
      denied  → MessageBus(RISK_REJECTED) — no venue call
      approved → ExecutionEngine → FillSource.submit → Venue
                 Venue ack/reject → Cache upsert (Order FSM) → MessageBus(ORDER_PLACED|ORDER_REJECTED)
                 Venue fill → ExecutionEngine.record_trade (idempotent on trade_id)
                   → Cache order status FSM → MessageBus(TRADE_APPLIED)
                   → PositionManager.apply_trade → MessageBus(POSITION_*)
```

### 5.6 Denial vs Rejection

| Event | Meaning |
|-------|---------|
| RISK_REJECTED | Local risk denied; never reached venue |
| ORDER_REJECTED | Venue proved non-acceptance |
| UNKNOWN | Ambiguous network failure; resolved by reconciliation, never invented as REJECTED |

### 5.7 FillSource Implementations

| FillSource | Mode | Behavior |
|------------|------|----------|
| ReplayFillSource | REPLAY | Reads durable MessageLog; republishes events through same MessageBus |
| SimulatedFillSource | BACKTEST | Immediate fill at bar close or configured slippage model |
| PaperFillSource | PAPER | Uses live market data for pricing; simulates fills |
| BrokerFillSource | LIVE | Delegates to BrokerAdapter.submit_order / cancel_order |

### 5.8 Reconciliation

```
BrokerAdapter.mass_status/positions/funds → ExecutionEngine
  → ReconciliationEngine.compare(local Cache, broker snapshot)
  → for each HIGH/MEDIUM drift: Cache upsert (FSM-validated) + RiskEngine capital refresh
  → MessageBus(RECONCILIATION_DRIFT) if any
  → MessageBus(RECONCILIATION_COMPLETED)
```

**Triggers:** On broker connect/reconnect, on periodic mass-status, on any UNKNOWN submission outcome.

### 5.9 TradingContext

```python
@dataclass
class TradingContext:
    cache: TradingCache
    clock: Clock
    environment: Environment
    account: Account
    positions: dict[InstrumentId, Position]
    open_orders: list[Order]
```

Strategies receive TradingContext snapshots; they do not mutate cache directly.

### 5.10 Trading State

| State | Meaning | Accepts Orders? |
|-------|---------|-----------------|
| READY | Normal operation | Yes |
| DEGRADED | Partial reconciliation or non-critical drift | Yes, with warnings |
| HALTED | Kill switch or critical failure | No |
| RECONCILING | Reconciliation in progress after reconnect | No |

### 5.11 Invariants

1. Single ExecutionEngine wiring at boot
2. No bypass order paths — architecture test enforced
3. RiskGate checked before every venue I/O
4. IdempotencyGuard checked before RiskGate
5. Order FSM transitions validated before cache update
6. Fill processing idempotent on trade_id
7. Reconciliation applied inside ExecutionEngine, not detached service
8. UNKNOWN never mapped to REJECTED without venue proof
9. Same code path in REPLAY, BACKTEST, PAPER, LIVE
10. TradingOrchestrator never calls BrokerAdapter directly

---

## 6. Strategy and Analytics

> Full specification: [05-strategy-and-analytics.md](05-strategy-and-analytics.md)

### 6.1 Strategy System (Inversion of Control)

Users implement the Strategy protocol. The framework:
1. Registers strategy with StrategyEngine
2. Routes relevant messages (Bar, Quote, OrderFilled) via MessageBus
3. Invokes on_start, on_bar, on_quote, on_fill, on_stop
4. Collects order intents from strategy output

### 6.2 Isolation Invariant

Strategies and scanners **must not** import or call:
- OrderManager, PositionManager, ExecutionEngine
- BrokerAdapter or any concrete broker module
- Runtime composition root

All order flow goes: Strategy → MessageBus → ExecutionEngine.

Trading must remain usable with **zero strategies loaded**.

### 6.3 Scanner System

```
InstrumentMaster → Scanner.scan() → list[Signal]
  → PortfolioModel.rebalance(signals) → list[OrderCommand]
  → MessageBus.publish(OrderCommand) → ExecutionEngine
```

Scanners produce signals; they do not place orders directly.

### 6.4 FeaturePipeline

```
MarketDataEngine → FeaturePipeline → Indicators → StrategyEngine
```

FeaturePipeline runs before strategy.on_bar(). Strategies receive enriched bars with pre-computed features and indicators.

### 6.5 Analytics Suite

| Module | Responsibility |
|--------|----------------|
| BacktestEngine | Historical simulation through same ExecutionEngine |
| ReplayEngine | Event-sourced replay from MessageLog |
| PaperTradingEngine | Live data + PaperFillSource |
| LiveTradingEngine | Live data + BrokerFillSource |
| WalkForwardEngine | Parameter optimization across rolling windows |
| ScannerEngine | Momentum, breakout, volume, relative-strength scans |
| RankingEngine | Universe ranking by metric |
| SectorAnalyzer | Rotation, strength, volume by sector |
| OptionsAnalytics | Greeks, chain analysis |
| FuturesAnalytics | Contract analytics |
| VolatilityAnalytics | IV, historical vol, skew |
| OrderFlowAnalytics | Bid/ask imbalance, delta |
| MarketBreadthAnalytics | Advance/decline, new highs/lows |
| VolumeProfileBuilder | Volume-at-price profiles |
| ProbabilityEngine | Signal probability scoring |
| FundamentalsAnalytics | Financial ratio analysis |
| IntradayAnalytics | Session-based intraday patterns |
| StockAnalytics | Per-stock deep analysis |
| ReportEngine | PnL, drawdown, Sharpe, trade statistics |
| StatisticsEngine | Domain-level metric computation |

### 6.6 Four-Mode Engine Comparison

| Aspect | ReplayEngine | BacktestEngine | PaperTradingEngine | LiveTradingEngine |
|--------|--------------|----------------|--------------------|--------------------|
| Clock | FakeClock | FakeClock | SystemClock | SystemClock |
| FillSource | Replay (from log) | SimulatedFillSource | PaperFillSource | BrokerFillSource |
| Data | MessageLog | Datalake | Live adapter | Live adapter |
| ExecutionEngine | Identical | Identical | Identical | Identical |
| FeaturePipeline | Identical | Identical | Identical | Identical |
| RiskEngine | Identical | Identical | Identical | Identical |

### 6.7 Indicator Library

Pure functions in domain layer (no I/O):

| Category | Indicators |
|----------|------------|
| Trend | SMA, EMA, WMA, VWMA |
| Momentum | RSI, MACD, ROC, CCI |
| Volatility | ATR, Bollinger, Keltner |
| Volume | OBV, VWAP, MFI |
| Pattern | Candlestick patterns |
| HalfTrend | HalfTrend trend-following indicator |

### 6.8 Analytics-First CLI Commands

| Command Group | Subcommands | Purpose |
|---------------|-------------|---------|
| scanner | momentum, breakout, volume, rs | Universe scans |
| indicator | halftrend, halftrend_scan | Indicator analysis |
| strategy | list, run | Strategy management |
| backtest | run, replay, optimize, walkforward, paper | Simulation modes |
| market | breadth, sector, sector_rotation, sector_strength, sector_volume | Market structure |
| support | levels, nearest | Support/resistance |
| fundamentals | — | Financial analysis |
| report | — | Performance reports |
| config | get, set, list, reset, validate | Configuration |
| live | — | Live trading (with safety gates) |
| paper | — | Paper trading session |

### 6.9 Invariants

1. Strategies communicate only via MessageBus
2. Zero strategies loaded must not break OMS/execution
3. All four modes use same ExecutionEngine (four-mode parity)
4. FeaturePipeline runs before strategy callbacks
5. Indicators are pure functions (domain layer)
6. PortfolioModel produces OrderCommands, not direct venue calls
7. Scanner output is signals, not orders
8. ReplayEngine reproduces identical state from MessageLog
9. Analytics modules are read-only on OMS state (no direct cache mutation)

---

## 7. Broker Adapter Framework

> Full specification: [06-broker-adapter-framework.md](06-broker-adapter-framework.md)

### 7.1 Architecture Pattern: Gateway → Connection → Sub-Adapters

```
BrokerGateway (implements BrokerAdapter)
  └── BrokerConnection (owns transport, lifecycle)
        ├── OrdersAdapter      (place, cancel, modify, orderbook, tradebook)
        ├── MarketDataAdapter  (quote, ltp, depth, history, chains)
        ├── PortfolioAdapter   (positions, holdings, funds)
        ├── InstrumentAdapter  (load, resolve, search)
        └── StreamingAdapter   (quotes, depth, order updates)
```

### 7.2 Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| BrokerGateway | Thin facade implementing BrokerAdapter; delegates to BrokerConnection |
| BrokerConnection | Owns HTTP/WebSocket transport, sub-adapters, lifecycle |
| OrdersAdapter | Order placement, cancellation, modification |
| MarketDataAdapter | Quotes, LTP, depth, historical, option/future chains |
| PortfolioAdapter | Positions, holdings, funds, balances |
| InstrumentAdapter | Instrument loading, symbol resolution, search |
| StreamingAdapter | WebSocket subscriptions for quotes, depth, order updates |
| WireMapper | Broker-native payload ↔ domain types |
| Transport | HTTP client, WebSocket client with rate limiting |

### 7.3 Plugin Registration

Each broker plugin self-registers at import time:

```python
@dataclass(frozen=True)
class BrokerPlugin:
    broker_id: BrokerId
    env_file: str
    default_mode: Environment
    supported_modes: frozenset[Environment]
    is_live: bool
    capabilities: BrokerCapabilities
```

Entry-point discovery:
```
tradex.brokers:
  dhan   → plugins.brokers.dhan
  upstox → plugins.brokers.upstox
  paper  → plugins.brokers.paper
```

Runtime resolves broker **once at startup** via BrokerId enum. No string equality branching.

### 7.4 Target Layout per Provider

```
plugins/brokers/{provider}/
  __init__.py          # Self-registration, BrokerPlugin metadata
  gateway.py           # Gateway implements BrokerAdapter
  connection.py        # Connection owns transport + sub-adapters
  orders.py            # OrdersAdapter
  market_data.py       # MarketDataAdapter
  portfolio.py         # PortfolioAdapter
  instruments.py       # InstrumentAdapter
  streaming.py         # StreamingAdapter
  wire.py              # WireMapper (native ↔ domain)
  transport.py         # HTTP + WebSocket clients
  auth.py              # TOTP, token store
  reconciliation.py    # Mass status, drift detection
  config.py            # Provider-specific config schema
```

### 7.5 Common Infrastructure

| Component | Responsibility |
|-----------|----------------|
| BaseWireAdapter | Enum mapping, decimal/datetime normalization |
| BaseTransport | HTTP client abstraction with retries |
| SymbolResolver | Canonical (symbol, exchange) → venue InstrumentRef |
| QuoteNormalizer | Venue quote → domain Quote |
| RateLimitConfig | Per-broker rate limit definitions |

Wire identifiers never leak past gateway boundary — callers use canonical InstrumentId only.

### 7.6 Connection Lifecycle

Standardized across all providers:
```
connect() → authenticate() → load_instruments() → ready
disconnect() → flush() → close_transport()
health_check() → ConnectionHealth
```

### 7.7 BrokerHealthMonitor

| Check | Pass | Fail Action |
|-------|------|-------------|
| WebSocket connected | Connected within 30s of start | Alert + reconnect policy |
| Auth token valid | Token not expired | Refresh or halt |
| Reconciliation complete | No HIGH drift | DEGRADED until healed |
| Mass status responsive | Response within timeout | Circuit breaker trip |

### 7.8 Invariants

1. Application layer never imports concrete broker modules
2. Runtime is sole layer permitted concrete broker imports
3. All gateways implement identical BrokerAdapter protocol
4. Wire identifiers never leak to gateway callers
5. Self-registration via entry points; no central switch
6. Connection lifecycle standardized across providers
7. Rate limiting enforced at transport boundary
8. Status mapping centralized in StatusMapperRegistry
9. BrokerHealthMonitor mandatory for Live/Paper modes
10. Reconnect triggers reconciliation before accepting new risk

---

## 8. Data Infrastructure

> Full specification: [07-data-infrastructure.md](07-data-infrastructure.md)

### 8.1 Unified DataEngine

```
┌─────────────────────────────────────────────────────────────┐
│                      DataEngine                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Live Ticks  │  │  Historical  │  │  DataLake        │  │
│  │  (StreamOrch)│  │  Fetch       │  │  (DuckDB+Parquet)│  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         └─────────────────┼────────────────────┘            │
│                    SourceSelectionPolicy                    │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 Market Data Flow

```
Broker WebSocket/REST → WireMapper → Quote/Bar/Tick (domain)
  → MarketDataEngine → TradingCache.set_quote(instrument_id, quote)
  → MessageBus.publish(QUOTE|TICK|BAR)
  → Strategy/Orchestrator handler
```

**Cache-Then-Publish Invariant:** Quote is written to TradingCache **before** event publishes.

### 8.3 Datalake Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      DATALAKE                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Ingestion│  │ Storage  │  │ Quality  │  │ Analytics│   │
│  │ Federated│  │ Parquet  │  │ Validate │  │ SQL Views│   │
│  │ Sync     │  │ DuckDB   │  │ Health   │  │ Greeks   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│  ┌──────────┐  ┌──────────┐                                 │
│  │ Core     │  │ MCP      │                                 │
│  │ Schema   │  │ Server   │                                 │
│  └──────────┘  └──────────┘                                 │
└─────────────────────────────────────────────────────────────┘
```

### 8.4 Data Pipeline (ETL)

| Stage | Input | Output |
|-------|-------|--------|
| Extract | External APIs, broker historical, CSV | Raw DataFrames |
| Transform | Raw data | Normalized bars, instruments |
| Load | Clean data | Parquet files, DuckDB tables |
| Quality | Loaded data | Validation report, gap alerts |
| Materialize | Loaded data | Analytics views |

### 8.5 Storage Layout

```
datalake/
├── raw/           # Raw tick data (partitioned by exchange/symbol/date)
├── bars/          # OHLCV bars (1m/, 5m/, 1d/ partitions)
├── options/       # Option chain snapshots (NIFTY/, BANKNIFTY/)
└── catalog.db     # DuckDB metadata + analytics engine
```

### 8.6 SourceSelectionPolicy

Resolution order for historical data: datalake local → broker historical → federated sync.

---

## 9. Risk and Safety

> Full specification: [09-risk-and-safety.md](09-risk-and-safety.md)

### 9.1 Risk System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    RISK SYSTEM                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Pre-Trade   │  │  Post-Trade  │  │  Circuit Breaker │  │
│  │  RiskGate    │  │  Monitor     │  │  Kill Switch     │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐                         │
│  │  Loss Limit  │  │  Order Limit │                         │
│  │  (Daily)     │  │  (Per-Day)   │                         │
│  └──────────────┘  └──────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

### 9.2 Pre-Trade RiskGate

Mandatory check before every venue I/O:

```python
class RiskModel(Protocol):
    def check_order(self, command: OrderCommand, context: RiskContext) -> RiskCheckResult: ...
    def check_position(self, position: Position, context: RiskContext) -> RiskCheckResult: ...
    def check_account(self, account: Account, context: RiskContext) -> RiskCheckResult: ...
```

### 9.3 Indian Market Risk Rules

| Rule | Description |
|------|-------------|
| STT (Securities Transaction Tax) | Tax on equity delivery and intraday |
| Margin requirements | Exchange-mandated margin for F&O |
| Circuit limits | Upper/lower circuit breakers per instrument |
| Position limits | Maximum position size per instrument/account |
| Trading hours | NSE: 9:15 AM – 3:30 PM IST |

### 9.4 Post-Trade Monitor

Monitors positions and triggers risk actions:
- Drawdown alerts when unrealized PnL exceeds threshold
- Auto-flatten when loss exceeds configurable threshold
- Circuit breaker trips on daily loss limit breach

### 9.5 Kill Switch

Manual or automatic trigger that:
- Immediately halts all order submission
- Cancels all open orders
- Publishes HALTED state via MessageBus
- Requires manual operator intervention to resume

### 9.6 Audit Requirements

Every order lifecycle event must be auditable:

| Event | Audit Fields |
|-------|-------------|
| OrderCommand received | correlation_id, instrument, side, qty, timestamp |
| RiskCheck | approved, reason, limits checked |
| Venue submission | order_id, venue response, latency |
| Fill | trade_id, price, qty, timestamp |
| Reconciliation | drift items, severity, actions taken |
| Kill switch | reason, operator, timestamp |

Audit sink is append-only. No deletion or modification of audit records.

### 9.7 Invariants

1. RiskGate bound before accepting traffic
2. RiskGate checked before every venue I/O
3. IdempotencyGuard checked before RiskGate
4. Loss circuit breaker trip halts all order submission
5. Kill switch is manual-reset only
6. Risk limits cannot be relaxed at runtime
7. Indian market hours enforced for LIVE mode
8. Audit log captures every risk decision

---

## 10. Observability and Operations

> Full specification: [10-observability-and-ops.md](10-observability-and-ops.md)

### 10.1 Observability Stack

```
┌─────────────────────────────────────────────────────────┐
│                  OBSERVABILITY STACK                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Structured  │  │   Metrics    │  │   Tracing    │  │
│  │  Logging     │  │  Collection  │  │  (OpenTel)   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│  ┌──────────────┐  ┌──────────────┐                     │
│  │  Health      │  │  Audit       │                     │
│  │  Checks      │  │  Sink        │                     │
│  └──────────────┘  └──────────────┘                     │
└─────────────────────────────────────────────────────────┘
```

### 10.2 Structured Logging

Logging uses **structlog** for JSON output with bound context (component_id, correlation_id, session_id).

| Level | Events |
|-------|--------|
| DEBUG | Message bus dispatch, cache reads |
| INFO | Order submitted, fill received, component started |
| WARNING | Risk rejected, reconciliation drift (LOW/MEDIUM) |
| ERROR | Venue rejection, parse failure, handler exception |
| CRITICAL | Kill switch tripped, reconciliation HIGH drift, HALTED |

### 10.3 Built-In Metrics

| Metric | Type | Labels |
|--------|------|--------|
| orders_submitted_total | Counter | broker, side, instrument |
| orders_filled_total | Counter | broker, side, instrument |
| orders_rejected_total | Counter | broker, reason |
| risk_rejected_total | Counter | reason |
| order_latency_seconds | Histogram | broker, operation |
| fill_latency_seconds | Histogram | broker |
| position_count | Gauge | account |
| unrealized_pnl | Gauge | account |
| message_bus_queue_depth | Gauge | component |
| reconciliation_drift_total | Counter | severity |
| broker_connected | Gauge | broker_id |
| component_health | Gauge | component_id, state |

### 10.4 Health Checks

| Probe | Checks | Use |
|-------|--------|-----|
| Liveness | Process running, no deadlock | Restart if fails |
| Readiness | All components RUNNING, broker connected, reconciliation done | Route traffic if passes |

### 10.5 AlertingEngine

| Alert | Trigger | Severity | Action |
|-------|---------|----------|--------|
| BrokerDisconnected | WS disconnect > 30s | WARNING | Reconnect policy |
| ReconciliationHighDrift | HIGH severity drift | CRITICAL | HALTED + operator notify |
| LossCircuitBreakerTripped | daily_pnl threshold | CRITICAL | HALTED |
| KillSwitchTripped | Manual or auto trip | CRITICAL | HALTED |
| QueueBackpressure | MessageBus queue > 80% | WARNING | Log + metric |
| ComponentError | Component state == ERROR | CRITICAL | HALTED |

### 10.6 Invariants

1. Every order path produces trace spans
2. Every order state transition produces audit record
3. Metrics exported via OpenTelemetry protocol
4. Health checks exposed on HTTP endpoint
5. No secrets in logs, metrics labels, or traces
6. Audit sink is append-only
7. Component health checked by LifecycleManager periodically
8. AlertingEngine publishes on all CRITICAL risk/system events
9. BrokerHealthMonitor metrics included in readiness probe

---

## 11. Configuration and Developer Experience

> Full specification: [11-configuration-and-dx.md](11-configuration-and-dx.md)

### 11.1 Declarative Configuration (YAML)

```yaml
# config/trading.yaml
environment: PAPER          # REPLAY | BACKTEST | PAPER | LIVE
broker: dhan                  # dhan | upstox | paper

components:
  message_bus:
    max_queue_size: 10000
    persistent_log: false
  execution:
    default_order_type: MARKET
  risk:
    max_order_size: 1000
    max_position_size: 5000
    max_daily_loss: 50000
    max_orders_per_day: 100
  data:
    datalake_path: ./data/lake
    default_timeframe: 1m

strategies:
  - id: momentum_v1
    class: strategies.momentum.MomentumStrategy
    params:
      lookback: 20
      threshold: 0.02

logging:
  level: INFO
  format: json

observability:
  metrics_enabled: true
  tracing_enabled: true
  otlp_endpoint: http://localhost:4317
```

### 11.2 Configuration Hierarchy

Resolved in order (later overrides earlier):
1. Built-in defaults
2. Base YAML (`config/tradex.yaml`)
3. Profile overlay (`config/profiles/{profile}.yaml`)
4. Environment variables (`TRADEX_*` prefix)
5. CLI overrides (`--config key=value`)

### 11.3 Environment Profiles

| Profile | Environment | Broker | Risk Limits |
|---------|-------------|--------|-------------|
| replay.yaml | REPLAY | paper | Relaxed |
| backtest.yaml | BACKTEST | paper | Relaxed |
| paper.yaml | PAPER | dhan/upstox | Moderate |
| live.yaml | LIVE | dhan/upstox | Strict |

LIVE profile requires explicit enablement flag.

### 11.4 Component Wiring

```python
class RuntimeFactory:
    @staticmethod
    def build(config: AppConfig) -> Runtime:
        bus = MessageBus(config.components.message_bus)
        clock = resolve_clock(config.environment)
        fill_source = resolve_fill_source(config.environment, config.broker)
        cache = TradingCache()
        risk = RiskManager(config.components.risk)
        execution = ExecutionEngine(bus, fill_source, cache, risk, clock)
        return Runtime(bus, execution, cache, ...)
```

### 11.5 TradingNode (Public Entry Point)

```python
class TradingNode:
    @classmethod
    def from_config(cls, path: str) -> TradingNode: ...

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def submit_order(self, intent: OrderIntent) -> OrderResult: ...
    def cancel_order(self, order_id: OrderId) -> CancelResult: ...
    def query_positions(self) -> list[Position]: ...
    def query_pnl(self) -> PnLReport: ...
```

### 11.6 Interface Matrix

| Surface | Purpose | Mode Support |
|---------|---------|--------------|
| Click CLI | Analytics-first research + trading | All four modes |
| Textual TUI | Terminal trading dashboard | Paper, Live |
| FastAPI REST | Programmatic access | All modes |
| MCP Server | Datalake queries for external tools | Read-only |
| Interactive shell | REPL exploration | All modes |

### 11.7 Developer Workflow

```
1. Define strategy (implement Strategy protocol)
2. Configure backtest profile
3. Run: tradex backtest --strategy my_strategy
4. Review report
5. Configure sandbox profile
6. Run: tradex paper --strategy my_strategy
7. Monitor via TUI/API
8. Configure live profile with strict risk limits
9. Run: tradex live --strategy my_strategy --confirm
```

### 11.8 Invariants

1. Same strategy code runs in backtest, paper, and live
2. Configuration drives all wiring; no code changes between environments
3. CLI provides discoverable commands with --help
4. Config validation fails fast at startup
5. LIVE requires explicit --confirm flag
6. Plugin development follows standard entry-point pattern

---

## 12. Testing and Quality

> Full specification: [12-testing-and-quality.md](12-testing-and-quality.md)

### 12.1 Test Pyramid

```
                    ┌─────────┐
                    │   E2E   │  Full session flows
                   ┌┴─────────┴┐
                   │ Integration │  Broker adapters, datalake
                  ┌┴─────────────┴┐
                  │  Component     │  OMS, execution, risk
                 ┌┴───────────────┴┐
                 │     Unit         │  Domain, messages, FSM
                 └───────────────────┘
```

| Layer | Scope | Target Share | Examples |
|-------|-------|--------------|----------|
| Unit | Pure domain logic, FSM, messages, lifecycle | ~70% | Order FSM, ComponentState transitions, RiskRule logic |
| Component | Single subsystem with real deps | ~15% | ExecutionEngine + SimulatedFillSource, MessageBus routing |
| Integration | Cross-subsystem with real broker sandbox | ~10% | Dhan adapter place/cancel, datalake roundtrip |
| E2E | Full session flows | ~5% | Replay → backtest → paper session |
| Architecture | Layer boundaries, flow contracts, graph degree | CI-blocking | Import linter, god-class degree ≤ 50, bypass scan |

### 12.2 Four-Mode Parity Tests

The parity gate verifies identical behavior across all four modes:

| Rule | Test |
|------|------|
| Same ExecutionEngine code | Import path identical across modes |
| Same RiskEngine code | Risk check produces same result given same context |
| Same Order FSM | All transitions tested identically |
| Same FeaturePipeline | Features computed identically given same bars |
| FillSource differs only | Replay/Simulated/Paper/Broker are the only delta |
| No bypass paths | Architecture test: zero alternate order paths |
| Parity gate never skipped in LIVE | LIVE mode rejects SKIP_PARITY_GATE |
| Replay determinism | MessageLog replay → identical cache snapshot |

### 12.3 AdapterTestHarness

Standardized test harness for broker adapter validation:

```python
class AdapterTestHarness:
    def test_connect(self) -> None: ...
    def test_get_quote(self, instrument_id: InstrumentId) -> None: ...
    def test_place_and_cancel(self, command: OrderCommand) -> None: ...
    def test_get_positions(self) -> None: ...
    def test_get_funds(self) -> None: ...
    def test_mass_status(self) -> None: ...
    def test_streaming(self, instrument_id: InstrumentId) -> None: ...
    def test_reconciliation(self) -> None: ...
    def test_wire_mapping_roundtrip(self) -> None: ...
```

### 12.4 Architecture Quality Gates

**Import Boundary Contracts:**

| Contract | Rule |
|----------|------|
| Domain purity | domain imports nothing from outer layers |
| Application isolation | application imports only domain |
| Runtime exclusivity | only runtime imports concrete brokers |
| Strategy isolation | strategies cannot import OMS/execution |

### 12.5 Test Markers

| Marker | Purpose |
|--------|---------|
| @pytest.mark.live | Requires live broker credentials |
| @pytest.mark.integration | Requires external services |
| @pytest.mark.slow | Long-running tests |
| @pytest.mark.parity | Zero-parity gate tests |

### 12.6 Quality Invariants

1. No mocked components in integration or E2E tests
2. Four-mode parity gate runs on every CI build
3. LIVE parity gate cannot be skipped
4. No bypass order paths — architecture test enforced
5. Architecture tests are CI-blocking
6. AdapterTestHarness required for every venue plugin
7. Flow contract markers verified by architecture tests
8. Replay determinism test: log replay → identical cache
9. Mutation testing on critical trading paths

---

## 13. Deployment

> Full specification: [13-deployment.md](13-deployment.md)

### 13.1 Containerization

Multi-stage Dockerfile:
- Stage 1 (builder): Install dependencies with uv
- Stage 2 (runtime): Copy .venv, source, config; non-root user

### 13.2 Kubernetes Deployment

| Constraint | Reason |
|------------|--------|
| replicaCount: 1 | Single trading instance; no concurrent order submission |
| No autoscaling | Trading state is in-memory; scaling requires state externalization |
| Persistent volume | Datalake and token state |
| PodDisruptionBudget: maxUnavailable: 0 | Prevent accidental termination during market hours |

### 13.3 CI/CD Pipeline

| Stage | Blocking | Frequency |
|-------|----------|-----------|
| Lint + Unit + Component + Architecture | Yes | Every push |
| Parity gate | Yes | Every push |
| Integration | Yes | Nightly + pre-release |
| E2E | Yes | Pre-release |
| Docker build | Yes | Every merge to main |
| Deploy staging | No | Automatic on main |
| Deploy production | Yes (manual) | Release tag only |

### 13.4 Release Checklist

- [ ] All CI stages pass (including parity gate)
- [ ] Four-mode parity gate passes
- [ ] Integration tests pass against broker sandbox
- [ ] E2E replay, backtest, and paper sessions verified
- [ ] CHANGELOG updated
- [ ] Version bumped in pyproject.toml
- [ ] Docker image built and scanned
- [ ] Staging deployment verified
- [ ] Manual approval for production
- [ ] Production deployment during market off-hours
- [ ] Post-deploy reconciliation verified
- [ ] Monitoring dashboards checked

### 13.5 Post-Deploy Reconciliation (LIVE)

Mandatory gates after every LIVE deployment:

| Gate | Pass Criteria | Failure Action |
|------|---------------|----------------|
| Venue connectivity | Broker adapter connected and authenticated | Roll back deploy; alert operator |
| Position reconciliation | No HIGH-severity drift vs broker | Block order submission; manual review |
| Order reconciliation | No UNKNOWN orders in cache | Reconcile or cancel orphans |
| RiskGate profile | LIVE limits loaded and active | Abort startup |
| Four-mode parity | Parity gate passed in CI for release tag | Block production deploy |
| Audit continuity | Audit sink receiving events | Fail readiness probe |

### 13.6 Disaster Recovery

| Scenario | Response |
|----------|----------|
| Pod crash | K8s restarts; reconciliation on reconnect |
| Broker API outage | Circuit breaker; queue orders; alert operator |
| Data corruption | Restore from Parquet backup; reconcile |
| Kill switch triggered | Manual reset required; audit review |
| Network partition | UNKNOWN orders; reconcile on reconnect |

### 13.7 Deployment Invariants

1. Single trading instance per account
2. Non-root container user
3. Health probes on every deployment
4. Production deploy requires manual approval
5. Post-deploy reconciliation mandatory
6. No secrets in images or config files
7. Four-mode parity gate passes before any production deploy

---

## 14. Data Flow Diagrams

> Full specification: [08-flows-and-dfds.md](08-flows-and-dfds.md)

### 14.1 DFD Level 0 — Context Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  External Entities                                           │
│  Operator (CLI/TUI/API)  ·  Broker APIs  ·  Data Sources   │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                    TradeXV2 Framework                        │
│  Commands/Config/Queries  ←→  Results/Reports/Logs          │
│  Orders/Cancellations    ←→  Market Data/Fills/Updates      │
│  Historical Data Requests←→  OHLCV/Instruments/Corp Actions │
└─────────────────────────────────────────────────────────────┘
```

### 14.2 DFD Level 1 — Major System Components

```
Operator → CLI/TUI/API → runtime/ → OMS/Execution/Analytics/Datalake
    ↕                       ↕                    ↕
Broker APIs ←→ Broker Gateway ←→ Domain Layer ←→ MessageBus
    ↕                                              ↕
Data Sources ←→ Datalake ←→ Analytics Views
```

### 14.3 DFD Level 2A — Brokers Module

```
Broker APIs (REST + WS)
    → HTTP Client → Wire Adapter → Domain Types
    → WebSocket → Wire Adapter → Domain Types
    → BrokerGateway → BrokerConnection
        ├── OrdersAdapter
        ├── MarketDataAdapter
        ├── PortfolioAdapter
        ├── InstrumentAdapter
        └── StreamingAdapter
    → Common Infrastructure (Rate Limiting, Idempotency, Capabilities)
```

### 14.4 DFD Level 2B — OMS & Execution Engine

```
Strategies → TradingOrchestrator → ExecutionEngine
    → RiskGate → OrderManager → FillSource → Broker Gateway
    → PositionManager ←→ TradingCache
    → ReconciliationService ←→ BrokerAdapter.mass_status
    → TradingContext (bundles all references)
```

### 14.5 DFD Level 2C — Analytics Module

```
FeaturePipeline ←→ StrategyPipeline ←→ BacktestEngine
    ↕                    ↕                    ↕
ScannerEngine      ReplayEngine      PaperTradingEngine
    ↕                    ↕                    ↕
RankingEngine      WalkForward      LiveTradingEngine
    ↕
Indicators / Sector / Options / Volatility / Breadth / Reports
```

### 14.6 DFD Level 2D — Datalake Module

```
Broker APIs → Ingestion (Federated Sync) → Parquet Storage
    ↕                                       ↕
Quality Engine ←→ DuckDB Analytics ←→ MCP Server
    ↕                                       ↕
DataCatalog ←→ SourceSelectionPolicy ←→ Analytics Consumers
```

### 14.7 DFD Level 2E — Runtime Composition Root

```
CLI/TUI/API → InterfaceCompose → RuntimeFactory
    → BrokerDiscovery → BrokerBuilders → BrokerInfrastructure
    → ExecutionTarget → ExecutionConfig
    → Composition (wire_domain_port_sinks)
    → ParityGate + ProductionConfig
    → LifecycleManager → ServiceRegistry
```

### 14.8 Flow 1: Order Placement (End-to-End)

```
Strategy → MessageBus → ExecutionEngine → IdempotencyGuard → RiskGate
    → [approved] → FillSource → BrokerGateway → BrokerAPI
    → [denied] → RISK_REJECTED (no venue call)
    → Venue Fill → ExecutionEngine.record_trade → OrderManager → PositionManager → MessageBus
```

### 14.9 Flow 2: Market Data Ingestion

```
Broker WebSocket → WireAdapter → TradingCache.set_quote → MessageBus.publish(QUOTE)
    → Strategy.on_quote → FeaturePipeline.on_bar → Indicators → StrategyEngine
    → RiskManager (position MTM update)
```

### 14.10 Flow 3: Reconciliation (Hot Path)

```
Broker reconnect → BrokerGateway.mass_status → ExecutionEngine.apply_mass_status
    → ReconciliationEngine.compare(local, broker)
    → DriftItems → Cache upsert (FSM-validated) → RiskManager.refresh_capital
    → MessageBus(RECONCILIATION_DRIFT | RECONCILIATION_COMPLETED)
```

---

## 15. Implementation Phases

> Full specification: [14-implementation-guide.md](14-implementation-guide.md)

### Phase 1: Foundation (Week 1–2)

| Task | Deliverable | Acceptance |
|------|-------------|------------|
| Domain model | Entities, value objects, enums, messages | All types importable; frozen dataclasses; Decimal for money |
| Port protocols | Strategy, BrokerAdapter, FillSource, RiskModel, Clock, EventBusPort | Protocol compliance testable |
| MessageBus | Subscribe, publish, routing, optional log | Unit tests: publish delivers to subscribers |
| Component + LifecycleManager | initialize/start/stop/reset lifecycle | Unit tests: lifecycle order enforced |
| Config schema | AppConfig Pydantic model, YAML loader | Validation rejects invalid config |
| Observability base | Structured logging, metrics interface | JSON log format verified |

**Exit criteria:** MessageBus routes messages; components follow lifecycle; config validates.

### Phase 2: Broker Adapter Framework (Week 3–4)

| Task | Deliverable | Acceptance |
|------|-------------|------------|
| Common infrastructure | Transport, idempotency, capabilities, status mapper | Unit tests pass |
| BrokerAdapter protocol | Full port composition | Protocol compliance test |
| Paper provider | PaperGateway, PaperOrders, PaperMarketData, PaperPortfolio | AdapterTestHarness pass |
| Dhan provider | Gateway, Connection, 5 sub-adapters, wire mapper, auth | AdapterTestHarness pass (sandbox) |
| Upstox provider | Gateway, Connection, 5 sub-adapters, wire mapper, auth | AdapterTestHarness pass (sandbox) |
| Plugin registration | Entry points, self-registration | Discovery finds all 3 brokers |

**Exit criteria:** All three brokers pass AdapterTestHarness; plugin discovery works.

### Phase 3: Execution Engine (Week 5)

| Task | Deliverable | Acceptance |
|------|-------------|------------|
| OrderManager | Order FSM with validated transitions | FSM tests: all transitions + illegal rejected |
| PositionManager | Position projection from fills | Fill → correct position state |
| RiskManager | Pre-trade RiskGate with configurable limits | Risk rejection prevents venue call |
| IdempotencyGuard | correlation_id dedup | Duplicate returns prior result |
| ExecutionEngine | Orchestrates order path via MessageBus | Component test: full order spine |
| FillSource implementations | Replay, Simulated, Paper, Broker | Four-mode parity test passes |
| ReconciliationEngine | Pure compare functions | Unit tests: drift severity correct |

**Exit criteria:** Order flow works end-to-end with PaperFillSource; four-mode parity test passes; no bypass paths.

### Phase 4: Composition Root (Week 6)

| Task | Deliverable | Acceptance |
|------|-------------|------------|
| RuntimeFactory | Build from AppConfig | All components wired correctly |
| PluginDiscovery | Entry-point broker/exchange resolution | BrokerId enum resolution |
| ExecutionTargetResolver | FillSource + Clock per mode | REPLAY/BACKTEST/PAPER/LIVE matrix correct |
| TradingCache | Authoritative in-memory state | Cache-then-publish verified |
| MessageLog | Durable event store | Append + replay verified |
| Startup flow | Boot checks, environment freeze | Missing RiskGate → abort |
| YAML profiles | replay, backtest, paper, live configs | Profile validation passes |

**Exit criteria:** `tradex replay`, `tradex backtest`, and `tradex paper` run full sessions.

### Phase 5: Strategy, Analytics, and Data (Week 7–8)

| Task | Deliverable | Acceptance |
|------|-------------|------------|
| FeaturePipeline | Market Data → features → indicators | Pipeline ordering test |
| StrategyEngine | Register, route messages, emit orders | Strategy receives enriched bars |
| ReplayEngine | Event-sourced replay from MessageLog | Deterministic replay test |
| BacktestEngine | Historical simulation | Backtest produces metrics |
| PaperTradingEngine | Live data + paper fills | Paper session test |
| LiveTradingEngine | Live data + broker fills | Live safety gates test |
| Scanner suite | Momentum, breakout, volume, RS | Scan pipeline test |
| Analytics modules | Ranking, sector, options, futures, volatility, orderflow, breadth, volume profile, probability, fundamentals | Each module integration test |
| WalkForwardEngine | Parameter optimization | Walk-forward test |
| ReportEngine | PnL, drawdown, Sharpe | Report generation test |
| MarketDataEngine | Live quote flow, cache-then-publish | Quote flow contract test |
| Datalake core | Parquet, DuckDB, ingestion, quality, corporate actions | Data roundtrip test |
| SourceSelectionPolicy | Federated history resolution | Source selection test |
| NSE exchange plugin | Calendar, trading hours | Trading day checks |
| MCP server | Datalake query tools | MCP integration test |
| Analytics-first CLI | Full command tree | All commands functional |
| TUI + FastAPI | Terminal and REST surfaces | Interface smoke tests |

**Exit criteria:** Full replay → backtest → paper → live workflow demonstrable.

### Phase 6: Testing, Observability, and Deployment (Week 9–10)

| Task | Deliverable | Acceptance |
|------|-------------|------------|
| Architecture tests | Import linter, flow contracts | CI-blocking pass |
| Parity gate | Four-mode FSM test | Never skipped in LIVE |
| Bypass path scan | Architecture test | Zero alternate order paths |
| Replay determinism | Log replay → identical cache | Nightly pass |
| E2E tests | Full session flows | Startup → order → fill → reconcile |
| Observability | Metrics, tracing, health endpoints | Prometheus scrape works |
| Audit sink | Append-only order audit | All transitions logged |
| Dockerfile | Multi-stage, non-root | Image builds and runs |
| CI pipeline | All stages configured | Green build on main |
| Documentation | API docs, CLI help | Complete and accurate |

**Exit criteria:** CI green; Docker image runs; 147/147 capabilities COVERED; production checklist complete.

### Build Order Dependency Graph

```
Phase 1: Foundation → Phase 2: Brokers → Phase 3: Execution
    ↓                                           ↓
Phase 1: Foundation → Phase 3: Execution → Phase 4: Composition
                                                    ↓
                                            Phase 5: Strategy/Analytics
                                                    ↓
                                            Phase 6: Testing/Deploy
```

---

## 16. Framework Contract

The framework's promise to users:

```python
class FrameworkContract:
    """
    1. Research-to-Live Parity: Same strategy code runs in Replay/Backtest/Paper/Live
    2. Single Spine: All orders through ExecutionEngine; no bypass
    3. Message Ordering: Messages are processed in timestamp order
    4. Idempotency: Duplicate messages are handled safely
    5. Observability: Every message is traced and logged
    6. Extensibility: Any component can be replaced via config
    7. Safety: RiskGate and IdempotencyGuard mandatory on every order path
    8. Deterministic Replay: Message log replay rebuilds identical state
    9. Broker Agnosticism: New venue via plugin only; application unchanged
    10. Performance: Sub-millisecond latency for local risk + routing
    """
```

### Verification Checklist

- [ ] Strategy code runs unchanged in REPLAY, BACKTEST, PAPER, LIVE
- [ ] No order path bypasses ExecutionEngine
- [ ] RiskGate blocks venue I/O on denial
- [ ] Four-mode parity gate passes
- [ ] ReplayEngine reproduces identical state from MessageLog
- [ ] 147/147 capabilities COVERED in ledger
- [ ] IdempotencyGuard prevents duplicate submissions
- [ ] Reconciliation heals HIGH drift
- [ ] Environment frozen at boot
- [ ] All brokers pass AdapterTestHarness
- [ ] Replay determinism test passes
- [ ] Architecture import contracts enforced
- [ ] Audit log captures all order transitions
- [ ] Health probes respond correctly
- [ ] LIVE requires explicit confirmation

---

## 17. Capability Coverage

> Full specification: [15-capability-coverage.md](15-capability-coverage.md)

All 147 capabilities are COVERED across the numbered spec documents:

| Category | Rows | COVERED |
|----------|------|---------|
| Core Engine | 15 | 15 |
| Execution Modes | 10 | 10 |
| OMS and Trading | 15 | 15 |
| Research Pipeline | 9 | 9 |
| Strategy and Analytics | 25 | 25 |
| Broker Adapters | 18 | 18 |
| Data Infrastructure | 16 | 16 |
| Interfaces | 6 | 6 |
| Observability | 8 | 8 |
| Quality and Deployment | 12 | 12 |
| Domain Model | 9 | 9 |
| Implementation | 4 | 4 |
| **Total** | **147** | **147** |

---

## Appendix: Cross-Reference to Detailed Specs

| Topic | Primary Spec | Supporting Specs |
|-------|-------------|------------------|
| Scope and vision | 00 | 14 |
| Architecture HLD | 01 | 03, 08 |
| Domain model | 02 | 07 |
| Message bus | 03 | 01, 08 |
| Execution/OMS | 04 | 09, 12 |
| Strategy/analytics | 05 | 07, 08, 11 |
| Broker adapters | 06 | 07, 08, 12 |
| Data infrastructure | 07 | 08 |
| Flows/DFDs | 08 | 04, 05 |
| Risk/safety | 09 | 04, 12 |
| Observability | 10 | 13 |
| Configuration | 11 | 14 |
| Testing | 12 | 01, 06 |
| Deployment | 13 | 10, 12 |
| Implementation guide | 14 | All |
| Capability coverage | 15 | All |
