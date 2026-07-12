# D1.4 — Domain Model Diagram

> **Phase 1 deliverable.** Mermaid class diagrams for each major aggregate
> in the TradeXV2 domain, derived from the actual source code.

---

## 1. Instrument Aggregate

The `Instrument` class is the central aggregate root, with subclass variants for each asset kind. It composes identity, trading spec, and extension management, and mixes in market data, streaming, and trading behaviors.

```mermaid
classDiagram
    direction TB

    class Instrument {
        <<Aggregate Root>>
        +InstrumentId _id
        +InstrumentIdentity _identity
        +TradingSpec _trading
        +InstrumentState _state
        +ExtensionManager _extensions
        +OrderServicePort _order_service_ref
        +DataProvider _provider
        +symbol str
        +exchange str
        +asset_type str
        +lot_size int
        +tick_size Decimal
        +buy(quantity, price, order_type, product_type) OrderResult
        +sell(quantity, price, order_type, product_type) OrderResult
        +market(quantity, side, product_type) OrderResult
        +limit(quantity, price, side, product_type) OrderResult
        +stop_loss(quantity, trigger_price, side) OrderResult
        +cancel(order_id) OrderResult
        +modify(order_id, quantity, price) OrderResult
        +refresh() QuoteSnapshot
        +depth() MarketDepth
        +spread() Decimal
        +mid_price() Decimal
        +history InstrumentHistory
        +option_chain(expiry) OptionChain
        +future_chain() FutureChain
        +clone() Instrument
    }

    class Equity {
        +lot_size = 1
    }

    class ETF {
        +lot_size = 1
    }

    class Spot {
        +lot_size = 1
    }

    class Currency {
        +lot_size = 1
    }

    class Index {
        +lot_size = 1
    }

    class Future {
        +expiry date
        +basis(spot) Decimal
        +cost_of_carry(rate) Decimal
        +continuous() HistoricalSeries
    }

    class Commodity {
        +expiry date
        +rollover() Future
        +basis(spot) Decimal
    }

    class Option {
        +strike Decimal
        +expiry date
        +right str
        +is_call bool
        +is_put bool
        +greeks Greeks
        +iv Decimal
        +delta() Decimal
        +black_scholes(S0, K, T, r, sigma, q) Decimal
        +payoff(spot) Decimal
        +intrinsic_value(spot) Decimal
        +extrinsic_value(spot) Decimal
        +moneyness(spot) str
        +implied_volatility(market_price, S0, K, T, r) Decimal
    }

    Instrument <|-- Equity
    Instrument <|-- ETF
    Instrument <|-- Spot
    Instrument <|-- Currency
    Instrument <|-- Index
    Instrument <|-- Future
    Instrument <|-- Option
    Future <|-- Commodity

    class InstrumentIdentity {
        <<Value Object>>
        +InstrumentId instrument_id
        +symbol str
        +exchange str
        +asset_type str
    }

    class TradingSpec {
        <<Value Object>>
        +lot_size int
        +tick_size Decimal
        +product_types tuple
        +margin_required Decimal
    }

    class ExtensionManager {
        +get(name) Any
        +register(name, extension)
        +list() list
    }

    class InstrumentId {
        <<Value Object>>
        +exchange str
        +underlying str
        +expiry date
        +strike Decimal
        +right str
        +kind str
        +equity(exchange, symbol) InstrumentId
        +future(exchange, underlying, expiry) InstrumentId
        +option(exchange, underlying, expiry, strike, right) InstrumentId
        +parse(s) InstrumentId
        +asset_type str
        +asset_kind AssetKind
        +is_equity bool
        +is_future bool
        +is_option bool
    }

    class AssetKind {
        <<Enum>>
        EQUITY
        INDEX
        FUTURES
        OPTIONS
        ETF
        CURRENCY
        COMMODITY
        SPOT
        CRYPTO
        BOND
        SYNTHETIC
    }

    class InstrumentState {
        <<Value Object>>
        +QuoteSnapshot quote
        +MarketDepth depth
        +SubscriptionState subscription
        +last_update datetime
        +error str
        +is_subscribed bool
        +with_quote(quote) InstrumentState
        +with_depth(depth) InstrumentState
        +with_error(error) InstrumentState
        +with_subscription(subscription) InstrumentState
    }

    class InstrumentRecord {
        <<Adapter Record>>
        +symbol str
        +exchange str
        +security_id str
        +instrument_type str
        +lot_size int
        +tick_size Decimal
        +name str
        +option_type str
        +strike_price Decimal
        +expiry str
        +underlying str
    }

    Instrument *-- InstrumentIdentity : identity
    Instrument *-- TradingSpec : trading
    Instrument *-- InstrumentState : state
    Instrument *-- ExtensionManager : extensions
    InstrumentId *-- AssetKind : kind
    InstrumentRecord ..> InstrumentId : maps to
```

