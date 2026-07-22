# TradeXV2 V2 Architecture Redesign

> Complete rewrite of the brokers module and infrastructure, following Nautilus Trader patterns.
> This document consolidates all discussions, diagrams, HLD/LLD, DFDs, and implementation plan.

---

## 1. Architecture Overview (HLD)

### 1.1 System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          TRADEX FRAMEWORK                               │
│                        (Nautilus Trader-Level)                          │
│                                                                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │
│  │   CLI / TUI     │  │   FastAPI       │  │   MCP Server    │         │
│  │   (interface/)  │  │   (interface/)  │  │   (datalake/)   │         │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘         │
│           │                    │                    │                  │
│           ▼                    ▼                    ▼                  │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    COMPOSITION ROOT                             │   │
│  │                    (runtime/)                                   │   │
│  │                                                                 │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────┐ │   │
│  │  │  Component  │  │  Lifecycle  │  │  MessageBus │  │  Config │ │   │
│  │  │  Registry    │  │  Manager    │  │  (EventBus) │  │ Manager │ │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────┘ │   │
│  └─────────────────────────────┬───────────────────────────────────┘   │
│                                │                                       │
│                                ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     EXECUTION ENGINE                            │   │
│  │                     (application/)                              │   │
│  │                                                                 │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │   │
│  │  │  Order      │  │  Position   │  │  Risk       │             │   │
│  │  │  Manager    │  │  Manager    │  │  Manager    │             │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘             │   │
│  │                                                                 │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │   │
│  │  │  Execution  │  │  Strategy   │  │  Data       │             │   │
│  │  │  Engine     │  │  Engine     │  │  Engine     │             │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘             │   │
│  └─────────────────────────────┬───────────────────────────────────┘   │
│                                │                                       │
│                                ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      ADAPTER LAYER                              │   │
│  │                      (brokers/)                                 │   │
│  │                                                                 │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────┐ │   │
│  │  │  Dhan       │  │  Upstox     │  │  Paper      │  │  Data   │ │   │
│  │  │  Gateway    │  │  Gateway    │  │  Gateway    │  │  Lake   │ │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────┘ │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                        DOMAIN MODEL                             │   │
│  │                        (domain/)                                │   │
│  │                                                                 │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────┐ │   │
│  │  │  Entities   │  │  Value      │  │  Events     │  │  Ports  │ │   │
│  │  │  (Order,     │  │  Objects    │  │  (Message)  │  │  (Proto)│ │   │
│  │  │  Position,   │  │  (Money,    │  │             │  │         │ │   │
│  │  │  Quote, ...) │  │  Quantity,  │  │             │  │         │ │   │
│  │  │               │  │  Price, ...)│  │             │  │         │ │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────┘ │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Core Design Principles

1. **Message-Driven Architecture** — All inter-component communication via `MessageBus` with typed messages
2. **Component Lifecycle** — Every component implements `initialize() → start() → stop() → reset()`
3. **Zero-Parity Engine** — Same execution engine for backtest and live, only FillSource differs
4. **Plugin Architecture** — Adapters discovered via entry points, no central switch statements
5. **Observability First** — Every message is traced, every operation is metered
6. **Declarative Configuration** — YAML config drives all component assembly
7. **Gateway → Connection → Sub-Adapters** — Standardized broker adapter pattern
8. **Instrument Ref Isolation** — Wire identifiers never leak to gateway callers

### 1.3 Component Layers

| Layer | Components | Responsibility |
|---|---|---|
| **Interface** | CLI, TUI, API, MCP | User interaction surfaces |
| **Composition** | ComponentRegistry, LifecycleManager, MessageBus, ConfigManager | Framework assembly and lifecycle |
| **Execution** | OrderManager, PositionManager, RiskManager, PortfolioManager, ExecutionEngine, StrategyEngine | Trading logic |
| **Data** | MarketDataEngine, HistoricalDataEngine, InstrumentEngine | Data management |
| **Adapters** | DhanGateway, UpstoxGateway, PaperGateway, DataLakeGateway | External system integration |
| **Domain** | Entities, ValueObjects, Events, Ports | Business model |

---

## 2. Class Diagram (LLD)

### 2.1 Broker Adapter Framework

