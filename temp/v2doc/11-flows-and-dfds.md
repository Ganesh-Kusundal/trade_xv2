# 11 — Flows & Data Flow Diagrams

## 1. Level 0 — Context Diagram

```mermaid
graph TB
    subgraph External
        User[Trader / Operator]
        NSE[NSE Exchange]
        BSE[BSE Exchange]
        Dhan[Dhan Broker API]
        Upstox[Upstox Broker API]
    end

    subgraph TradeXV2
        CLI[CLI / TUI]
        API[REST API]
        Core[Trading Core]
        DataLake[(DataLake)]
    end

    User -->|Commands| CLI
    User -->|Commands| API
    CLI -->|Order Commands| Core
    API -->|Order Commands| Core
    Core -->|Place/Cancel Orders| Dhan
    Core -->|Place/Cancel Orders| Upstox
    Dhan -->|Market Data| Core
    Upstox -->|Market Data| Core
    Core -->|Ingest| DataLake
    DataLake -->|Historical Data| Core
    Core -->|Positions, P&L| CLI
    Core -->|Positions, P&L| API
```

## 2. Level 1 — System Decomposition

```mermaid
graph TB
    subgraph Interface
        CLI[CLI / TUI]
        REST[REST API]
        MCP[MCP Server]
    end

    subgraph Runtime
        Bootstrap[Bootstrap]
        Lifecycle[Lifecycle Manager]
        Config[Config Manager]
        Factory[Component Factory]
    end

    subgraph Application
        EE[Execution Engine]
        OM[Order Manager]
        PM[Position Manager]
        RM[Risk Manager]
        SE[Strategy Engine]
        DE[Data Engine]
    end

    subgraph Infrastructure
        Dhan[ Dhan Gateway]
        Upstox[Upstox Gateway]
        Paper[Paper Gateway]
        Catalog[Data Catalog]
    end

    subgraph Domain
        Entities[Entities]
        Events[Events]
        Ports[Ports]
        Bus[Message Bus]
    end

    CLI --> Bootstrap
    REST --> Bootstrap
    MCP --> Bootstrap
    Bootstrap --> Config
    Bootstrap --> Factory
    Factory --> EE
    Factory --> OM
    Factory --> PM
    Factory --> RM
    Factory --> SE
    Factory --> DE
    Factory --> Dhan
    Factory --> Upstox
    Factory --> Paper
    Factory --> Catalog

    EE --> OM
    EE --> PM
    EE --> RM
    EE --> Bus
    OM --> Bus
    PM --> Bus
    RM --> Bus
    SE --> Bus

    EE --> Dhan
    EE --> Upstox
    EE --> Paper
    DE --> Catalog
    SE --> DE
```

## 3. Level 2 — Order Placement Flow

```mermaid
sequenceDiagram
    participant User
    participant API as REST API
    participant Bus as MessageBus
    participant EE as ExecutionEngine
    participant RM as RiskManager
    participant OM as OrderManager
    participant FS as FillSource
    participant GW as BrokerGateway
    participant BRK as Broker API
    participant PM as PositionManager

    User->>API: POST /orders {symbol, side, qty}
    API->>Bus: publish(PlaceOrderCommand)
    Bus->>EE: _on_place_order(command)

    EE->>RM: check_order(command)
    alt Risk DENIED
        RM-->>EE: CheckResult(ok=False, reason)
        EE->>Bus: publish(OrderRejected)
        Bus-->>API: OrderRejected event
        API-->>User: 422 {reason}
    else Risk OK
        RM-->>EE: CheckResult(ok=True)
        EE->>Bus: publish(OrderPlaced)
        EE->>OM: register_order(id, command)
        EE->>FS: submit_order(command)

        alt Live Mode
            FS->>GW: place_order(command)
            GW->>BRK: HTTP POST /orders
            BRK-->>GW: {broker_order_id, status}
            GW-->>FS: Order
            FS-->>EE: order_id
        else Paper/Backtest
            FS-->>EE: order_id (simulated)
        end
    end
```

