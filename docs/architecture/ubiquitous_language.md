# Ubiquitous Language Glossary — TradeXV2

**Version:** 1.0 · **Phase:** 1 (Transformation Roadmap) · **Date:** 2026-07-12

> Every term below is derived from actual source code. "Current Code" links
> point to the canonical definition; "Used In" lists the bounded contexts
> that reference the term.

---

## Instruments

### Instrument
**Definition:** The base domain object representing a tradeable financial product. Wraps an `InstrumentId` and binds session ports for data, execution, and extensions. All market interactions — quoting, ordering, subscribing — are routed through an Instrument.
**Current Code:** `src/domain/instruments/instrument.py` — `class Instrument`
**Used In:** Market Data, OMS, Strategy Engine, Analytics, Backtest, Replay, Portfolio
**Synonyms:** Security, Asset, Symbol (colloquial)

### Equity
**Definition:** An `Instrument` subclass representing an equity share traded on an exchange (e.g., RELIANCE on NSE). Default `lot_size=1`, `tick_size=0.05`.
**Current Code:** `src/domain/instruments/instrument.py` — `class Equity(Instrument)` (line 386)
**Used In:** Market Data, OMS, Scanner, Portfolio
**Synonyms:** Stock, Share

### Future
**Definition:** An `Instrument` subclass representing a futures contract. Has `expiry`, `basis()`, `cost_of_carry()`, and `continuous` chain resolution. MCX futures default to `AssetKind.COMMODITY`.
**Current Code:** `src/domain/instruments/instrument.py` — `class Future(Instrument)` (line 446)
**Used In:** Market Data, OMS, Options, Analytics, Backtest
**Synonyms:** Futures contract

### Option
**Definition:** An `Instrument` subclass representing an options contract (CE/PE). Computes `greeks()`, `iv`, `delta`, `black_scholes()`, `payoff()`, `intrinsic_value()`, `extrinsic_value()`, `moneyness()`, and `implied_volatility()`.
**Current Code:** `src/domain/instruments/instrument.py` — `class Option(Instrument)` (line 642)
**Used In:** Market Data, OMS, Options, Analytics, Backtest
**Synonyms:** Options contract, Derivative

### OptionChain
**Definition:** A canonical collection of `OptionStrike` rows (each containing call and put `OptionLeg`s) for a given underlying, exchange, and expiry. Returned by broker adapters and data providers.
**Current Code:** `src/domain/entities/options.py` — `class OptionChain` (line 101)
**Used In:** Market Data, Options, Strategy Engine, API
**Synonyms:** Chain, Option ladder

### Commodity
**Definition:** An `Instrument` subclass for commodity futures (typically on MCX). Adds `rollover()` logic and `cost_of_carry()` computation specific to physical commodity contracts.
**Current Code:** `src/domain/instruments/instrument.py` — `class Commodity(Instrument)` (line 522)
**Used In:** Market Data, OMS, Analytics, Backtest
**Synonyms:** Commodity future

### Currency
**Definition:** An `Instrument` subclass representing a currency pair or currency future underlying. Created via `InstrumentId.currency(exchange, symbol)`.
**Current Code:** `src/domain/instruments/instrument.py` — `class Currency(Instrument)` (line 422)
**Used In:** Market Data, OMS
**Synonyms:** FX, Forex

### Spot
**Definition:** An `Instrument` subclass for spot-market instruments (FX/commodity spot when supported by a broker). Created via `InstrumentId.spot(exchange, symbol)`.
**Current Code:** `src/domain/instruments/instrument.py` — `class Spot(Instrument)` (line 410)
**Used In:** Market Data, OMS
**Synonyms:** Cash market instrument

### ETF
**Definition:** An `Instrument` subclass for Exchange-Traded Funds. Cash-like trading behavior, `lot_size=1`.
**Current Code:** `src/domain/instruments/instrument.py` — `class ETF(Instrument)` (line 398)
**Used In:** Market Data, OMS, Portfolio
**Synonyms:** Exchange-Traded Fund

### Index
**Definition:** An `Instrument` subclass for market indices (NIFTY, BANKNIFTY, SENSEX). Non-tradeable directly; used as underlyings for derivatives.
**Current Code:** `src/domain/instruments/instrument.py` — `class Index(Instrument)` (line 434)
**Used In:** Market Data, Options, Analytics
**Synonyms:** Market index, Underlying index

### InstrumentId
**Definition:** Canonical instrument identity. Format: `exchange:underlying:expiry:strike:right` (e.g., `NSE:RELIANCE`, `NFO:NIFTY:20260730:25000:CE`). Single source of truth for instrument identification across all modules.
**Current Code:** `src/domain/instruments/instrument_id.py` — `class InstrumentId` (line 50)
**Used In:** All bounded contexts — Market Data, OMS, Strategy, Analytics, Portfolio, Datalake, API
**Synonyms:** Instrument identifier, Canonical key

---

## Orders and Execution