```mermaid
classDiagram
    class BrokerAdapter {
        <<abstract>>
        +broker_id: str
        +is_connected: bool
        +authenticate() bool
        +close() void
        +quote(symbol, exchange) Quote
        +ltp(symbol, exchange) Decimal
        +depth(symbol, exchange) MarketDepth
        +history(symbol, ...) DataFrame
        +option_chain(underlying, ...) OptionChain
        +place_order(request) OrderResponse
        +cancel_order(order_id) OrderResponse
        +modify_order(order_id, **changes) OrderResponse
        +get_order(order_id) Order
        +get_orderbook() list[Order]
        +get_trade_book() list[Trade]
        +positions() list[Position]
        +holdings() list[Holding]
        +funds() Balance
        +load_instruments() void
        +search(query) list[dict]
        +stream(symbol, ...) Any
        +unstream(symbol, ...) void
        +stream_order(on_order) Any
        +capabilities() BrokerCapabilities
        +describe() dict
    }

    class BaseWireAdapter {
        +_enum_value(value) str
        +_to_decimal(value) Decimal
        +_to_int(value) int
        +_to_datetime(value) datetime
    }

    class BaseTransport {
        +authenticate() bool
        +get(path, params) dict
        +post(path, json) dict
        +put(path, json) dict
        +delete(path) dict
        +ws_subscribe(channel, callback) void
        +is_connected: bool
        +close() void
    }

    class BrokerGateway {
        +broker_id: str
        -_connection: BrokerConnection
        +initialize(config) void
        +start() void
        +stop() void
        +reset() void
    }

    class BrokerConnection {
        -_transport: BaseTransport
        -_orders: OrdersAdapter
        -_market_data: MarketDataAdapter
        -_portfolio: PortfolioAdapter
        -_instruments: InstrumentAdapter
        -_streaming: StreamingAdapter
        +orders: OrdersAdapter
        +market_data: MarketDataAdapter
        +portfolio: PortfolioAdapter
        +instruments: InstrumentAdapter
        +streaming: StreamingAdapter
        +authenticate() bool
        +is_connected: bool
        +close() void
    }

    class OrdersAdapter {
        +place_order(request) OrderResponse
        +cancel_order(order_id) OrderResponse
        +modify_order(order_id, **changes) OrderResponse
        +get_order(order_id) Order
        +get_orderbook() list[Order]
        +get_trade_book() list[Trade]
        -_map_request(request) dict
        -_map_response(data) OrderResponse
        -_map_order(data) Order
    }

    class MarketDataAdapter {
        +get_quote(symbol, exchange) Quote
        +get_ltp(symbol, exchange) Decimal
        +get_depth(symbol, exchange) MarketDepth
        +get_history(symbol, ...) DataFrame
        +get_batch_ltp(symbols, ...) dict
        +get_option_chain(underlying, ...) OptionChain
        +get_future_chain(underlying, ...) FutureChain
        -_resolve_ref(symbol, exchange) InstrumentRef
        -_map_quote(data) Quote
    }

    class PortfolioAdapter {
        +get_positions() list[Position]
        +get_holdings() list[Holding]
        +get_balance() Balance
        -_map_position(data) Position
        -_map_holding(data) Holding
        -_map_balance(data) Balance
    }

    class InstrumentAdapter {
        +load(source) void
        +resolve(symbol, exchange) InstrumentRef
        +search(query) list[dict]
        +is_loaded() bool
        -_resolver: SymbolResolver
    }

    class StreamingAdapter {
        +subscribe_market(symbol, exchange, mode, on_tick) Any
        +unsubscribe_market(symbol, exchange, on_tick) void
        +subscribe_order(on_order) Any
        +unsubscribe_order(on_order) void
    }

    class SymbolResolver {
        -_by_symbol: dict[tuple[str, str], InstrumentRef]
        -_by_ref: dict[str, tuple[str, str]]
        +add(symbol, exchange, ref) void
        +resolve(symbol, exchange) InstrumentRef
        +reverse(ref) tuple[str, str]
        +count: int
    }

    class InstrumentRef {
        <<abstract>>
    }

    class DhanInstrumentRef {
        +exchange_segment: str
        +security_id: str
        +security_id_str() str
    }

    class UpstoxInstrumentRef {
        +instrument_key: str
        +exchange: str
    }

    class DepthStreamHandle {
        -_initial: MarketDepth
        -_on_stop: Callable
        -_stopped: bool
        +initial: MarketDepth
        +stop() void
    }

    class BrokerCapabilities {
        +broker_id: str
        +name: str
        +is_live: bool
        +market_data: MarketDataCapabilities
        +execution: ExecutionCapabilities
        +portfolio: PortfolioCapabilities
        +streaming: StreamingCapabilities
        +instruments: InstrumentCapabilities
    }

    class BrokerPlugin {
        +broker_id: str
        +env_file: str
        +default_mode: str
        +supported_modes: frozenset
        +is_live: bool
        +capabilities_loader: Callable
    }

    BrokerAdapter <|-- BaseWireAdapter
    BaseWireAdapter <|-- DhanGateway
    BaseWireAdapter <|-- UpstoxGateway
    BaseWireAdapter <|-- PaperGateway

    BrokerGateway --> BrokerConnection
    BrokerConnection --> OrdersAdapter
    BrokerConnection --> MarketDataAdapter
    BrokerConnection --> PortfolioAdapter
    BrokerConnection --> InstrumentAdapter
    BrokerConnection --> StreamingAdapter
    BrokerConnection --> BaseTransport

    MarketDataAdapter --> SymbolResolver
    InstrumentAdapter --> SymbolResolver
    SymbolResolver --> InstrumentRef
    InstrumentRef <|-- DhanInstrumentRef
    InstrumentRef <|-- UpstoxInstrumentRef

    OrdersAdapter --> BaseWireAdapter
    MarketDataAdapter --> BaseWireAdapter
    PortfolioAdapter --> BaseWireAdapter
    InstrumentAdapter --> BaseWireAdapter
    StreamingAdapter --> BaseWireAdapter

    DhanGateway --> DhanConnection
    UpstoxGateway --> UpstoxConnection
    PaperGateway --> PaperConnection

    BrokerGateway --> BrokerPlugin
    BrokerGateway --> BrokerCapabilities
```

### 2.2 Execution Engine