## 4. Level 2 — Fill Processing Flow

```mermaid
sequenceDiagram
    participant BRK as Broker API
    participant GW as BrokerGateway
    participant WS as WebSocket
    participant EE as ExecutionEngine
    participant OM as OrderManager
    participant PM as PositionManager
    participant RM as RiskManager
    participant Bus as MessageBus
    participant Strategy

    BRK->>WS: Fill update (WebSocket)
    WS->>GW: Parse fill message
    GW->>EE: on_fill(trade)

    EE->>OM: apply_fill(trade)
    OM->>OM: Update order status
    OM->>Bus: publish(OrderFilled)

    EE->>PM: apply_fill(trade)
    PM->>PM: Update position
    PM->>Bus: publish(PositionChanged)

    EE->>RM: on_fill(trade)
    RM->>RM: Update P&L, check drawdown

    Bus-->>Strategy: on_order_filled(event)
    Bus-->>Strategy: on_position_changed(event)

    alt Drawdown exceeded
        RM->>Bus: publish(KillSwitchActivated)
        Bus-->>EE: Kill switch
        EE->>EE: Cancel all orders
    end
```

## 5. Level 2 — Market Data Flow

```mermaid
sequenceDiagram
    participant Exchange
    participant WS as WebSocket
    participant GW as BrokerGateway
    participant Pipeline as LiveTickPipeline
    participant Strategy
    participant Catalog as DataCatalog
    participant Bus as MessageBus

    Exchange->>WS: Tick data (WebSocket)
    WS->>GW: Raw tick message
    GW->>GW: Parse & normalize
    GW->>Pipeline: on_tick(quote)

    par Dispatch to strategy
        Pipeline->>Strategy: on_tick(quote)
    and Buffer for flush
        Pipeline->>Pipeline: Buffer tick
    end

    Note over Pipeline: Every 60 seconds
    Pipeline->>Catalog: ingest_ticks(symbol, df)
    Catalog->>Catalog: Write to Parquet

    Bus->>Bus: publish(TickReceived)
```

## 6. Level 2 — Backtest Flow

```mermaid
sequenceDiagram
    participant User
    participant BT as BacktestEngine
    participant Catalog as DataCatalog
    participant Bus as MessageBus
    participant EE as ExecutionEngine
    participant FS as SimulatedFillSource
    participant Strategy
    participant OM as OrderManager
    participant PM as PositionManager

    User->>BT: run(strategy, symbols, start, end)
    BT->>Catalog: get_bars(symbols, start, end)
    Catalog-->>BT: DataFrame

    loop For each bar
        BT->>FS: on_bar(bar)
        FS->>FS: Check pending orders

        alt Order fills
            FS->>EE: on_fill(trade)
            EE->>OM: apply_fill(trade)
            EE->>PM: apply_fill(trade)
            EE->>Bus: publish(OrderFilled)
            Bus-->>Strategy: on_order_filled(event)
        end

        BT->>Strategy: on_bar(bar)

        alt Strategy places order
            Strategy->>Bus: publish(PlaceOrderCommand)
            Bus->>EE: _on_place_order(command)
            EE->>FS: submit_order(command)
            FS->>FS: Add to pending
        end
    end

    BT-->>User: BacktestResult
```

## 7. Component Lifecycle Flow

```mermaid
stateDiagram-v2
    [*] --> UNINITIALIZED : Component created

    UNINITIALIZED --> INITIALIZED : initialize()
    note right of INITIALIZED
        Subscriptions registered
        Resources allocated
    end note

    INITIALIZED --> RUNNING : start()
    note right of RUNNING
        Processing messages
        Business logic active
    end note

    RUNNING --> STOPPED : stop()
    note right of STOPPED
        Subscriptions cleared
        Resources released
    end note

    RUNNING --> ERROR : Exception
    note right of ERROR
        Component failed
        Requires intervention
    end note

    STOPPED --> INITIALIZED : reset() + initialize()
    ERROR --> UNINITIALIZED : hard_reset()
```