### Order
**Definition:** Canonical order entity returned by every broker adapter. Frozen dataclass with `Money`/`Quantity` value objects for price and quantity fields. Represents an order at any lifecycle stage (OPEN, FILLED, CANCELLED, REJECTED, UNKNOWN).
**Current Code:** `src/domain/entities/order.py` — `class Order` (line 59)
**Used In:** OMS, Broker Adapters, API, Portfolio, Reconciliation
**Synonyms:** Order record, Order entity

### OrderIntent
**Definition:** Domain command representing a user/strategy desire to trade, before risk checks or OMS admission. Pure — no broker IDs, no transport fields. Alias `TradingIntent` preferred in new code.
**Current Code:** `src/domain/orders/intent.py` — `class OrderIntent` (line 25)
**Used In:** Strategy Engine, OMS, Scanner
**Synonyms:** TradingIntent (preferred alias), Trade desire

### PersistedOrderIntent
**Definition:** Durable order command persisted to the execution ledger before broker I/O. Distinct from pre-risk `OrderIntent`. Contains `intent_id`, `order_id`, `correlation_id`, and full order parameters.
**Current Code:** `src/domain/execution_contracts.py` — `class OrderIntent` (line 28), aliased as `PersistedOrderIntent` (line 130)
**Used In:** OMS Ledger Outbox, Recovery, Reconciliation
**Synonyms:** Ledger intent, Durable order command

### OrderRequest
**Definition:** Input model for placing an order — domain fields only. Immutable dataclass with `symbol`, `exchange`, `transaction_type`, `quantity`, `price`, `order_type`, `product_type`. Broker-transport fields have been moved to `BrokerOrderPayload`.
**Current Code:** `src/domain/orders/requests.py` — `class OrderRequest` (line 28)
**Used In:** OMS, Execution Provider, Broker Adapters
**Synonyms:** Place order request, Order input

### OmsOrderCommand
**Definition:** Internal command object used by the OMS `OrderManager` to route orders through the lifecycle. Carries the domain order plus execution context (submit function, risk check result).
**Current Code:** `src/application/oms/order_manager.py` — `class OmsOrderCommand` (line 65)
**Used In:** OMS OrderManager, Execution
**Synonyms:** Internal order command

### Fill
**Definition:** A confirmed execution of an order (or part of it). In the domain model, fills are tracked as `Trade` entities and `LedgerFillRecord` durable records. Represents the economic fact that shares changed hands at a specific price.
**Current Code:** `src/domain/execution_contracts.py` — `class LedgerFillRecord` (line 105)
**Used In:** OMS, Portfolio, Reconciliation, Datalake
**Synonyms:** Execution, Trade fill

### Trade
**Definition:** Canonical trade entity returned by every broker adapter. Records a single execution event with `trade_id`, `order_id`, `symbol`, `side`, `quantity`, `price`, `trade_value`. Frozen dataclass with `Money`/`Quantity` value objects.
**Current Code:** `src/domain/entities/trade.py` — `class Trade` (line 30)
**Used In:** OMS, Portfolio, Broker Adapters, Datalake, API
**Synonyms:** Execution, Trade record

---

## Positions and Portfolio

### Position
**Definition:** Canonical position entity representing the current holding for a symbol/exchange pair. Tracks `quantity`, `avg_price`, `ltp`, `unrealized_pnl`, `realized_pnl`, and `multiplier`. Supports atomic `with_fill()` and `with_ltp()` transitions.
**Current Code:** `src/domain/entities/position.py` — `class Position` (line 30)
**Used In:** OMS, Portfolio, Broker Adapters, API, Risk
**Synonyms:** Open position, Market position

### Holding
**Definition:** Canonical holding entity representing a broker-reported long-term equity holding (CNC/MIS). Distinct from `Position` which represents intraday/derivative positions. Tracks `quantity`, `available_quantity`, `avg_price`, `ltp`, `pnl`.
**Current Code:** `src/domain/entities/position.py` — `class Holding` (line 151)
**Used In:** Portfolio, Broker Adapters, API
**Synonyms:** Demat holding, Delivery holding

### PnL
**Definition:** Profit and Loss — computed as `unrealized_pnl + realized_pnl` on a Position or Portfolio. Unrealized PnL is live-updated via `with_ltp()`; realized PnL is computed atomically on `with_fill()`.
**Current Code:** `src/domain/entities/position.py` — `Position.pnl` property (line 70); `src/domain/portfolio/portfolio.py` — `Portfolio.total_pnl` (line 73)
**Used In:** Portfolio, Risk, Strategy Engine, API, Dashboard
**Synonyms:** Profit and Loss, Mark-to-market P&L

### Portfolio
**Definition:** Aggregate root owning a collection of Positions keyed by `symbol:exchange`. Computes portfolio-level `total_pnl`, `gross_exposure`, `concentration()`, and `symbol_exposure()`. Positions are replaced atomically on update.
**Current Code:** `src/domain/portfolio/portfolio.py` — `class Portfolio` (line 24)
**Used In:** Risk, Strategy Engine, API, Dashboard
**Synonyms:** Account portfolio, Trading portfolio

---

## Signals and Strategy

### Candidate
**Definition:** An instrument identified by a scanner as a potential trading opportunity, carrying a score and metadata. Passed to the strategy pipeline for further evaluation.
**Current Code:** `src/analytics/scanner/models.py` — `class Candidate` (line 59)
**Used In:** Scanner, Strategy Engine, Backtest
**Synonyms:** Scan hit, Scanner result