```mermaid
classDiagram
    class ExecutionEngine {
        +component_id: str
        -_ctx: TradingContext
        -_fill_source: FillSource
        -_order_manager: OrderManager
        -_risk_manager: RiskManager
        +initialize() void
        +start() void
        +stop() void
        +on_order_command(command) void
        +on_fill(fill) void
        +apply_mass_status(orders, positions, funds) list[DriftItem]
    }

    class FillSource {
        <<Protocol>>
        +submit_order(command) OrderId
        +cancel_order(order_id) bool
        +modify_order(order_id, command) bool
    }

    class SimulatedFillSource {
        -_market_data: HistoricalData
        -_clock: FakeClock
        +submit_order(command) OrderId
    }

    class PaperFillSource {
        -_quote_fn: Callable
        +submit_order(command) OrderId
    }

    class BrokerFillSource {
        -_gateway: BrokerAdapter
        +submit_order(command) OrderId
    }

    class TradingContext {
        -_event_bus: EventBusPort
        -_order_manager: OrderManager
        -_position_manager: PositionManager
        -_risk_manager: RiskManager
        -_reconciliation_service: ReconciliationService
        +event_bus: EventBusPort
        +order_manager: OrderManager
        +position_manager: PositionManager
        +risk_manager: RiskManager
    }

    class OrderManager {
        -_event_bus: EventBusPort
        -_risk_manager: RiskManager
        -_processed_trades: ProcessedTradeRepositoryPort
        +register_order(order_id, command) void
        +apply_fill(fill) void
        +get_order(order_id) Order
        +get_orderbook() list[Order]
    }

    class PositionManager {
        -_event_bus: EventBusPort
        -_processed_trades: ProcessedTradeRepositoryPort
        +apply_fill(fill) Position
        +get_positions() list[Position]
        +get_position(symbol) Position
    }

    class RiskManager {
        -_position_manager: PositionManager
        -_risk_config: RiskConfig
        -_capital_provider: CapitalProvider
        +check_order(command) RiskCheckResult
        +update_daily_pnl(daily_pnl) void
        +reset_daily_pnl() void
    }

    ExecutionEngine --> TradingContext
    ExecutionEngine --> FillSource
    ExecutionEngine --> OrderManager
    ExecutionEngine --> RiskManager

    FillSource <|.. SimulatedFillSource
    FillSource <|.. PaperFillSource
    FillSource <|.. BrokerFillSource

    TradingContext --> OrderManager
    TradingContext --> PositionManager
    TradingContext --> RiskManager

    OrderManager --> RiskManager
    PositionManager --> OrderManager
```

### 2.3 Message Bus

```mermaid
classDiagram
    class MessageBus {
        -_subscribers: dict[type, list[Callable]]
        -_async_subscribers: dict[type, list[Callable]]
        -_logger: Logger
        -_metrics: MessageBusMetrics
        +publish(message) void
        +publish_async(message) void
        +subscribe(msg_type, handler) Subscription
        +subscribe_async(msg_type, handler) Subscription
    }

    class Message {
        <<abstract>>
        +timestamp: pd.Timestamp
        +correlation_id: UUID
        +source: str
        +with_correlation(correlation_id) Message
    }

    class Subscription {
        -_msg_type: type
        -_handler: Callable
        -_bus: MessageBus
        +unsubscribe() void
    }

    class Component {
        <<abstract>>
        +component_id: str
        -_bus: MessageBus
        -_state: ComponentState
        +initialize() void
        +start() void
        +stop() void
        +reset() void
        +_subscribe(msg_type, handler) Subscription
        +_publish(message) void
    }

    class ComponentState {
        <<enumeration>>
        UNINITIALIZED
        INITIALIZED
        RUNNING
        STOPPED
        ERROR
    }

    class LifecycleManager {
        -_components: dict[str, Component]
        -_order: list[str]
        +register(component) void
        +initialize_all() void
        +start_all() void
        +stop_all() void
    }

    MessageBus --> Subscription
    MessageBus --> Message
    Component --> MessageBus
    Component --> ComponentState
    LifecycleManager --> Component
```

---

## 3. Flow Diagrams

### 3.1 Order Placement Flow (End-to-End)

```mermaid
sequenceDiagram
    participant Caller as Strategy/OMS
    participant Bus as MessageBus
    participant EE as ExecutionEngine
    participant RM as RiskManager
    participant OM as OrderManager
    participant FS as FillSource
    participant GW as BrokerGateway
    participant BRK as Broker API

    Caller->>Bus: publish(OrderCommand)
    Bus->>EE: on_order_command(command)
    EE->>RM: check_order(command)
    alt Risk Denied
        RM-->>EE: RiskCheckResult(approved=False)
        EE->>Bus: publish(RiskRejected)
    else Risk Approved
        RM-->>EE: RiskCheckResult(approved=True)
        EE->>Bus: publish(RiskApproved)
        EE->>FS: submit_order(command)
        alt Paper/Sim Mode
            FS->>FS: Simulate fill
            FS-->>EE: OrderId
        else Live Mode
            FS->>GW: place_order(request)
            GW->>BRK: POST /orders
            BRK-->>GW: OrderAck
            GW-->>FS: OrderId
        end
        EE->>Bus: publish(OrderSubmitted)
        EE->>OM: register_order(order_id, command)
        alt Fill Arrives
            FS->>EE: on_fill(fill)
            EE->>OM: apply_fill(fill)
            EE->>Bus: publish(OrderFilled)
            EE->>Bus: publish(PositionUpdated)
        end
    end
```

### 3.2 Market Data Flow

```mermaid
sequenceDiagram
    participant BRK as Broker API
    participant GW as BrokerGateway
    participant Conn as BrokerConnection
    participant MD as MarketDataAdapter
    participant Bus as MessageBus
    participant Strat as Strategy

    BRK->>Conn: WebSocket: QuoteUpdate
    Conn->>MD: _on_quote(payload)
    MD->>MD: _map_quote(payload)
    MD->>Bus: publish(Quote)
    Bus->>Strat: on_quote(Quote)
    Bus->>Conn: on_quote(Quote) (for risk)
```