## 8. Broker Connection Flow

```mermaid
sequenceDiagram
    participant App
    participant GW as BrokerGateway
    participant Conn as BrokerConnection
    participant Transport as BaseTransport
    participant Orders as OrdersAdapter
    participant MarketData as MarketDataAdapter
    participant Streaming as StreamingAdapter
    participant Resolver as SymbolResolver
    participant API as Broker API

    App->>GW: initialize(config)
    GW->>Conn: __init__(config)
    Conn->>Transport: __init__(base_url, token)
    Conn->>Orders: __init__(transport, wire, resolver)
    Conn->>MarketData: __init__(transport, wire, resolver)
    Conn->>Streaming: __init__(config, wire, resolver)

    App->>GW: authenticate()
    GW->>Conn: authenticate()
    Conn->>Transport: authenticate()
    Transport->>API: POST /auth
    API-->>Transport: {access_token}
    Transport-->>Conn: True

    App->>GW: get_quote("RELIANCE", "NSE")
    GW->>Conn: market_data.get_quote()
    Conn->>Resolver: resolve("RELIANCE", "NSE")
    Resolver-->>Conn: DhanInstrumentRef
    Conn->>Transport: GET /market_data
    Transport->>API: HTTP GET
    API-->>Transport: Raw response
    Transport-->>Conn: Raw data
    Conn->>Conn: wire.map_quote(data)
    Conn-->>GW: Quote
    GW-->>App: Quote
```

## 9. Data Flow Diagram — Source Selection

```mermaid
graph LR
    subgraph Request
        A[get_bars request]
    end

    subgraph Source Selection
        B{Data in DataLake?}
        C{Data fresh enough?}
    end

    subgraph Sources
        D[DataLake]
        E[Broker API]
    end

    subgraph Result
        F[Return data]
        G[Ingest into DataLake]
    end

    A --> B
    B -->|Yes| C
    B -->|No| E
    C -->|Yes| D
    C -->|No| E
    D --> F
    E --> F
    E --> G
    G --> D
```

## 10. Risk Check Flow

```mermaid
graph TB
    A[PlaceOrderCommand] --> B{Kill Switch Active?}
    B -->|Yes| Z[REJECT: Kill switch]
    B -->|No| C{Position Limit?}
    C -->|Exceeded| Z2[REJECT: Position limit]
    C -->|OK| D{Order Size?}
    D -->|Exceeded| Z3[REJECT: Order size]
    D -->|OK| E{Daily Loss?}
    E -->|Exceeded| Z4[REJECT: Daily loss]
    E -->|OK| F{Order Rate?}
    F -->|Exceeded| Z5[REJECT: Rate limit]
    F -->|OK| G[APPROVE]

    Z --> H[publish OrderRejected]
    Z2 --> H
    Z3 --> H
    Z4 --> H
    Z5 --> H
    G --> I[publish OrderPlaced]
```

## 11. Deployment Flow

```mermaid
graph TB
    subgraph Development
        Dev[Developer]
        Git[Git Push]
    end

    subgraph CI
        GH[GitHub Actions]
        Lint[Lint + Type Check]
        Test[Unit + Integration Tests]
        ImportLint[Import-Linter]
        Build[Build Package]
    end

    subgraph CD
        Docker[Docker Build]
        Registry[Container Registry]
        K8s[Kubernetes]
    end

    subgraph Production
        Pod1[Trading Pod 1]
        Pod2[Trading Pod 2]
        Monitor[Monitoring]
    end

    Dev --> Git
    Git --> GH
    GH --> Lint
    GH --> Test
    GH --> ImportLint
    GH --> Build
    Build --> Docker
    Docker --> Registry
    Registry --> K8s
    K8s --> Pod1
    K8s --> Pod2
    Pod1 --> Monitor
    Pod2 --> Monitor
```