---

## 2. Order Aggregate

The order lifecycle spans intent → plan → request → order entity → result. The `ExecutionPlan` is the sizing/routing aggregate that converts signals into order intents.

```mermaid
classDiagram
    direction TB

    class OrderIntent {
        <<Value Object>>
        +symbol str
        +exchange str
        +side Side
        +quantity int
        +price Decimal
        +order_type OrderType
        +product_type ProductType
        +trigger_price Decimal
        +validity Validity
        +correlation_id str
        +tag str
    }

    class ExecutionPlan {
        <<Aggregate>>
        +source_strategy str
        +symbol str
        +exchange str
        +signal_type str
        +confidence Decimal
        +correlation_id str
        +legs list~OrderIntent~
        +sizing OrderSizing
        +slicing SlicingPlan
        +routing RoutingHint
        +guards PlanGuards
        +from_signal(signal, ctx) ExecutionPlan
        +to_intents() list~OrderIntent~
        +sliced_quantities() list~int~
        +to_dict() dict
    }

    class OrderSizing {
        <<Value Object>>
        +total_qty int
        +per_leg_allocation list~int~
        +method SizingMethod
        +equity Decimal
        +max_position_pct Decimal
        +existing_notional Decimal
        +atr Decimal
        +atr_risk_pct Decimal
    }

    class SlicingPlan {
        <<Value Object>>
        +algo SlicingAlgo
        +slice_count int
        +interval_seconds int
        +disclosed_qty int
        +twap_duration_seconds int
        +vwap_participation_rate Decimal
    }

    class SlicingAlgo {
        <<Enum>>
        NONE
        TWAP
        VWAP
        ICEBERG
    }

    class RoutingHint {
        <<Value Object>>
        +order_type OrderType
        +product_type ProductType
        +exchange_segment str
        +broker_algo str
    }

    class PlanGuards {
        <<Value Object>>
        +min_confidence Decimal
        +kill_switch_active bool
        +validity_window_seconds int
    }

    class PlanContext {
        <<Value Object>>
        +equity Decimal
        +max_position_pct Decimal
        +existing_notional Decimal
        +atr Decimal
        +default_order_type OrderType
        +default_product_type ProductType
        +default_exchange str
        +min_confidence Decimal
        +kill_switch_active bool
        +slicing SlicingPlan
    }

    class Order {
        <<Entity>>
        +order_id str
        +symbol str
        +exchange str
        +side Side
        +order_type OrderType
        +quantity Quantity
        +filled_quantity Quantity
        +price Money
        +trigger_price Money
        +status OrderStatus
        +timestamp datetime
        +product_type ProductType
        +validity Validity
        +avg_price Money
        +reject_reason str
        +correlation_id str
        +remaining_quantity int
        +is_complete bool
        +with_status(status) Order
        +with_fill(qty, avg_price) Order
        +with_price(price) Order
    }

    class OrderRequest {
        <<Value Object>>
        +symbol str
        +exchange str
        +transaction_type Side
        +quantity int
        +price Decimal
        +trigger_price Decimal
        +order_type OrderType
        +product_type ProductType
        +validity Validity
        +correlation_id str
        +slicing_algo str
        +slice_count int
        +slice_interval int
    }

    class ModifyOrderRequest {
        <<Value Object>>
        +order_id str
        +quantity int
        +price Decimal
        +trigger_price Decimal
        +order_type OrderType
    }

    class OrderResponse {
        <<Value Object>>
        +success bool
        +order_id str
        +message str
        +status OrderStatus
        +broker_order_id str
        +error_code str
        +http_status int
        +raw_payload dict
        +latency_ms float
        +ok() OrderResponse
        +fail() OrderResponse
        +to_ack() OrderAck
    }

    class OrderAck {
        <<Value Object>>
        +success bool
        +order_id str
        +message str
        +status OrderStatus
        +broker_order_id str
    }

    class OrderResult {
        +success bool
        +order Order
        +error str
        +ok(order) OrderResult
        +fail(error) OrderResult
    }

    class OrderStatus {
        <<Enum>>
        OPEN
        PLACED
        TRIGGERED
        FILLED
        PARTIALLY_FILLED
        CANCELLED
        REJECTED
        EXPIRED
    }

    ExecutionPlan *-- OrderSizing : sizing
    ExecutionPlan *-- SlicingPlan : slicing
    ExecutionPlan *-- RoutingHint : routing
    ExecutionPlan *-- PlanGuards : guards
    ExecutionPlan o-- OrderIntent : legs
    SlicingPlan *-- SlicingAlgo : algo
    OrderResponse --> OrderAck : to_ack()
    Order ..> OrderStatus : has
```

