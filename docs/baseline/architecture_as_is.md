# D0.4 — As-Is Architecture Diagrams

> Generated from code-only analysis. All diagrams verified against actual imports and call paths.

---

## 1. Layer Dependency Graph

```mermaid
graph TD
    subgraph "Interface Layer"
        API["interface/api<br/>FastAPI REST + WebSocket"]
        CLI["interface/ui<br/>Interactive CLI"]
        AGENT["interface/agent<br/>AI Agent Framework"]
        MCP_B["brokers/mcp<br/>FastMCP Server"]
        WEB["web/<br/>React SPA"]
    end

    subgraph "Application Layer"
        OMS["application/oms<br/>Order Manager + Risk + Trade Recorder"]
        TRADING["application/trading<br/>Trading Orchestrator"]
        STREAMING["application/streaming<br/>Tick Router + Candle Aggregator"]
        PORTFOLIO["application/portfolio<br/>Portfolio Service"]
        EXECUTION["application/execution<br/>Execution Service"]
        STRAT["application/strategy_engine<br/>Live Strategy Engine"]
        SERVICES["application/services<br/>Canonical Instrument Registry"]
    end

    subgraph "Broker Layer"
        SESSION["brokers/session<br/>BrokerSession (public API)"]
        SERVICES_CORE["brokers/services<br/>Single Service Core"]
        RUNTIME_B["brokers/runtime<br/>RuntimeBundle"]
        CERT["brokers/certification<br/>Broker Certifier"]
        DIAG["brokers/diagnostics<br/>Doctor/Health/Benchmark"]
        DHAN["brokers/dhan<br/>Dhan Adapter"]
        UPSTOX["brokers/upstox<br/>Upstox Adapter"]
        PAPER["brokers/paper<br/>Paper Simulator"]
        COMMON["brokers/common<br/>ACL, Idempotency, Validation"]
    end

    subgraph "Analytics Layer"
        BACKTEST["analytics/backtest<br/>BacktestEngine"]
        REPLAY["analytics/replay<br/>ReplayEngine"]
        PIPELINE["analytics/pipeline<br/>FeaturePipeline"]
        STRATEGY["analytics/strategy<br/>StrategyPipeline"]
        SCANNER["analytics/scanner<br/>ScannerRunner"]
        OPTIONS["analytics/options<br/>Options Analytics"]
    end

    subgraph "Infrastructure Layer"
        EVENTBUS["infrastructure/event_bus<br/>EventBus + DLQ"]
        LIFECYCLE["infrastructure/lifecycle<br/>LifecycleManager"]
        GATEWAY["infrastructure/gateway<br/>Gateway Factory"]
        PERSIST["infrastructure/persistence<br/>SQLite Stores"]
        DI["infrastructure/di<br/>DI Container"]
        METRICS["infrastructure/metrics<br/>MetricsRegistry"]
        SECURE["infrastructure/security<br/>Secrets + SSL"]
    end

    subgraph "Domain Layer"
        INSTRUMENTS["domain/instruments<br/>Instrument Aggregate"]
        EVENTS["domain/events<br/>Domain Events"]
        ORDERS["domain/orders<br/>Order Aggregate"]
        PORT["domain/ports<br/>Protocol Interfaces"]
        PORTFOLIO_D["domain/portfolio<br/>Position + PnL"]
        RISK_D["domain/risk<br/>Kill Switch + Circuit Breaker"]
        CAPABILITIES["domain/capabilities<br/>Capability System"]
        UNIVERSE["domain/universe<br/>Instrument Universe"]
    end

    subgraph "Data Layer"
        DATALAKE["datalake<br/>Parquet + DuckDB"]
        CONFIG["config<br/>AppConfig + FeatureFlags"]
    end

    %% Interface → Application/Broker
    API --> OMS
    API --> STREAMING
    API --> PORTFOLIO
    API --> DATALAKE
    CLI --> SESSION
    CLI --> SERVICES_CORE
    AGENT --> SERVICES_CORE
    MCP_B --> SERVICES_CORE
    WEB --> API

    %% Application → Domain
    OMS --> ORDERS
    OMS --> EVENTS
    OMS --> PORT
    TRADING --> STRATEGY
    TRADING --> PIPELINE
    TRADING --> OMS
    STREAMING --> INSTRUMENTS
    PORTFOLIO --> PORTFOLIO_D
    EXECUTION --> OMS
    STRAT --> TRADING
    SERVICES --> INSTRUMENTS

    %% Broker → Domain + Infrastructure
    SESSION --> RUNTIME_B
    RUNTIME_B --> GATEWAY
    SERVICES_CORE --> SESSION
    CERT --> SESSION
    DIAG --> SESSION
    DHAN --> COMMON
    DHAN --> GATEWAY
    UPSTOX --> COMMON
    UPSTOX --> GATEWAY
    PAPER --> COMMON
    PAPER --> GATEWAY

    %% Infrastructure → Domain
    EVENTBUS --> EVENTS
    LIFECYCLE --> PORT
    GATEWAY --> PORT
    PERSIST --> PORT
    DI --> PORT
    METRICS --> PORT

    %% Analytics → Domain
    BACKTEST --> REPLAY
    REPLAY --> STRATEGY
    REPLAY --> PIPELINE
    PIPELINE --> INSTRUMENTS
    STRATEGY --> PORT
    SCANNER --> PIPELINE

    %% Data → Domain
    DATALAKE --> PORT

    %% Style
    style DOMAIN fill:#e8f5e9,stroke:#2e7d32
    style INFRA fill:#e3f2fd,stroke:#1565c0
    style APP fill:#fff3e0,stroke:#ef6c00
    style BROKER fill:#fce4ec,stroke:#c62828
    style INTERFACE fill:#f3e5f5,stroke:#7b1fa2
    style ANALYTICS fill:#e0f2f1,stroke:#00695c
    style DATA fill:#fff8e1,stroke:#f9a825
```