### 3.3 Component Lifecycle Flow

```mermaid
sequenceDiagram
    participant Factory as RuntimeFactory
    participant LC as LifecycleManager
    participant Bus as MessageBus
    participant Comp as Component

    Factory->>LC: register(component)
    LC->>LC: _components[cid] = component
    LC->>LC: _order.append(cid)

    Factory->>LC: initialize_all()
    loop for each component in order
        LC->>Comp: initialize()
        Comp->>Bus: subscribe(msg_type, handler)
    end

    Factory->>LC: start_all()
    loop for each component in order
        LC->>Comp: start()
    end

    Factory->>LC: stop_all()
    loop for each component in reverse order
        LC->>Comp: stop()
    end
```

### 3.4 Backtest Engine Flow

```mermaid
sequenceDiagram
    participant BT as BacktestEngine
    participant Bus as MessageBus
    participant EE as ExecutionEngine
    participant Strat as Strategy
    participant DE as DataEngine

    BT->>Bus: subscribe(Bar, strategy.on_bar)
    BT->>Bus: subscribe(OrderFilled, strategy.on_fill)
    BT->>EE: _fill_source = SimulatedFillSource

    loop for each historical bar
        DE->>BT: fetch_history(...)
        BT->>Bus: publish(Bar)
        Bus->>Strat: on_bar(Bar)
        Strat->>Bus: publish(OrderCommand)
        Bus->>EE: on_order_command(command)
        EE->>EE: Simulate fill
        EE->>Bus: publish(OrderFilled)
        Bus->>Strat: on_fill(fill)
    end
```

---

## 4. File/Folder Organization

### 4.1 Brokers Module (Redesigned)

```
brokers/
├── __init__.py                    # BrokerAdapter protocol re-export
├── gateway.py                     # BrokerGateway facade
├── session.py                     # BrokerSession (merge session/)
│
├── common/                        # SHARED INFRA — 5 files
│   ├── __init__.py
│   ├── transport.py               # BaseTransport, TransportError hierarchy
│   ├── wire_base.py               # BaseWireAdapter base class
│   ├── streaming.py               # DepthStreamHandle
│   └── util.py                    # enum_value, to_decimal, etc.
│
├── providers/
│   ├── __init__.py
│   │
│   ├── dhan/                      # 8 files (was 102)
│   │   ├── __init__.py            # Exports + self-registration
│   │   ├── gateway.py             # DhanGateway (BrokerAdapter impl)
│   │   ├── connection.py          # DhanConnection (owns sub-adapters)
│   │   ├── transport.py           # DhanTransport (HTTP + WS)
│   │   ├── adapters/
│   │   │   ├── __init__.py
│   │   │   ├── orders.py          # DhanOrdersAdapter
│   │   │   ├── market_data.py     # DhanMarketDataAdapter
│   │   │   ├── portfolio.py       # DhanPortfolioAdapter
│   │   │   └── instruments.py     # DhanInstrumentAdapter
│   │   └── config.py              # DhanConfig, dhan_capabilities()
│   │
│   ├── upstox/                    # 8 files (was 128)
│   │   ├── __init__.py            # Exports + self-registration
│   │   ├── gateway.py             # UpstoxGateway (BrokerAdapter impl)
│   │   ├── connection.py          # UpstoxConnection (owns sub-adapters)
│   │   ├── transport.py           # UpstoxTransport (HTTP + WS)
│   │   ├── adapters/
│   │   │   ├── __init__.py
│   │   │   ├── orders.py          # UpstoxOrdersAdapter
│   │   │   ├── market_data.py     # UpstoxMarketDataAdapter
│   │   │   ├── portfolio.py       # UpstoxPortfolioAdapter
│   │   │   └── instruments.py     # UpstoxInstrumentAdapter
│   │   └── config.py              # UpstoxConfig, upstox_capabilities()
│   │
│   └── paper/                     # 6 files (was 12)
│       ├── __init__.py            # Exports + self-registration
│       ├── gateway.py             # PaperGateway (BrokerAdapter impl)
│       ├── market_data.py         # PaperMarketData
│       ├── orders.py              # PaperOrders
│       ├── portfolio.py           # PaperPortfolio
│       └── config.py              # PaperConfig, paper_capabilities()
│
└── runtime/                       # 2 files (was 8)
    ├── __init__.py                # RuntimeBundle
    └── managers.py                # All managers merged
```

### 4.2 Full Project Structure (Redesigned)