---

## 3. Position & Portfolio Aggregate

Position tracks per-instrument state with fill-based lifecycle. Portfolio aggregates all positions for portfolio-level metrics.

```mermaid
classDiagram
    direction TB

    class Position {
        <<Entity>>
        +symbol str
        +exchange str
        +quantity Quantity
        +avg_price Money
        +ltp Money
        +unrealized_pnl Money
        +realized_pnl Money
        +product_type ProductType
        +correlation_id str
        +instrument_id str
        +multiplier Decimal
        +pnl Decimal
        +with_ltp(ltp) Position
        +with_fill(quantity, price) Position
    }

    class PositionState {
        <<Enum>>
        FLAT
        OPEN
        REDUCING
        CLOSED
        REVERSED
        +is_active bool
        +is_terminal bool
    }

    class PositionAggregate {
        <<Aggregate Root>>
        +account_id str
        +instrument_id str
        +position Position
        +quantity int
        +unrealized_pnl Decimal
        +realized_pnl Decimal
        +update_ltp(ltp)
        +apply_fill(quantity, price)
    }

    class Holding {
        <<Entity>>
        +symbol str
        +exchange str
        +quantity Quantity
        +available_quantity Quantity
        +avg_price Money
        +ltp Money
        +pnl Money
        +correlation_id str
    }

    class Portfolio {
        <<Aggregate Root>>
        -_positions dict
        +positions dict
        +position_count int
        +unrealized_pnl Decimal
        +realized_pnl Decimal
        +total_pnl Decimal
        +gross_exposure Decimal
        +add_position(position)
        +remove_position(symbol, exchange)
        +update_ltp(symbol, exchange, ltp)
        +symbol_exposure(symbol, exchange) Decimal
        +concentration(symbol, exchange) Decimal
        +pnl() Decimal
    }

    class OptionChain {
        <<Value Object>>
        +underlying str
        +expiry date
        +strikes list~OptionStrike~
    }

    class OptionStrike {
        <<Value Object>>
        +strike Decimal
        +call OptionContract
        +put OptionContract
    }

    class OptionContract {
        <<Value Object>>
        +instrument_id InstrumentId
        +ltp Decimal
        +oi int
        +volume int
    }

    class FutureChain {
        <<Value Object>>
        +underlying str
        +contracts list~FutureContract~
    }

    class FutureContract {
        <<Value Object>>
        +instrument_id InstrumentId
        +expiry date
        +ltp Decimal
        +oi int
        +volume int
    }

    PositionAggregate *-- Position : owns
    Portfolio o-- Position : positions
    OptionChain *-- OptionStrike : strikes
    OptionStrike *-- OptionContract : call, put
    OptionChain --> FutureChain : related
```