### Signal
**Definition:** An actionable trading recommendation produced by a strategy evaluation. Contains `SignalType` (BUY/SELL/HOLD), confidence, instrument reference, and optional `to_intent()` for direct order placement.
**Current Code:** `src/analytics/strategy/models.py` — `class Signal` (line 81)
**Used In:** Strategy Engine, LiveStrategyEngine, Backtest
**Synonyms:** Trading signal, Actionable signal

### SignalType
**Definition:** Enum classifying the direction of a trading signal: BUY, SELL, HOLD (and potentially variants). Used by `StrategyResult` to communicate actionable recommendations.
**Current Code:** `src/analytics/strategy/models.py` — `class SignalType` (line 32)
**Used In:** Strategy Engine, Backtest, Scanner
**Synonyms:** Signal direction, Action type

### FeatureSet
**Definition:** A collection of computed technical features for a single instrument, used as input to strategy evaluation. Contains indicator values (RSI, MACD, VWAP, etc.) organized for strategy consumption.
**Current Code:** `src/analytics/core/models.py` — `class FeatureSet` (line 55); `src/domain/models/features.py` — `class FeatureSet` (line 9)
**Used In:** Analytics Pipeline, Strategy Engine, Backtest
**Synonyms:** Indicator snapshot, Feature vector

### FeaturePipeline
**Definition:** The analytics pipeline that transforms raw `HistoricalSeries` data into `FeatureSet` objects. Computes technical indicators (RSI, ATR, VWAP, MACD, patterns). Used identically across scanner, backtest, replay, paper, and live modes.
**Current Code:** `src/analytics/pipeline/pipeline.py` — `class FeaturePipeline` (line 29)
**Used In:** Analytics, Scanner, Strategy Engine, Backtest, Replay
**Synonyms:** Indicator pipeline, Analytics pipeline

---

## Strategy

### Strategy
**Definition:** An abstract or concrete trading strategy that evaluates candidates against features and produces `StrategyResult` containing actionable signals.
**Current Code:** `src/analytics/strategy/pipeline.py` — `class StrategyPipeline` (line 241)
**Used In:** Strategy Engine, Backtest, Live Trading
**Synonyms:** Trading strategy, Quant strategy

### StrategyPipeline
**Definition:** The evaluation pipeline that orchestrates multiple strategy evaluators against candidates and features. Returns `StrategyResult` objects containing actionable signals. The same pipeline is used across all modes.
**Current Code:** `src/analytics/strategy/pipeline.py` — `class StrategyPipeline` (line 241)
**Used In:** Strategy Engine, Backtest, LiveTradingEngine
**Synonyms:** Strategy evaluator, Strategy orchestrator

### StrategyResult
**Definition:** The output of a strategy evaluation: contains a list of actionable signals, rejected signals, and evaluation metadata. The `actionable` attribute provides signals that meet the strategy's confidence threshold.
**Current Code:** `src/analytics/strategy/models.py` — `class StrategyResult` (line 159)
**Used In:** Strategy Engine, Backtest
**Synonyms:** Evaluation result

---

## Sessions and Runtime

### BrokerSession
**Definition:** The public, broker-agnostic entry point for market access. Wraps a composition-root `Session` and returns rich domain objects (`Equity`, `OptionChain`, etc.). No gateway, adapter, or client type is exposed — adding a broker requires only a new plugin package.
**Current Code:** `src/brokers/session/broker_session.py` — `class BrokerSession` (line 44)
**Used In:** CLI, API, SDK, Examples
**Synonyms:** SDK session, Trading session (public)

### DomainSession
**Definition:** The composition-root session object (`tradex.connect` / `universe.Session`) that owns broker connectivity, instrument universe, and event bus. Internal to the runtime; `BrokerSession` wraps this.
**Current Code:** `src/brokers/runtime/bundle.py` (imports `from domain.universe import Session as DomainSession`)
**Used In:** Runtime, Broker Adapters, RuntimeBundle
**Synonyms:** Composition session, Internal session

### RuntimeBundle
**Definition:** Session-scoped coordinator grouping all runtime managers (subscriptions, history, quotes, execution, capabilities, symbols, events). Created by the composition root; provides observable startup checkpoints for the SRE layer.
**Current Code:** `src/brokers/runtime/bundle.py` — `class RuntimeBundle` (line 26)
**Used In:** Runtime, CLI, API Bootstrap
**Synonyms:** Session bundle, Runtime context

---

## Market Data

### Quote
**Definition:** Canonical quote snapshot — the older market data model with `ltp`, `open`, `high`, `low`, `close`, `volume`, `bid`, `ask`, `timestamp`. Supports `spread()`, `mid()`, `change_pct()`, `is_stale()`, and `to_snapshot()` bridge.
**Current Code:** `src/domain/entities/market.py` — `class Quote` (line 176)
**Used In:** Market Data, Broker Adapters, Strategy Engine, API
**Synonyms:** LTP quote, Market quote