```
tradex/
├── src/
│   ├── tradex/                    # Public SDK (thin facade)
│   │   ├── __init__.py
│   │   ├── cli.py
│   │   └── session.py
│   │
│   ├── domain/                    # Pure business logic (stdlib only)
│   │   ├── __init__.py
│   │   ├── entities.py            # Order, Position, Quote, Instrument, Balance
│   │   ├── events.py              # DomainEvent, EventType (Message base)
│   │   ├── ports.py               # Protocols: BrokerAdapter, EventBus, Clock, etc.
│   │   ├── enums.py               # ExchangeId, OrderSide, OrderType, etc.
│   │   ├── value_objects.py       # Money, Quantity, InstrumentId, CorrelationId
│   │   ├── risk.py                # RiskConfig, RiskCheck, RiskResult
│   │   └── indicators.py          # Pure indicator functions
│   │
│   ├── application/               # Use-cases (no infra/runtime/broker imports)
│   │   ├── __init__.py
│   │   ├── oms/                   # OrderManager, PositionManager, RiskManager
│   │   ├── execution/             # ExecutionEngine, FillSource
│   │   ├── trading/               # TradingOrchestrator, StrategyEngine
│   │   ├── data/                  # DataEngine, HistoricalDataCoordinator
│   │   └── scheduling/            # QuotaScheduler
│   │
│   ├── infrastructure/            # Adapters (implements domain ports)
│   │   ├── __init__.py
│   │   ├── message_bus.py         # MessageBus (NEW)
│   │   ├── component.py           # Component, LifecycleManager (NEW)
│   │   ├── event_bus.py           # EventBus (existing)
│   │   ├── observability.py       # ObservabilityStack, HealthChecker (NEW)
│   │   ├── config.py              # ConfigLoader, AppConfig (NEW)
│   │   ├── io/                    # ParquetWriter, atomic writes
│   │   ├── auth/                  # Token management, TOTP
│   │   ├── resilience/            # CircuitBreaker, RateLimiter
│   │   ├── lifecycle.py           # LifecycleManager (merged)
│   │   ├── clock.py               # SystemClock, FakeClock
│   │   └── gateway/               # GatewayFactory
│   │
│   ├── runtime/                   # Composition root
│   │   ├── __init__.py
│   │   ├── factory.py             # RuntimeFactory (consolidated)
│   │   └── runtime.py             # Runtime dataclass
│   │
│   ├── brokers/                   # Broker adapters (redesigned)
│   │   ├── __init__.py
│   │   ├── gateway.py
│   │   ├── session.py
│   │   ├── common/                # 5 files
│   │   └── providers/             # Dhan, Upstox, Paper (8+8+6 files)
│   │
│   ├── datalake/                  # Data storage + analytics
│   │   ├── __init__.py
│   │   ├── gateway.py             # DataLakeGateway
│   │   ├── storage/               # Catalog, parquet_store
│   │   ├── core/                  # IO, schema, symbols
│   │   ├── ingestion/             # Sync, broker_selection
│   │   └── analytics/             # Features, S/R, VWAP
│   │
│   ├── interface/                 # Presentation layers
│   │   ├── __init__.py
│   │   ├── api/                   # FastAPI
│   │   ├── cli/                   # CLI commands
│   │   └── mcp/                   # MCP server
│   │
│   ├── config/                    # Configuration
│   │   └── schema.py              # AppConfig, ConfigLoader
│   │
│   └── analytics/                 # Analytics (existing)
│       ├── __init__.py
│       ├── pipeline/              # FeaturePipeline
│       ├── scanner/               # Scanners
│       ├── backtest/              # BacktestEngine
│       ├── replay/                # ReplayEngine
│       ├── strategy/              # StrategyPipeline
│       └── indicators/            # Indicators
│
├── tests/
│   ├── unit/                     # Domain + pure logic tests
│   ├── component/                # Single-service tests
│   ├── integration/              # Broker API tests (gated)
│   ├── e2e/                      # Full flow tests
│   ├── architecture/             # Import-linter + dependency tests
│   ├── property/                 # Hypothesis property-based tests
│   ├── mutation/                 # Mutmut config + tests
│   └── conftest.py
│
├── docs/
│   ├── constitution/             # Product + architecture canon
│   ├── adr/                      # Architecture decision records
│   ├── flows.md                  # Flow contracts
│   └── diagrams/                 # Architecture diagrams
│
├── config/
│   ├── paper.yaml                # Paper trading config
│   ├── backtest.yaml             # Backtest config
│   └── live.yaml                 # Live trading config
│
├── pyproject.toml
├── Dockerfile
├── .github/workflows/
└── Makefile
```

---

## 5. Data Flow Diagrams (DFDs)

### 5.1 DFD Level 0 — Context

```mermaid
graph LR
    subgraph "External Entities"
        OP[Operator<br/>CLI/TUI/API]
        BR[Dhan/Upstox<br/>Broker APIs]
        DS[Data Sources<br/>NSE/Parquet/DuckDB]
    end

    subgraph "TradeXV2 Framework"
        FW[Framework<br/>Runtime + Kernel]
    end

    OP -- "Commands<br/>Config<br/>Queries" --> FW
    FW -- "Results<br/>Reports<br/>Logs" --> OP
    FW -- "Orders<br/>Cancellations<br/>Modifications" --> BR
    BR -- "Market Data<br/>Order Updates<br/>Fills" --> FW
    FW -- "Historical Data<br/>Requests" --> DS
    DS -- "OHLCV<br/>Instruments<br/>Corporate Actions" --> FW
```

### 5.2 DFD Level 1 — Major Components