---

## 4. Execution & Trade Aggregate

The `Execution` aggregate owns fills for a single order, computing running statistics.

```mermaid
classDiagram
    direction TB

    class Execution {
        <<Aggregate Root>>
        -_order_id str
        -_instrument_id InstrumentId
        -_side Side
        -_order_quantity int
        -_trades list~Trade~
        -_lock RLock
        -_event_bus DomainEventBus
        +order_id str
        +instrument_id InstrumentId
        +side Side
        +order_quantity int
        +trades tuple~Trade~
        +filled_quantity int
        +remaining_quantity int
        +avg_price Decimal
        +notional Decimal
        +is_complete bool
        +apply_trade(trade)
    }

    class Trade {
        <<Entity>>
        +trade_id str
        +order_id str
        +symbol str
        +exchange str
        +side Side
        +quantity Quantity
        +price Money
        +trade_value Money
        +timestamp datetime
        +product_type ProductType
        +correlation_id str
        +value Decimal
    }

    class LedgerFillRecord {
        <<Value Object>>
    }

    class SubmissionOutcome {
        <<Value Object>>
    }

    class SubmissionState {
        <<Enum>>
        PENDING
        ACCEPTED
        REJECTED
        UNKNOWN
    }

    class TradeIdKey {
        <<Value Object>>
        +trade_id str
        +order_id str
        +symbol str
        +exchange str
        +from_trade(trade) TradeIdKey
        +from_payload(payload) TradeIdKey
        +to_dict() dict
        +from_dict(data) TradeIdKey
    }

    Execution o-- Trade : trades
    SubmissionOutcome --> SubmissionState : state
```

---

## 5. Value Objects — Primitives

The foundational value objects shared across all contexts.

```mermaid
classDiagram
    direction TB

    class Money {
        <<Value Object>>
        +amount Decimal
        +currency str
        +to_decimal() Decimal
        +is_zero() bool
        +is_positive() bool
        +is_negative() bool
        +abs() Money
        +scale(factor) Money
    }

    class Quantity {
        <<Value Object>>
        +magnitude Decimal
        +unit str
        +to_int() int
        +to_decimal() Decimal
        +is_zero() bool
        +abs() Quantity
        +notional(unit_price) Money
    }

    class Clock {
        <<Value Object>>
        -_now Callable
        +now() datetime
    }

    class TickSize {
        <<Value Object>>
        +value Decimal
        +snap(price) Decimal
        +is_valid_price(price) bool
    }

    class InstrumentState {
        <<Value Object>>
        +quote QuoteSnapshot
        +depth MarketDepth
        +subscription SubscriptionState
        +last_update datetime
        +error str
    }

    class SubscriptionState {
        <<Value Object>>
        +status SubscriptionStatus
        +symbol str
        +exchange str
        +started_at datetime
        +error str
    }

    class QuoteSnapshot {
        <<Value Object>>
        +symbol str
        +exchange str
        +ltp Decimal
        +bid Decimal
        +ask Decimal
        +open_ Decimal
        +high Decimal
        +low Decimal
        +close Decimal
        +volume int
    }

    class MarketDepth {
        <<Value Object>>
        +buy_levels list
        +sell_levels list
    }

    Money --|> Decimal : amount
    Quantity --|> Decimal : magnitude
```

---

## 6. Risk Management — Policy Framework

Composable, testable risk policies with a single entry point.