### QuoteSnapshot
**Definition:** Point-in-time quote snapshot with provenance — the newer model that includes `DataProvenance` for multi-broker auditing. Distinct from `Quote` which lacks provenance. New code prefers `QuoteSnapshot`.
**Current Code:** `src/domain/entities/market.py` — `class QuoteSnapshot` (line 299)
**Used In:** Market Data, Broker Adapters, API, Data Lake
**Synonyms:** Snap quote, Provenance-aware quote

### Depth
**Definition:** Market depth (order book) — a bid/ask ladder of `DepthLevel` entries. `MarketDepth` supports `best_bid`, `best_ask`, `spread()`, `mid_price()`, `micro_price()`, `imbalance()`, `weighted_bid()`, `weighted_ask()`, and `cumulative_depth()`.
**Current Code:** `src/domain/entities/market.py` — `class MarketDepth` (line 37)
**Used In:** Market Data, Depth Analysis, Strategy Engine, API
**Synonyms:** Order book, Market depth

### DepthLevel
**Definition:** A single price level in market depth. Contains `price`, `quantity`, and `orders` count at that level.
**Current Code:** `src/domain/entities/market.py` — `class DepthLevel` (line 28)
**Used In:** Market Depth
**Synonyms:** Price level, Order book level

### MarketDepth
**Definition:** Canonical market depth — bid/ask ladder with derived computations (spread, mid, micro price, imbalance, cumulative depth). `frozen=False` because `bids`/`asks` are mutable lists built incrementally by broker adapters.
**Current Code:** `src/domain/entities/market.py` — `class MarketDepth` (line 37)
**Used In:** Market Data, Depth Analysis, Strategy Engine, API
**Synonyms:** Order book, Depth ladder

---

## Historical Data

### HistoricalSeries
**Definition:** Domain collection of `HistoricalBar`s with coverage metadata, gap detection, and merge manifest. Supports `to_dataframe()` (lazy pandas export), `resample()`, `statistics()`, `merge()`, and indicator computation. Single source of truth for historical OHLCV data.
**Current Code:** `src/domain/candles/historical.py` — `class HistoricalSeries` (line 323)
**Used In:** Analytics, Backtest, Replay, Datalake, Strategy Engine
**Synonyms:** Bar series, OHLCV series

### Bar / HistoricalBar
**Definition:** Domain SSOT for one OHLCV bar. Contains `Decimal` OHLC, `Volume`, UTC `event_time`, `DataProvenance`, and `is_partial` flag for live candles still forming. Supports `from_replay()` and `from_live_bucket()` factory methods.
**Current Code:** `src/domain/candles/historical.py` — `class HistoricalBar` (line 131)
**Used In:** Analytics, Backtest, Replay, Datalake, Streaming
**Synonyms:** Candle, OHLCV bar, Historical bar

### Candle
**Definition:** Wire-only Pydantic model used in the API layer for candle requests/responses. Contains `t/o/h/l/c/v/oi` fields. **Not** a domain type — the domain equivalent is `HistoricalBar`.
**Current Code:** `src/interface/api/schemas.py` — `class Candle(BaseModel)` (line 134)
**Used In:** API
**Synonyms:** API candle (wire-only, not domain)

### OHLCV
**Definition:** Open-High-Low-Close-Volume — the standard candlestick data format. In the domain layer, represented as fields on `HistoricalBar` with `Decimal` precision. Used informally to refer to the bar data structure.
**Current Code:** `src/domain/candles/historical.py` — fields on `HistoricalBar` (line 131)
**Used In:** Analytics, Backtest, Replay, Datalake
**Synonyms:** Candlestick data, Bar data

---

## Subscriptions and Streaming

### Subscription
**Definition:** First-class domain object for a live market-data stream. Wraps the provider's subscription handle, counts ticks/depths, and publishes `TICK` / `DEPTH_UPDATED` domain events through the injected event bus.
**Current Code:** `src/domain/instruments/subscription.py` — `class Subscription` (line 23)
**Used In:** Market Data, Streaming, Strategy Engine
**Synonyms:** Live subscription, Data subscription

### SubscriptionHandle
**Definition:** Protocol for an active market-data subscription returned by `DataProvider.subscribe()`. Provides `is_active` property and `unsubscribe()` method. Used to manage subscription lifecycle.
**Current Code:** `src/domain/ports/protocols.py` — `class SubscriptionHandle(Protocol)` (line 44)
**Used In:** Market Data, Streaming
**Synonyms:** Stream handle, Subscription token

### Stream
**Definition:** A live WebSocket data feed delivering market ticks, depth updates, or order updates. Managed by `SubscriptionManager` in the `RuntimeBundle`. Colloquially refers to the entire streaming infrastructure.
**Current Code:** `src/application/streaming/orchestrator.py` — `class StreamOrchestrator`
**Used In:** Market Data, Streaming, Broker Adapters
**Synonyms:** WebSocket feed, Live feed

---

## Capabilities and Extensions

### Capability
**Definition:** Enum value representing a discrete broker capability (e.g., `MARKET_DATA`, `ORDER_COMMAND`, `OPTIONS_CHAIN`, `DEPTH_200`). Used by routing, UI gating, and feature access decisions to avoid broker-name branching.
**Current Code:** `src/domain/capabilities/enums.py` — `class Capability(str, Enum)` (line 12)
**Used In:** Broker Integration, OMS, API, Strategy Engine
**Synonyms:** Feature flag, Broker feature