```mermaid
graph TD
    subgraph "External"
        OP[Operator]
        BROKERS[Dhan/Upstox APIs]
        DATA[Data Sources]
    end

    subgraph "TradeXV2 Framework"
        CLI[CLI / TUI / API<br/>interface/]
        RT[runtime/<br/>Composition Root]
        OMS[application/oms/<br/>Order/Position/Risk]
        EXEC[application/execution/<br/>Execution Engine]
        ANALYTICS[analytics/<br/>Scanner/Strategy/Backtest]
        DATALAKE[datalake/<br/>Storage/Ingestion/Analytics]
        DOM[domain/<br/>Entities/Ports/Events]
    end

    OP -- "Commands<br/>Queries" --> CLI
    CLI -- "Session Config<br/>Strategy Params" --> RT
    RT -- "Wiring<br/>Component Refs" --> OMS
    RT -- "Wiring<br/>Component Refs" --> EXEC
    RT -- "Wiring<br/>Component Refs" --> ANALYTICS
    RT -- "Wiring<br/>Component Refs" --> DATALAKE

    OMS -- "Order Commands<br/>Fill Events" --> EXEC
    EXEC -- "Order Results<br/>Fill Reports" --> OMS
    EXEC -- "Order Submit/Cancel<br/>to Broker" --> BROKERS
    BROKERS -- "Market Data<br/>Fills/Updates" --> EXEC
    BROKERS -- "Market Data<br/>Quotes/Bars" --> ANALYTICS

    ANALYTICS -- "Scan Results<br/>Signals<br/>Backtest Results" --> CLI
    ANALYTICS -- "Historical Data<br/>Requests" --> DATALAKE
    DATALAKE -- "OHLCV<br/>Instruments<br/>Analytics" --> ANALYTICS
    DATALAKE -- "Sync Data<br/>Parquet Files" --> DATA
    DATA -- "Historical Bars<br/>Metadata" --> DATALAKE

    OMS -- "Domain Events<br/>Order/Position/Risk" --> DOM
    DOM -- "Event Types<br/>Port Protocols" --> OMS
    DOM -- "Event Types<br/>Port Protocols" --> EXEC
    DOM -- "Event Types<br/>Port Protocols" --> ANALYTICS
    DOM -- "Event Types<br/>Port Protocols" --> DATALAKE

    CLI -- "Display Data<br/>Reports" --> OP
```

### 5.3 DFD Level 2A — Brokers Module

```mermaid
graph TD
    subgraph "External Entities"
        DHAN_API[Dhan HQ API<br/>REST + WebSocket]
        UPSTOX_API[Upstox API<br/>REST + WebSocket]
        PAPER[Paper Trading<br/>In-Memory]
    end

    subgraph "Brokers Subsystem (src/brokers/)"
        subgraph "Common Infrastructure"
            BROKER_COMMON[brokers/common/<br/>BaseWireAdapter,<br/>BaseTransport,<br/>DepthStreamHandle]
        end

        subgraph "Dhan Provider"
            DHAN_GW[brokers/providers/dhan/<br/>DhanGateway]
            DHAN_CONN[brokers/providers/dhan/<br/>DhanConnection]
            DHAN_ORD[brokers/providers/dhan/adapters/<br/>orders.py]
            DHAN_MD[brokers/providers/dhan/adapters/<br/>market_data.py]
            DHAN_PORT[brokers/providers/dhan/adapters/<br/>portfolio.py]
            DHAN_INST[brokers/providers/dhan/adapters/<br/>instruments.py]
            DHAN_STREAM[brokers/providers/dhan/adapters/<br/>streaming.py]
            DHAN_TRANSPORT[brokers/providers/dhan/<br/>transport.py]
        end

        subgraph "Upstox Provider"
            UPSTOX_GW[brokers/providers/upstox/<br/>UpstoxGateway]
            UPSTOX_CONN[brokers/providers/upstox/<br/>UpstoxConnection]
            UPSTOX_ORD[brokers/providers/upstox/adapters/<br/>orders.py]
            UPSTOX_MD[brokers/providers/upstox/adapters/<br/>market_data.py]
            UPSTOX_PORT[brokers/providers/upstox/adapters/<br/>portfolio.py]
            UPSTOX_INST[brokers/providers/upstox/adapters/<br/>instruments.py]
            UPSTOX_STREAM[brokers/providers/upstox/adapters/<br/>streaming.py]
            UPSTOX_TRANSPORT[brokers/providers/upstox/<br/>transport.py]
        end

        subgraph "Paper Provider"
            PAPER_GW[brokers/providers/paper/<br/>PaperGateway]
            PAPER_MD[brokers/providers/paper/<br/>market_data.py]
            PAPER_ORD[brokers/providers/paper/<br/>orders.py]
            PAPER_PORT[brokers/providers/paper/<br/>portfolio.py]
        end
    end

    %% Dhan flows
    DHAN_API -- "REST: Orders,<br/>Positions,<br/>Funds" --> DHAN_TRANSPORT
    DHAN_API -- "WS: Quotes,<br/>Depth,<br/>Order Updates" --> DHAN_TRANSPORT
    DHAN_TRANSPORT -- "HTTP/WS Messages" --> DHAN_CONN
    DHAN_CONN -- "Order Operations" --> DHAN_ORD
    DHAN_CONN -- "Market Data" --> DHAN_MD
    DHAN_CONN -- "Portfolio" --> DHAN_PORT
    DHAN_CONN -- "Instruments" --> DHAN_INST
    DHAN_CONN -- "Streaming" --> DHAN_STREAM
    DHAN_ORD -- "Dhan-native →<br/>Domain types" --> DHAN_GW
    DHAN_MD -- "Dhan-native →<br/>Domain types" --> DHAN_GW
    DHAN_PORT -- "Dhan-native →<br/>Domain types" --> DHAN_GW
    DHAN_INST -- "Dhan-native →<br/>Domain types" --> DHAN_GW
    DHAN_STREAM -- "Dhan-native →<br/>Domain types" --> DHAN_GW
    DHAN_GW -- "Domain Events,<br/>Order Commands" --> RT[runtime/]

    %% Upstox flows
    UPSTOX_API -- "REST: Orders,<br/>Positions,<br/>Funds" --> UPSTOX_TRANSPORT
    UPSTOX_API -- "WS: Quotes,<br/>Depth,<br/>Order Updates" --> UPSTOX_TRANSPORT
    UPSTOX_TRANSPORT -- "HTTP/WS Messages" --> UPSTOX_CONN
    UPSTOX_CONN -- "Order Operations" --> UPSTOX_ORD
    UPSTOX_CONN -- "Market Data" --> UPSTOX_MD
    UPSTOX_CONN -- "Portfolio" --> UPSTOX_PORT
    UPSTOX_CONN -- "Instruments" --> UPSTOX_INST
    UPSTOX_CONN -- "Streaming" --> UPSTOX_STREAM
    UPSTOX_ORD -- "Upstox-native →<br/>Domain types" --> UPSTOX_GW
    UPSTOX_MD -- "Upstox-native →<br/>Domain types" --> UPSTOX_GW
    UPSTOX_PORT -- "Upstox-native →<br/>Domain types" --> UPSTOX_GW
    UPSTOX_INST -- "Upstox-native →<br/>Domain types" --> UPSTOX_GW
    UPSTOX_STREAM -- "Upstox-native →<br/>Domain types" --> UPSTOX_GW
    UPSTOX_GW -- "Domain Events,<br/>Order Commands" --> RT

    %% Paper flows
    PAPER -- "In-Memory Orders" --> PAPER_ORD
    PAPER_ORD -- "Order State" --> PAPER_GW
    PAPER_MD -- "Simulated Quotes" --> PAPER_GW
    PAPER_PORT -- "Paper Portfolio" --> PAPER_GW
    PAPER_GW -- "Domain Events,<br/>Order Commands" --> RT

    %% Common infrastructure
    BROKER_COMMON -- "Base Class" --> DHAN_GW
    BROKER_COMMON -- "Base Class" --> UPSTOX_GW
    BROKER_COMMON -- "Base Class" --> PAPER_GW
```