```mermaid
classDiagram
    direction TB

    class RiskGate {
        <<Value Object>>
        +notional OrderNotionalLimit
        +concentration ConcentrationLimit
        +gross_exposure GrossExposureLimit
        +check_order(order_notional, portfolio_notional, total_exposure, capital) RiskResult
    }

    class RiskResult {
        <<Value Object>>
        +approved bool
        +reason str
    }

    class OrderNotionalLimit {
        <<Value Object>>
        +max_notional Decimal
        +check(order_notional) RiskResult
    }

    class ConcentrationLimit {
        <<Value Object>>
        +max_pct Decimal
        +check(order_notional, portfolio_notional) RiskResult
    }

    class GrossExposureLimit {
        <<Value Object>>
        +max_pct Decimal
        +check(total_exposure, capital) RiskResult
    }

    class DailyLossCircuitBreaker {
        <<Stateful Policy>>
        +daily_loss_limit Decimal
        +cumulative_pnl Decimal
        +is_tripped bool
        +record_pnl(pnl)
        +reset()
        +check() RiskResult
    }

    class KillSwitch {
        <<Mutable Policy>>
        -_active bool
        +activate()
        +deactivate()
        +is_active bool
        +check() RiskResult
    }

    RiskGate *-- OrderNotionalLimit : notional
    RiskGate *-- ConcentrationLimit : concentration
    RiskGate *-- GrossExposureLimit : gross_exposure
    RiskGate ..> RiskResult : produces
    OrderNotionalLimit ..> RiskResult : produces
    ConcentrationLimit ..> RiskResult : produces
    GrossExposureLimit ..> RiskResult : produces
    DailyLossCircuitBreaker ..> RiskResult : produces
    KillSwitch ..> RiskResult : produces
```

---

## 7. Account Aggregate

```mermaid
classDiagram
    direction TB

    class AccountAggregate {
        <<Aggregate Root>>
        -_account_id str
        -_balance Balance
        -_lock RLock
        +account_id str
        +balance Balance
        +available_balance Decimal
        +used_margin Decimal
        +update_balance(balance)
        +has_sufficient(required) bool
    }

    class Balance {
        <<Entity>>
        +available_balance Decimal
        +used_margin Decimal
        +total_margin Decimal
        +sod_limit Decimal
        +collateral_amount Decimal
        +utilized_amount Decimal
        +withdrawable_balance Decimal
        +has_sufficient(required) bool
    }

    AccountAggregate *-- Balance : owns
```

---

## 8. Event Types — Full Catalogue

Events grouped by their originating context.

```mermaid
classDiagram
    direction TB

    class DomainEvent {
        <<Value Object>>
        +event_type str
        +payload dict
        +timestamp datetime
        +correlation_id str
        +now(event_type, payload) DomainEvent
    }

    class TypedDomainEvent {
        +event_type EventType
        +event_id str
        +correlation_id str
    }

    DomainEvent <|-- TypedDomainEvent

    note for DomainEvent "Events by originating context:"

    class MarketEvents {
        <<Context: Market Data>>
        TICK
        DEPTH
        QUOTE
        INDEX_QUOTE
        OPTION_CHAIN
        QUOTE_UPDATED
        DEPTH_UPDATED
        BAR_CLOSED
    }

    class OrderEvents {
        <<Context: Order Management>>
        ORDER_PLACED
        ORDER_SUBMITTED
        ORDER_UPDATED
        ORDER_CANCELLED
        ORDER_REJECTED
        EXECUTION_PLAN_BUILT
        ORDER_REQUESTED
    }

    class TradeEvents {
        <<Context: Execution>>
        TRADE
        TRADE_FILLED
        TRADE_APPLIED
    }

    class PositionEvents {
        <<Context: Position & Portfolio>>
        POSITION_UPDATED
        POSITION_OPENED
        POSITION_CLOSED
        PORTFOLIO_UPDATED
    }

    class RiskEvents {
        <<Context: Risk Management>>
        RISK_LIMIT_BREACHED
        RISK_APPROVED
        RISK_REJECTED
        KILL_SWITCH_TOGGLED
        DAILY_PNL_RESET
        DRAWDOWN_LIMIT_HIT
        CIRCUIT_BREAKER_OPENED
        CIRCUIT_BREAKER_CLOSED
    }

    class BrokerEvents {
        <<Context: Broker Connectivity>>
        BROKER_CONNECTED
        BROKER_DISCONNECTED
        TOKEN_REFRESHED
        TOKEN_EXPIRED
    }

    class SystemEvents {
        <<Context: Lifecycle>>
        SERVICE_STARTED
        SERVICE_STOPPED
        SERVICE_FAILED
        SYSTEM_STARTED
        SYSTEM_SHUTDOWN
        HEALTH_CHECK_PASSED
        HEALTH_CHECK_FAILED
        METRICS_UPDATED
    }

    class StrategyEvents {
        <<Context: Strategy>>
        SCAN_STARTED
        CANDIDATE_GENERATED
        SCAN_COMPLETED
        SIGNAL_GENERATED
        SIGNAL_EXECUTED
        SCANNER_STATE_CHANGED
        STRATEGY_ACTIVATED
        STRATEGY_PAUSED
        STRATEGY_DISABLED
    }

    class SubscriptionEvents {
        <<Context: Market Data>>
        SUBSCRIPTION_STARTED
        SUBSCRIPTION_ENDED
    }
```