### CapabilityDescriptor
**Definition:** Versioned capability snapshot held in the `BrokerRegistry`. Wraps `BrokerCapabilities` with registered extension names and observation timestamp. Used for runtime discovery.
**Current Code:** `src/domain/capabilities/broker_capabilities.py` — `class CapabilityDescriptor` (line 229)
**Used In:** Broker Registry, Runtime
**Synonyms:** Capability snapshot

### BrokerCapabilities
**Definition:** Runtime capability matrix for a single broker connection. Boolean `supports_*` flags, parameterized limits (`rate_limit_profiles`, `historical_windows`, `stream_limits`), and market coverage (`market_surfaces`). Single source of truth for what a broker can do.
**Current Code:** `src/domain/capabilities/broker_capabilities.py` — `class BrokerCapabilities` (line 95)
**Used In:** Broker Integration, OMS, API, Routing
**Synonyms:** Capability matrix, Broker profile

### Extension
**Definition:** Base class for broker-specific capabilities as composable plugins. Each extension declares `name`, `broker`, `version`, `capabilities`, and `is_available_for()`. Registered at startup via `ExtensionRegistry`.
**Current Code:** `src/domain/extensions/base.py` — `class Extension(ABC)` (line 22)
**Used In:** Broker Integration, Runtime, OMS
**Synonyms:** Broker extension, Plugin extension

### ExtendedCapabilities
**Definition:** Broker-specific capabilities beyond the base `BrokerCapabilities` matrix. Implemented as `Extension` subclasses (e.g., `Depth200Extension`, `ForeverOrderExtension`, `SuperOrderExtension`). Discovered at runtime via `ExtensionRegistry`.
**Current Code:** `src/domain/extensions/` directory (various extension files)
**Used In:** Broker Integration, Runtime
**Synonyms:** Broker extensions, Plugin capabilities

---

## Events and Messaging

### Event / DomainEvent
**Definition:** A past-tense fact about something that happened in the system (e.g., `ORDER_PLACED`, `TRADE_APPLIED`, `QUOTE_UPDATED`). Immutable dataclass with `event_id`, `event_type`, `payload`, `timestamp`, `correlation_id`. Published through the `DomainEventBus`.
**Current Code:** `src/domain/events/types.py` — `class DomainEvent` (line 71)
**Used In:** All bounded contexts — OMS, Market Data, Strategy, Portfolio
**Synonyms:** Fact, Domain fact, Event record

### DomainEventBus
**Definition:** Abstract event bus that domain code depends on. Provides `publish()`, `subscribe()`, `unsubscribe()`. The concrete implementation lives in `infrastructure.event_bus`; the port is defined here.
**Current Code:** `src/domain/events/bus.py` — `class DomainEventBus(ABC)` (line 14)
**Used In:** OMS, Market Data, Streaming, Strategy Engine
**Synonyms:** Event bus, Pub/sub bus

### DeadLetterQueue (DLQ)
**Definition:** Destination for event handler failures that cannot be processed. Preserves failed events for inspection and retry. Failures are routed here by `_handle_handler_failure()` in the `EventBus`, never silently dropped.
**Current Code:** `src/infrastructure/event_bus/event_bus.py` — `_handle_handler_failure()` (line 515); `runtime/dead_letter.sqlite`
**Used In:** Infrastructure, Observability, SRE
**Synonyms:** DLQ, Failed event store

---

## Idempotency and Durability

### Idempotency
**Definition:** The property that executing an operation multiple times produces the same result as executing it once. Enforced in the OMS via `IdempotencyGuard` (thread-safe check/reserve/release on correlation IDs) and `IdempotencyService` (multi-backend cache with Redis/file/memory fallback).
**Current Code:** `src/application/oms/idempotency_guard.py` — `class IdempotencyGuard` (line 19); `src/infrastructure/idempotency/service.py` — `class IdempotencyService` (line 61)
**Used In:** OMS, Order Placement, Event Processing
**Synonyms:** Deduplication, Exactly-once semantics

### IdempotencyGuard
**Definition:** Thread-safe guard for order placement that prevents duplicate orders for the same correlation ID. Maintains a pending set; concurrent callers with the same ID get an "already in-flight" error.
**Current Code:** `src/application/oms/idempotency_guard.py` — `class IdempotencyGuard` (line 19)
**Used In:** OMS OrderManager
**Synonyms:** Order deduplication guard

### ProcessedTradeRepository
**Definition:** Persistence layer for tracking which trade events have been processed, enabling at-least-once delivery guarantees on the event bus. Prevents duplicate position/PnL updates from retried events.
**Current Code:** `src/infrastructure/event_bus/processed_trade_repository.py` — `class ProcessedTradeRepository` (line 49)
**Used In:** Infrastructure, Event Processing
**Synonyms:** Trade deduplication store, Event dedup repository

---

## Risk Management