---

## 6. Implementation Plan

### Phase 1: Foundation (Week 1-2)
1. Create `infrastructure/message_bus.py` — `MessageBus` class
2. Create `infrastructure/component.py` — `Component`, `LifecycleManager`
3. Create `infrastructure/observability.py` — `ObservabilityStack`, `HealthChecker`
4. Create `config/schema.py` — `AppConfig`, `ConfigLoader`
5. Update `domain/messages.py` — Expand message types

### Phase 2: Broker Restructuring (Week 3-4)
1. Create new directory structure (`brokers/providers/dhan/gateway.py`, etc.)
2. Move and consolidate Dhan files (102 → 8)
3. Move and consolidate Upstox files (128 → 8)
4. Move and consolidate Paper files (12 → 6)
5. Consolidate common infrastructure (37 → 5)
6. Merge runtime managers (8 → 2)

### Phase 3: Execution Engine (Week 5)
1. Update `ExecutionEngine` to use `MessageBus`
2. Implement `FillSource` protocol
3. Implement `SimulatedFillSource`, `PaperFillSource`, `BrokerFillSource`
4. Update `TradingContext` to use new patterns

### Phase 4: Composition Root (Week 6)
1. Create `runtime/factory.py` — `RuntimeFactory`
2. Create `runtime/runtime.py` — `Runtime` dataclass
3. Update `runtime/broker_infrastructure.py` if needed
4. Create YAML configuration files

### Phase 5: Testing & Documentation (Week 7)
1. Add `AdapterTestHarness` for standardized testing
2. Update existing tests
3. Create documentation
4. Run full test suite

### Phase 6: Deployment (Week 8)
1. Update Dockerfile
2. Create Helm chart
3. Create CI/CD pipeline
4. Final verification

---

## 7. File Count Summary