---

## 9. Ports — Dependency Inversion Boundaries

All protocols that contexts depend on, forming the hexagonal architecture boundaries.

```mermaid
classDiagram
    direction TB

    class DataProvider {
        <<Protocol>>
        +name str
        +get_quote(instrument_id) QuoteSnapshot
        +get_history(instrument_id, timeframe, lookback_days) list
        +get_history_series(instrument_id) HistoricalSeries
        +get_depth(instrument_id) MarketDepth
        +get_option_chain(underlying) OptionChain
        +get_future_chain(underlying) FutureChain
        +subscribe(instrument_id, callback) SubscriptionHandle
        +unsubscribe(subscription)
        +list_instruments(exchange) list
        +get_quotes_batch(ids) list
    }

    class ExecutionProvider {
        <<Protocol>>
        +name str
        +place_order(request) OrderResult
        +cancel_order(order_id) OrderResult
        +modify_order(request) OrderResult
        +get_order_book() list
        +get_positions() list
        +get_holdings() list
        +get_funds() Balance
    }

    class BrokerAdapter {
        <<Protocol>>
        +broker_id str
        +is_connected bool
        +authenticate() bool
        +close()
    }

    class OrderServicePort {
        <<Protocol>>
        +place(intent) OrderResult
        +cancel(order_id) OrderResult
        +modify(request) OrderResult
    }

    class RiskManagerPort {
        <<Protocol>>
        +get_status() dict
        +is_kill_switch_active() bool
        +check_order(order_request) RiskResult
    }

    class EventPublisher {
        <<Protocol>>
        +publish(event)
        +subscribe(event_type, handler)
    }

    class EventBusPort {
        <<Protocol>>
        +replay_mode bool
        +set_replay_mode(enabled)
        +logging_enabled bool
        +set_logging_enabled(enabled)
    }

    class EventLogPort {
        <<Protocol>>
        +errors int
        +append(event)
        +replay(event_types) Iterator
        +flush()
        +close()
    }

    class OrderStorePort {
        <<Protocol>>
        +upsert(order)
        +load_all() list
        +close()
    }

    class ExecutionLedgerPort {
        <<Protocol>>
        +record_intent(intent)
        +record_outcome(outcome)
        +outcome_for(intent_id) SubmissionOutcome
        +record_fill(fill)
        +list_fills() list
        +close()
    }

    class LifecycleManagerPort {
        <<Protocol>>
        +register(service)
        +unregister(name)
        +get(name) ManagedServicePort
        +start(name)
        +stop(name, timeout_seconds)
        +start_all()
        +stop_all()
        +health_snapshot() dict
    }

    class ManagedServicePort {
        <<Protocol>>
        +name str
        +start()
        +stop(timeout_seconds)
        +health() HealthStatus
    }

    class ClockPort {
        <<Protocol>>
        +now() datetime
        +timestamp() float
        +epoch_ms() int
        +exchange_now(exchange) datetime
    }

    class MarginProviderPort {
        <<Protocol>>
        +calculate_margin_for_order(order) Any
    }

    class MarketDataPort {
        <<Protocol>>
        +history(symbol, timeframe, lookback_days) HistoricalSeries
        +option_chain(underlying) OptionChain
        +future_chain(underlying) FutureChain
        +ltp(symbol) float
        +list_symbols(timeframe) list
    }

    class StrategyEvaluator {
        <<Protocol>>
        +evaluate_single(candidate, features) list
    }

    BrokerAdapter --|> DataProvider
    BrokerAdapter --|> ExecutionProvider
    EventBusPort --|> EventPublisher
    LifecycleManagerPort o-- ManagedServicePort : manages
```