### Kill Switch
**Definition:** A manually activated safety mechanism that rejects all orders when active. Stateful — toggled via `activate()` / `dechecked` via `deactivate()`. Checked by `RiskManager` before every order placement.
**Current Code:** `src/domain/risk/policy.py` — `class KillSwitch` (line 99)
**Used In:** OMS, Risk, Strategy Engine, API
**Synonyms:** Emergency stop, Trading halt

### Circuit Breaker / LossCircuitBreaker
**Definition:** Stateful risk policy that trips when cumulative intraday PnL loss exceeds a configurable threshold. `record_pnl()` accumulates PnL; once the daily loss limit is breached, `check()` returns REJECTED for all subsequent orders. Resets at the start of each trading day.
**Current Code:** `src/domain/risk/policy.py` — `class DailyLossCircuitBreaker` (line 68); `src/application/oms/_internal/loss_circuit_breaker.py` — `class LossCircuitBreaker` (line 76)
**Used In:** OMS, Risk, Strategy Engine
**Synonyms:** Daily loss breaker, Loss limiter

---

## Replay and Backtest

### Replay
**Definition:** Re-execution of historical market data through the live trading pipeline. Uses the same `FeaturePipeline`, `StrategyPipeline`, and OMS handlers as live mode with simulated I/O. Ensures strategy parity between backtest and live.
**Current Code:** `src/analytics/replay/engine.py` — `class ReplayEngine` (line 84)
**Used In:** Analytics, Strategy Validation, Parity Testing
**Synonyms:** Historical replay, Market replay

### ReplayEngine
**Definition:** The engine that drives historical data replay through the live pipeline. Feeds `HistoricalBar` data as if it were live ticks, exercising the same strategy evaluation and order placement code paths.
**Current Code:** `src/analytics/replay/engine.py` — `class ReplayEngine` (line 84)
**Used In:** Analytics, Parity Testing
**Synonyms:** Replay driver

### Backtest
**Definition:** Simulation of strategy performance against historical data. Uses `BacktestEngine` to evaluate strategies, producing `BacktestResult` with `BacktestMetrics` (return, Sharpe, Sortino, drawdown, win rate, profit factor).
**Current Code:** `src/analytics/backtest/engine.py` — `class BacktestEngine` (line 62); `src/domain/backtest/models.py` — `class BacktestResultResponse` (line 25)
**Used In:** Analytics, Strategy Validation, Research
**Synonyms:** Historical simulation, Strategy backtest

### BacktestEngine
**Definition:** The engine that orchestrates backtest runs. Loads historical data, feeds it through `FeaturePipeline` and `StrategyPipeline`, simulates fills, and computes performance metrics.
**Current Code:** `src/analytics/backtest/engine.py` — `class BacktestEngine` (line 62)
**Used In:** Analytics, Research
**Synonyms:** Backtest runner

---

## Scanning

### Scanner
**Definition:** Abstract base for market scanners. Stateless — scans instruments against criteria and returns ranked `ScannerResult` instances sorted by descending score. Subclasses implement `scan()`.
**Current Code:** `src/domain/scanners/scanner.py` — `class Scanner(ABC)` (line 30)
**Used In:** Scanner, Strategy Engine
**Synonyms:** Market scanner, Screener

### ScannerRunner
**Definition:** Orchestrator that runs one or more `Scanner` instances against a universe of instruments, collecting and ranking results. Manages scanner lifecycle and scheduling.
**Current Code:** `src/analytics/scanner/runner.py` — `class ScannerRunner` (line 67)
**Used In:** Scanner, Strategy Engine
**Synonyms:** Scan orchestrator

### MomentumScanner
**Definition:** A concrete `Scanner` implementation that identifies momentum-based trading opportunities using technical indicators (RSI, MACD, volume surge). Example of a strategy-specific scanner.
**Current Code:** Referenced in scanner implementations under `src/analytics/scanner/`
**Used In:** Scanner, Strategy Engine
**Synonyms:** Momentum screener

---

## Wire and Adapters

### Wire Adapter
**Definition:** The `brokers.<id>.wire` module that translates domain requests to broker-specific HTTP/WS payloads. Each broker plugin provides its own wire adapter. Part of the anti-corruption layer between domain and broker APIs.
**Current Code:** `brokers/dhan/wire.py` — `class DhanBrokerGateway` (referenced by `test_gateway_surface_freeze.py`)
**Used In:** Broker Integration, Wire Boundary
**Synonyms:** Broker wire, Transport adapter

### WireBoundary
**Definition:** The architectural boundary between domain/application code and broker-specific transport code. Enforced by `tests/architecture/test_wire_boundary.py` — ensures domain code never imports broker wire modules directly.
**Current Code:** `tests/architecture/test_wire_boundary.py`
**Used In:** Broker Integration, Architecture Tests
**Synonyms:** Broker boundary, Transport boundary

### BrokerAdapter
**Definition:** App-facing Protocol combining `DataProvider` and `ExecutionProvider` into a single interface. The composition root wires concrete broker implementations to this protocol. Domain code depends only on this abstraction.
**Current Code:** `src/domain/ports/broker_adapter.py` — `class BrokerAdapter(DataProvider, ExecutionProvider, Protocol)` (line 45)
**Used In:** OMS, Strategy Engine, Application
**Synonyms:** Broker interface, Unified broker API