---

## 2. Broker Plugin Architecture

```mermaid
graph TD
    EP["Entry Points<br/>tradex.brokers group"] --> IMPORT["importlib.import_module()"]
    IMPORT --> SELF["Self-Registration"]
    
    SELF --> BP["register_broker_plugin()<br/>BrokerPlugin dataclass"]
    SELF --> DA["register_data_adapter()<br/>DataProvider class"]
    SELF --> XP["register_execution_provider()<br/>ExecutionProvider class"]
    SELF --> SM["register_segment_mapper()<br/>ExchangeSegment mapper"]
    SELF --> BE["register_broker_extensions()<br/>Extension classes"]
    
    BP --> DISC["BrokerDiscovery<br/>runtime/broker_discovery.py"]
    DISC --> GF["GatewayFactory<br/>infrastructure/gateway/factory.py"]
    
    GF --> TRANSPORT["Transport Creation<br/>importlib lazy import"]
    GF --> STRUCTURAL["Structural Readiness Probe<br/>Token present on connection"]
    GF --> AUTH["Authenticated Readiness Probe<br/>Actual API call (funds/profile)"]
    AUTH -->|Rejected| TOTP["Token Refresh + Retry<br/>At most 1 retry"]
    AUTH -->|Accepted| RESULT["BootstrapResult<br/>status + gateway + warnings"]
    
    DA --> DP_PORT["DataProvider Protocol<br/>quote(), history(), subscribe()"]
    XP --> X_PORT["ExecutionProvider Protocol<br/>place_order(), cancel(), modify()"]
    SM --> SEG["ExchangeSegment<br/>NSE_EQ, NSE_FO, BSE, MCX"]
    BE --> EXT_PORT["ExtendedCapabilities<br/>Broker-specific superpowers"]
    
    subgraph "Paper Broker"
        P_PDP["PaperDataProvider"]
        P_XPP["PaperExecutionProvider"]
        P_SEG["PaperSegmentMapper"]
    end
    
    subgraph "Dhan Broker"
        D_PDP["DhanDataProvider"]
        D_XPP["DhanExecutionProvider"]
        D_SEG["DhanSegmentMapper"]
        D_EXT["DhanExtendedCapabilities<br/>(~365 lines, 20+ methods)"]
    end
    
    subgraph "Upstox Broker"
        U_PDP["UpstoxDataProvider"]
        U_XPP["UpstoxExecutionProvider"]
        U_SEG["UpstoxSegmentMapper"]
        U_EXT["UpstoxDepth30, UpstoxNews"]
    end
    
    DA -.-> P_PDP & D_PDP & U_PDP
    XP -.-> P_XPP & D_XPP & U_XPP
    SM -.-> P_SEG & D_SEG & U_SEG
    BE -.-> D_EXT & U_EXT
```