| Component | Current Files | Proposed Files | Reduction |
|---|---|---|---|
| **brokers/common/** | 37 | 5 | -86% |
| **brokers/providers/dhan/** | 102 | 8 | -92% |
| **brokers/providers/upstox/** | 128 | 8 | -94% |
| **brokers/providers/paper/** | 12 | 6 | -50% |
| **brokers/runtime/** | 8 | 2 | -75% |
| **brokers/services/** | 9 | 0 (merge) | -100% |
| **brokers/session/** | 4 | 0 (merge) | -100% |
| **infrastructure/** | ~30 | ~15 | -50% |
| **runtime/** | ~20 | ~5 | -75% |
| **Total** | **~307** | **~50** | **-84%** |

---

## 8. Graphify Validation

### 8.1 God Class Analysis

| Node | Degree | Source | Status |
|---|---|---|---|
| **DhanBroker** | 376 | `src/brokers/providers/dhan/wire.py` | 🔴 GOD CLASS |
| **UpstoxWireAdapter** | 195 | `src/brokers/providers/upstox/wire.py` | 🔴 GOD CLASS |
| **DhanConnection** | 121 | `src/brokers/providers/dhan/streaming/connection.py` | 🔴 GOD CLASS |
| **PaperGateway** | 158 | `src/brokers/providers/paper/paper_gateway.py` | 🟡 Reference impl |
| **TradingContext** | 67 | `src/application/oms/context/__init__.py` | 🟢 Central container |
| **BrokerRegistry** | 42 | `src/application/composer/registry.py` | 🟢 Registry |
| **ExecutionEngine** | 41 | `src/application/execution/execution_engine.py` | 🟢 Core engine |
| **BrokerAdapter** | 25 | `src/domain/ports/broker_adapter.py` | 🟢 Protocol |
| **BaseWireAdapter** | 7 | `src/brokers/common/wire_base.py` | 🟡 Under-utilized |

### 8.2 Gap Identification

| Component | Location | Status |
|---|---|---|
| **MessageBus** | `docs/architecture/e2e-spec/02-kernel-and-components.md` | ❌ Only in docs, not code |
| **Component** | Not found | ❌ Missing |
| **LifecycleManager** | Not found | ❌ Missing |
| **ObservabilityStack** | Not found | ❌ Missing |

### 8.3 Proposal Validation

| Proposal | Graphify Evidence | Validation |
|---|---|---|
| **Consolidate Dhan (102→8 files)** | DhanBroker: 376 connections, DhanConnection: 121 connections | ✅ **Strongly validated** |
| **Consolidate Upstox (128→8 files)** | UpstoxWireAdapter: 195 connections | ✅ **Strongly validated** |
| **Standardize Gateway→Connection→Adapters** | BaseWireAdapter: only 7 connections (under-used) | ✅ **Validated** |
| **Keep BrokerAdapter as core protocol** | BrokerAdapter: 25 connections, central in graph | ✅ **Confirmed correct** |
| **Keep TradingContext as container** | TradingContext: 67 connections, connects to OM/PM/RM/EE | ✅ **Confirmed correct** |
| **Keep ExecutionEngine as core** | ExecutionEngine: 41 connections, uses FillSource/OrderManager | ✅ **Confirmed correct** |
| **Keep BrokerInfrastructure as DI** | BrokerInfrastructure: 13 connections, composition root | ✅ **Confirmed correct** |
| **Add MessageBus** | MessageBus: only in docs, not in code | ✅ **Gap confirmed** |
| **Standardize sub-adapter interfaces** | 20+ sub-adapters per connection, inconsistent naming | ✅ **Validated** |
| **Add AdapterTestHarness** | 350+ test classes already exist, need standardization | ✅ **Validated** |

---

## 9. Testing Strategy

### 9.1 Test Pyramid

```
tests/
├── unit/                     # 40% — Domain + pure logic tests
│   ├── test_order_manager.py
│   ├── test_position_manager.py
│   ├── test_risk_manager.py
│   └── test_message_bus.py
│
├── component/                # 25% — Single-service tests
│   ├── test_execution_engine.py
│   ├── test_data_engine.py
│   └── test_strategy_engine.py
│
├── integration/              # 20% — Adapter + engine integration
│   ├── test_dhan_adapter.py
│   ├── test_upstox_adapter.py
│   └── test_paper_adapter.py
│
├── e2e/                      # 10% — Full framework lifecycle
│   ├── test_full_lifecycle.py
│   ├── test_paper_trading.py
│   └── test_live_smoke.py
│
├── architecture/             # 5% — Import-linter + dependency rules
│   ├── test_layer_isolation.py
│   ├── test_no_broker_imports.py
│   └── test_zero_parity.py
│
└── property/                 # 5% — Hypothesis property-based tests
    ├── test_order_idempotency.py
    ├── test_position_invariants.py
    └── test_risk_bounds.py
```

### 9.2 Adapter Test Harness

```python
class AdapterTestHarness:
    """Standardized test harness for broker adapters."""
    
    def __init__(self, adapter: BrokerAdapter):
        self._adapter = adapter
        self._mock_server = MockBrokerServer()
    
    def test_order_lifecycle(self) -> None:
        """Test place → ack → fill → cancel lifecycle."""
        # Setup mock responses
        self._mock_server.add_response("POST", "/orders", {
            "success": True,
            "order_id": "TEST-001",
            "status": "PLACED",
        })
        
        # Place order
        response = self._adapter.place_order(OrderRequest(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type=OrderSide.BUY,
            quantity=10,
            price=Decimal("2500"),
            order_type=OrderType.LIMIT,
            product_type="INTRADAY",
            validity=TimeInForce.DAY,
        ))
        
        assert response.success
        assert response.order_id == "TEST-001"
        
        # Verify order in orderbook
        orders = self._adapter.get_orderbook()
        assert any(o.order_id == "TEST-001" for o in orders)
```

---

## 10. Deployment Architecture

### 10.1 Docker (Multi-stage)

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv export -o requirements.txt
RUN uv pip install --system -r requirements.txt --target /install

FROM python:3.12-slim AS runtime
WORKDIR /app
COPY --from=builder /install /usr/local/lib/python3.12/site-packages
COPY src/ src/
COPY config/ config/

RUN useradd -m trader
USER trader

ENTRYPOINT ["python", "-m", "tradex"]
CMD ["run", "--config", "config/paper.yaml"]
```

### 10.2 Configuration (YAML)

```yaml
# config/paper.yaml
runtime:
  mode: paper
  timezone: Asia/Kolkata
  log_level: INFO

brokers:
  - id: paper
    type: paper
    enabled: true

data:
  storage:
    root: data/lake
    catalog: data/lake/catalog.json
  sync:
    timeframe: 1m
    workers: 10

risk:
  max_position_size: 100000.00
  max_daily_loss: 5000.00
  max_orders_per_day: 50

observability:
  metrics:
    enabled: true
    port: 8000
  tracing:
    enabled: false
  health:
    port: 9090

strategies:
  - id: momentum_1
    type: momentum
    instruments: ["RELIANCE", "TCS", "INFY"]
    params:
      lookback: 20
      threshold: 0.02
```