---

## Data Lake

### DataLake
**Definition:** The persistence layer for historical market data. Provides DuckDB-backed catalog queries, Parquet storage, and data ingestion pipelines. Consumer layers (analytics, backtest) access data through `DataCatalogPort`.
**Current Code:** `src/datalake/__init__.py` — `class DataLake` (line 50)
**Used In:** Analytics, Backtest, Replay, Research
**Synonyms:** Market data store, Historical data store

### DataCatalog
**Definition:** DuckDB-backed catalog providing SQL-queryable access to historical market data. Default path: `market_data/catalog.duckdb`. Accessed through `DuckDBCatalogPort` protocol.
**Current Code:** `src/domain/ports/data_catalog.py` — `class DuckDBCatalogPort(Protocol)` (line 22)
**Used In:** Analytics, Datalake, Backtest
**Synonyms:** Market data catalog

### ParquetStore
**Definition:** Parquet-file-based storage engine within the data lake. Handles reading/writing OHLCV data as Parquet files with efficient columnar compression.
**Current Code:** `src/datalake/storage/parquet_store.py` — `class ParquetStore` (line 26)
**Used In:** Datalake, Analytics
**Synonyms:** Parquet storage, Columnar store

---

## Provider Protocols

### ExecutionProvider
**Definition:** Central execution-access protocol. All order operations (`place_order`, `cancel_order`, `modify_order`, `get_order_book`, `get_positions`, `get_holdings`, `get_funds`) go through this interface.
**Current Code:** `src/domain/ports/protocols.py` — `class ExecutionProvider(Protocol)` (line 184)
**Used In:** OMS, Strategy Engine, Application
**Synonyms:** Order execution port, Trading port

### DataProvider
**Definition:** Central data-access protocol. Provides `get_quote()`, `get_history()`, `get_history_series()`, `get_depth()`, `get_option_chain()`, `get_future_chain()`, `subscribe()`, `history_batch()`, `list_instruments()`. Replaces scattered broker data references.
**Current Code:** `src/domain/ports/protocols.py` — `class DataProvider(Protocol)` (line 67)
**Used In:** Analytics, Strategy Engine, Backtest, Replay, API
**Synonyms:** Market data port, Data access port

### MarginProvider
**Definition:** Protocol for margin calculation providers. Broker adapters implement this interface to provide margin data to the risk manager. The risk manager depends only on this port, not on broker-specific implementations.
**Current Code:** `src/domain/ports/margin_provider.py` — `class MarginProviderPort(Protocol)` (line 13)
**Used In:** Risk, OMS
**Synonyms:** Margin calculation port

---

## Lifecycle and Management

### LifecycleManager
**Definition:** Owns a set of `ManagedService` instances. Starts services in registration order, stops them in reverse order, provides `health_snapshot()` for the SRE layer. Enforces stop timeouts — services that don't stop are abandoned and marked FAILED.
**Current Code:** `src/infrastructure/lifecycle/lifecycle.py` — `class LifecycleManager` (line 64)
**Used In:** Runtime, SRE, Observability
**Synonyms:** Service manager, Process lifecycle

### ManagedService
**Definition:** Protocol for a long-running service participating in the lifecycle. Must be idempotent on `start()` and `stop()`. Provides `health()` for polling. Implementations include `EventBusAlertingService`, `TokenRefreshScheduler`, `ReconciliationService`.
**Current Code:** `src/infrastructure/lifecycle/lifecycle.py` — `class ManagedService(Protocol)` (line 33)
**Used In:** Runtime, Infrastructure
**Synonyms:** Background service, Daemon service

---

## Infrastructure Concerns

### Token Redaction
**Definition:** Security mechanism that scrubs access tokens, API keys, passwords, and secrets from all log output before it reaches log sinks. Implemented via `TokenRedactionFilter` with 9 regex patterns and structured extras redaction.
**Current Code:** `src/infrastructure/logging_config.py` — `class TokenRedactionFilter` (line 54)
**Used In:** Infrastructure, Observability, Security
**Synonyms:** Log redaction, Secret scrubbing

### Anti-Corruption Layer (ACL)
**Definition:** Mapping layer between broker-specific status strings and canonical domain enums. Ensures domain code never interprets raw broker wire strings. Each broker plugin provides its own ACL mappers.
**Current Code:** `src/brokers/common/acl.py`
**Used In:** Broker Integration, OMS
**Synonyms:** Status mapper, Wire translation layer

### Composition Root
**Definition:** Module that wires ports to adapters at application startup. Determines which concrete implementations are used for each protocol. Examples: `runtime/composition.py`, `tradex.open_session()`.
**Current Code:** `src/runtime/composition.py`; referenced throughout as the wiring entry point
**Used In:** Runtime, CLI, API Bootstrap
**Synonyms:** DI container, Wiring root, Bootstrap module