---

## 3. OMS Order Lifecycle

```mermaid
sequenceDiagram
    autonumber
    participant Client as BrokerSession
    participant OM as OrderManager
    participant IG as IdempotencyGuard
    participant RV as OrderValidator
    participant RM as RiskManager
    participant CB as LossCircuitBreaker
    participant OL as OrderLifecycle
    participant LO as LedgerOutbox
    participant OSV as OrderStateValidator
    participant GW as GatewaySubmit
    participant EB as EventBus
    participant AAL as OrderAuditLogger

    Client->>OM: place_order(request, submit_fn)
    
    Note over OM: Acquire RLock
    
    OM->>IG: check_and_reserve(correlation_id)
    alt Duplicate detected
        IG-->>OM: (order_id, early_result)
        OM-->>Client: OrderResult (cached dedup)
    end
    
    OM->>RV: build_and_validate(order_id, request)
    RV->>RM: check_order(order)
    RM->>CB: check_loss_circuit()
    alt Kill switch active
        RM-->>OM: Rejection (KILL_SWITCH)
    else Loss threshold breached
        RM-->>OM: Rejection (CIRCUIT_BREAKER)
    else Margin insufficient
        RM-->>OM: Rejection (INSUFFICIENT_MARGIN)
    end
    RM-->>RV: passed
    RV-->>OM: (Order, None) — no rejection
    
    OM->>OL: submit_to_broker(order, submit_fn)
    OL->>OSV: validate_transition(PENDING_VALIDATION → SUBMITTED)
    OL->>LO: record(intent)  ← DURABLE WRITE FIRST
    
    Note over OL: Release RLock before I/O
    
    OL->>GW: submit_fn(order)  ← NETWORK CALL (OUTSIDE LOCK)
    GW-->>OL: broker_response
    
    alt Success
        OL->>LO: confirm(intent_id)
        OL->>OSV: transition(SUBMITTED → PLACED)
    else Failure
        OL->>LO: revert(intent_id)
        OL->>OSV: transition(SUBMITTED → REJECTED)
    end
    
    Note over OM: Re-acquire RLock for state mutation
    
    OM->>OL: record_and_publish(orders, order, request)
    OL->>AAL: log_event(order_id, ORDER_PLACED)
    OL->>EB: publish(DomainEvent)
    
    Note over OM: Release RLock
    
    OM-->>Client: OrderResult.ok
```

---

## 4. Event Flow Architecture

```mermaid
graph TD
    subgraph "Event Sources"
        BROKER_WS["Broker WebSocket<br/>Raw ticks"]
        BROKER_HTTP["Broker HTTP<br/>Order responses"]
        OMS_EVENTS["OMS<br/>Order/Trade events"]
        STRATEGY_EVENTS["Strategy Pipeline<br/>Signal/Candidate events"]
        SYSTEM_EVENTS["System<br/>Session/Health events"]
    end

    subgraph "Event Production"
        WIRE["Wire Adapter<br/>Normalize raw → domain"]
        TICK_ROUTER["TickRouter<br/>Dedup + fan-out"]
        ORDER_LC["OrderLifecycle<br/>Record + publish"]
        STRAT_PIPE["StrategyPipeline<br/>Evaluate + signal"]
    end

    subgraph "Event Bus (infrastructure/event_bus/event_bus.py)"
        EB_CORE["EventBus Core<br/>587 lines"]
        COPY["Copy-on-Publish<br/>dataclasses.replace()"]
        IDEMP["Idempotency Check<br/>TTL-based or in-memory"]
        ELOG["EventLog (JSONL)<br/>BufferedEventLog<br/>sync_mode for capital events"]
        HANDLERS["Handler Dispatch<br/>Sequential, never swallowed"]
        DLQ["DeadLetterQueue<br/>Persistent (SQLite) or In-Memory"]
        ALERTING["AlertingEngine<br/>Background daemon thread"]
        METRICS["EventMetrics<br/>Counters + rates"]
    end

    subgraph "Async Bridge"
        ASYNC_BUS["AsyncEventBus<br/>Bounded deque + worker thread"]
        BACKPRESSURE["Backpressure<br/>Normal: drop at 10K<br/>Critical: overflow to 20K"]
    end

    subgraph "Event Consumers"
        POS_MGR["PositionManager<br/>Update positions on fills"]
        PORT_SVC["PortfolioService<br/>Recompute PnL"]
        TRADE_REC["TradeRecorder<br/>Idempotent trade storage"]
        AUDIT["AuditLogger<br/>JSONL audit trail"]
        API_WS["API WebSocket<br/>Push to frontend"]
        SESSION_REC["SessionRecorder<br/>Fire-and-forget JSONL"]
    end

    BROKER_WS --> WIRE --> TICK_ROUTER
    BROKER_HTTP --> ORDER_LC
    STRATEGY_EVENTS --> STRAT_PIPE

    WIRE --> EB_CORE
    ORDER_LC --> EB_CORE
    STRAT_PIPE --> EB_CORE
    SYSTEM_EVENTS --> EB_CORE

    EB_CORE --> COPY --> IDEMP
    IDEMP --> ELOG
    IDEMP --> HANDLERS
    HANDLERS -->|failure| DLQ
    EB_CORE --> ALERTING
    EB_CORE --> METRICS

    EB_CORE --> ASYNC_BUS --> BACKPRESSURE

    HANDLERS --> POS_MGR
    HANDLERS --> PORT_SVC
    HANDLERS --> TRADE_REC
    HANDLERS --> AUDIT
    HANDLERS --> API_WS
    EB_CORE --> SESSION_REC
```