---

## 10. Universe & Session

The composition root that wires everything together.

```mermaid
classDiagram
    direction TB

    class Universe {
        -_instruments dict
        +equity(exchange, symbol) Instrument
        +etf(exchange, symbol) Instrument
        +future(exchange, underlying, expiry) Future
        +option(exchange, underlying, expiry, strike, right) Option
        +index(exchange, name) Index
        +get(instrument_id) Instrument
    }

    class Session {
        -_universe Universe
        -_provider DataProvider
        -_execution_provider ExecutionProvider
        -_order_service OrderServicePort
        -_event_bus EventBusPort
        +universe Universe
        +provider DataProvider
        +execution_provider ExecutionProvider
        +order_service OrderServicePort
        +event_bus EventBusPort
        +buy(symbol, quantity, price) OrderResult
        +sell(symbol, quantity, price) OrderResult
        +market(symbol, quantity, side) OrderResult
        +limit(symbol, quantity, price, side) OrderResult
        +stop_loss(symbol, quantity, trigger_price, side) OrderResult
        +place(intent) OrderResult
        +cancel(order_id) OrderResult
        +modify(order_id, quantity, price) OrderResult
        +account() Balance
        +orders() list
        +instrument(instrument_id) Instrument
        +resolve(symbol) Instrument
        +option_chain(underlying) OptionChain
        +close()
    }

    class SessionDx {
        +get_ltp_data(symbol) Decimal
        +get_quote_data(symbol) QuoteSnapshot
        +atm_strikes(underlying) list
        +otm_strikes(underlying) list
        +itm_strikes(underlying) list
    }

    Session *-- Universe : owns
    Session ..> DataProvider : uses
    Session ..> ExecutionProvider : uses
    Session ..> OrderServicePort : uses
    Session ..> EventBusPort : uses
    Session *-- SessionDx : dx
```

---

## Aggregate Relationship Summary

```mermaid
graph LR
    subgraph Identity
        IID["InstrumentId"]
        AK["AssetKind"]
    end

    subgraph Instrument
        INST["Instrument<br/>(aggregate root)"]
        II["InstrumentIdentity"]
        TS["TradingSpec"]
        IS["InstrumentState"]
    end

    subgraph Order
        OI["OrderIntent"]
        EP["ExecutionPlan"]
        ORD["Order"]
        OR["OrderResult"]
    end

    subgraph Execution
        EX["Execution"]
        TR["Trade"]
    end

    subgraph Position
        POS["Position"]
        PA["PositionAggregate"]
        PF["Portfolio"]
    end

    subgraph Risk
        RG["RiskGate"]
        RR["RiskResult"]
    end

    subgraph Account
        ACCT["AccountAggregate"]
        BAL["Balance"]
    end

    subgraph VOs
        M["Money"]
        Q["Quantity"]
        CK["Clock"]
    end

    INST --> IID
    INST --> IS
    II --> IID
    IS --> M
    ORD --> M
    ORD --> Q
    TR --> M
    TR --> Q
    POS --> M
    POS --> Q
    EP --> OI
    EP --> RR
    RG --> RR
    EX --> TR
    PA --> POS
    PF --> POS
    ACCT --> BAL
    RG -.->|pre-trade| ORD
    EX -.->|fill| POS
    INST -.->|buy/sell| ORD
```

---

*Generated from source analysis on 2026-07-12.*