### Fail Closed
**Definition:** Design principle: when a system encounters an unknown, ambiguous, or error state, it should reject the operation rather than silently proceeding. Money paths fail closed; production config fails closed; reconciliation failures fail closed.
**Current Code:** `src/runtime/production_config.py` — `validate_production_config()` (line 30); `src/domain/risk/notional.py` — `effective_notional()` returns `None` when price unavailable
**Used In:** All money-moving code, Production config, Risk
**Synonyms:** Fail-safe, Defensive default

### Record-Then-Submit
**Definition:** Order durability pattern: persist the order intent to the execution ledger *before* attempting broker I/O. If the process crashes between ledger write and broker submission, recovery can replay the intent.
**Current Code:** `src/application/oms/ledger_outbox.py` — `persist_intent_then_submit()` (line 14)
**Used In:** OMS, Order Placement
**Synonyms:** Ledger-first submission, Durable intent pattern

### Capability-Driven Dispatch
**Definition:** Routing pattern where feature access and broker selection are driven by `BrokerCapabilities` metadata (e.g., `supports_option_chain`, `supports_depth_200`) instead of `if broker_id == "dhan"` branching. Enables O(1) broker extensibility.
**Current Code:** `src/domain/capabilities/broker_capabilities.py` — `BrokerCapabilities.supports()` (line 172); `src/domain/extensions/registry.py`
**Used In:** OMS, Routing, API, Strategy Engine
**Synonyms:** Capability routing, Metadata-driven dispatch

---

## Term Index

| Term | Bounded Context |
|------|----------------|
| Instrument | Market Data, OMS, Strategy |
| Equity | Market Data, OMS, Portfolio |
| Future | Market Data, OMS, Analytics |
| Option | Market Data, OMS, Analytics |
| OptionChain | Market Data, Options, API |
| Commodity | Market Data, OMS, Analytics |
| Currency | Market Data, OMS |
| Spot | Market Data, OMS |
| ETF | Market Data, OMS, Portfolio |
| Index | Market Data, Options, Analytics |
| InstrumentId | All contexts |
| Order | OMS, Broker Adapters, API |
| OrderIntent | Strategy Engine, OMS |
| PersistedOrderIntent | OMS, Recovery |
| OrderRequest | OMS, Execution |
| OmsOrderCommand | OMS |
| Fill | OMS, Portfolio, Reconciliation |
| Trade | OMS, Portfolio, Datalake |
| Position | OMS, Portfolio, Risk |
| Holding | Portfolio, Broker Adapters |
| PnL | Portfolio, Risk, API |
| Portfolio | Risk, Strategy, API |
| Candidate | Scanner, Strategy Engine |
| Signal | Strategy Engine, Backtest |
| SignalType | Strategy Engine, Backtest |
| FeatureSet | Analytics, Strategy Engine |
| FeaturePipeline | Analytics, All modes |
| Strategy | Strategy Engine, Backtest |
| StrategyPipeline | Strategy Engine, Backtest |
| StrategyResult | Strategy Engine, Backtest |
| BrokerSession | CLI, API, SDK |
| DomainSession | Runtime, Broker Adapters |
| RuntimeBundle | Runtime, CLI |
| Quote | Market Data, API |
| QuoteSnapshot | Market Data, API, Datalake |
| Depth / MarketDepth | Market Data, Strategy |
| DepthLevel | Market Depth |
| HistoricalSeries | Analytics, Backtest, Datalake |
| Bar / HistoricalBar | Analytics, Backtest, Streaming |
| Candle | API (wire-only) |
| OHLCV | Analytics, Backtest, Datalake |
| Subscription | Market Data, Streaming |
| SubscriptionHandle | Market Data, Streaming |
| Capability | Broker Integration, OMS |
| CapabilityDescriptor | Broker Registry |
| BrokerCapabilities | Broker Integration, OMS |
| Extension | Broker Integration, Runtime |
| Event / DomainEvent | All contexts |
| DomainEventBus | OMS, Market Data, Streaming |
| DeadLetterQueue | Infrastructure, SRE |
| Idempotency | OMS, Order Placement |
| IdempotencyGuard | OMS OrderManager |
| ProcessedTradeRepository | Infrastructure |
| Kill Switch | OMS, Risk, API |
| Circuit Breaker / LossCircuitBreaker | OMS, Risk |
| Replay | Analytics, Parity |
| ReplayEngine | Analytics |
| Backtest | Analytics, Research |
| BacktestEngine | Analytics |
| Scanner | Scanner, Strategy Engine |
| ScannerRunner | Scanner |
| MomentumScanner | Scanner |
| Wire Adapter | Broker Integration |
| WireBoundary | Broker Integration |
| BrokerAdapter | OMS, Application |
| DataLake | Analytics, Datalake |
| DataCatalog | Analytics, Datalake |
| ParquetStore | Datalake |
| ExecutionProvider | OMS, Application |
| DataProvider | Analytics, Strategy, API |
| MarginProvider | Risk, OMS |
| LifecycleManager | Runtime, SRE |
| ManagedService | Runtime, Infrastructure |
| Token Redaction | Infrastructure, Security |
| Anti-Corruption Layer | Broker Integration |
| Composition Root | Runtime, CLI, API |
| Fail Closed | All money paths |
| Record-Then-Submit | OMS, Order Placement |
| Capability-Driven Dispatch | OMS, Routing, API |