---

## 5. End-to-End Live Trading Data Flow

```mermaid
graph TD
    subgraph "Broker (Dhan/Upstox)"
        WS_FEED["WebSocket Feed<br/>Raw ticks + depth"]
        REST_API["REST API<br/>Orders + Portfolio"]
    end

    subgraph "Wire Layer"
        WIRE_D["DhanWireAdapter<br/>Transport boundary"]
        WIRE_U["UpstoxWireAdapter<br/>Transport boundary"]
    end

    subgraph "Streaming (application/streaming)"
        SM["SessionManager<br/>WebSocket lifecycle"]
        RC["ReconnectController<br/>Exponential backoff"]
        TR["TickRouter<br/>Normalize → Dedup → Fan-out"]
        CA["CandleAggregator<br/>Tick → OHLCV (multi-TF)"]
    end

    subgraph "Strategy (analytics/strategy)"
        SCAN["ScannerRunner<br/>Momentum/Volume/RS/Breakout"]
        PIPE["FeaturePipeline<br/>20+ composable features"]
        STRAT["StrategyPipeline<br/>Multi-strategy evaluation"]
    end

    subgraph "Trading (application/trading)"
        TO["TradingOrchestrator<br/>807 lines — candidate→order"]
        FF["PipelineFeatureFetcher<br/>LRU-cached features"]
    end

    subgraph "OMS (application/oms)"
        OM["OrderManager<br/>Thread-safe (RLock)"]
        IG["IdempotencyGuard<br/>correlation_id dedup"]
        RISK["RiskManager<br/>Kill switch + circuit breaker"]
        OL["OrderLifecycle<br/>State machine + audit"]
        LO["LedgerOutbox<br/>Record-then-submit"]
        TC["TradingContext<br/>809 lines — lifecycle"]
    end

    subgraph "Execution (application/execution)"
        EXEC["ExecutionService<br/>Live/Paper/Replay dispatch"]
        SUBMIT["GatewaySubmit<br/>Broker HTTP transport"]
    end

    subgraph "Persistence"
        SQLITE["SQLite WAL<br/>Orders + Execution Ledger"]
        EVENT_LOG["EventLog JSONL<br/>Append-only event stream"]
        PARQUET["Parquet Storage<br/>Historical OHLCV"]
        DUCKDB["DuckDB Catalog<br/>Symbol metadata + quality"]
    end

    subgraph "Interfaces"
        API["REST API<br/>97 endpoints"]
        WS_API["WebSocket<br/>3 endpoints"]
        CLI["CLI<br/>34 commands"]
        MCP["MCP Server<br/>24 tools"]
        REACT["React SPA<br/>Dashboard"]
    end

    %% Data Flow
    WS_FEED --> WIRE_D & WIRE_U
    WIRE_D & WIRE_U --> SM
    SM --> RC
    SM --> TR
    TR --> CA
    CA --> PARQUET

    TR --> SCAN
    SCAN --> STRAT
    STRAT --> TO
    TO --> FF
    FF --> PIPE

    TO --> EXEC
    EXEC --> OM
    OM --> IG --> RISK --> OL
    OL --> LO --> SUBMIT
    SUBMIT --> REST_API

    OL --> EVENT_LOG
    OM --> SQLITE

    TC --> OM
    TC --> SM

    %% Interface access
    API --> EXEC
    API --> PORTFOLIO_S["PortfolioService"]
    WS_API --> TR
    CLI --> BROKER_SVC["brokers/services/core.py"]
    MCP --> BROKER_SVC
    REACT --> API
```

---

## 6. Strategy Parity Model

> The same `FeaturePipeline` + `StrategyPipeline` runs in every mode.

```mermaid
graph TD
    PIPE["FeaturePipeline<br/>20+ composable features"]
    STRAT["StrategyPipeline<br/>Multi-strategy evaluation"]

    subgraph "Mode: Scanner (Historical)"
        SCAN_D["DuckDB/Parquet Data"]
        SCAN_D --> PIPE --> STRAT --> CANDIDATES["Candidates"]
    end

    subgraph "Mode: Backtest (Historical)"
        BT_DATA["ReplayEngine bars"]
        BT_DATA --> PIPE --> STRAT --> BT_SIGNALS["Signals → Simulated Fills → PnL"]
    end

    subgraph "Mode: Paper (Simulated)"
        PAPER_TICKS["PaperBroker quotes"]
        PAPER_TICKS --> PIPE --> STRAT --> PAPER_SIGNALS["Signals → SimulatedOMSAdapter"]
    end

    subgraph "Mode: Live (Real)"
        LIVE_TICKS["Real broker WebSocket"]
        LIVE_TICKS --> PIPE --> STRAT --> LIVE_SIGNALS["Signals → OrderManager → Real broker"]
    end

    style PIPE fill:#e8f5e9,stroke:#2e7d32
    style STRAT fill:#e8f5e9,stroke:#2e7d32
```

**Key Insight**: Signal generation is identical across all modes. Only execution differs:
- Scanner: signals → candidates (no execution)
- Backtest: signals → simulated fills (ReplayEngine)
- Paper: signals → SimulatedOMSAdapter (fake broker)
- Live: signals → OrderManager → real broker

---

## 7. Component Ownership Map

```mermaid
graph LR
    subgraph "Domain (Import-Isolated)"
        D1["instruments"]
        D2["events"]
        D3["orders"]
        D4["portfolio"]
        D5["ports"]
        D6["risk"]
        D7["capabilities"]
        D8["value_objects"]
    end

    subgraph "Application (→ Domain only)"
        A1["oms"]
        A2["trading"]
        A3["streaming"]
        A4["portfolio"]
        A5["execution"]
        A6["strategy_engine"]
    end

    subgraph "Infrastructure (→ Domain + App)"
        I1["event_bus"]
        I2["lifecycle"]
        I3["gateway"]
        I4["persistence"]
        I5["di"]
        I6["metrics"]
        I7["security"]
    end

    subgraph "Broker (→ Domain + Infra)"
        B1["dhan"]
        B2["upstox"]
        B3["paper"]
        B4["common"]
        B5["session"]
        B6["services"]
    end

    subgraph "Interface (→ All)"
        IF1["api"]
        IF2["ui"]
        IF3["agent"]
        IF4["mcp"]
    end

    A1 -.-> D3
    A2 -.-> D1
    A4 -.-> D4
    B1 -.-> D5
    B5 -.-> D5
    I1 -.-> D2
    I3 -.-> D5
    IF1 -.-> A1
    IF2 -.-> B5
```

---

## Appendix: Import-Linter Contract Results

All 15 import-linter contracts **PASS**:

| Contract | Source | Forbidden | Status |
|----------|--------|-----------|--------|
| Domain isolation | `domain` | application, brokers, analytics, interface, config, infrastructure, datalake, plugins, tradex, runtime | ✅ PASS |
| Application boundary | `application` | brokers, interface, datalake | ✅ PASS |
| Broker generic | `brokers.common` | brokers.dhan, brokers.upstox | ✅ PASS |
| CLI/UI isolation | datalake, analytics | cli | ✅ PASS |
| No broker branching | generic code | broker-specific if/else | ✅ PASS |
| Wire boundary | `brokers/*/wire.py` | — | ✅ PASS |
| 9 additional contracts | Various | Various | ✅ PASS |

**27 stale `ignore_imports` warnings** — safe to clean up in Phase 3.
