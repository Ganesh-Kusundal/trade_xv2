# 08 — Flows and Data Flow Diagrams

## 1. Purpose

This document defines end-to-end flow contracts and data flow diagrams (DFDs) at levels 0–2. Every flow includes an Expected Behavior Contract specifying inputs, outputs, timing, state transitions, and failure modes.

## 2. DFD Level 0 — Context Diagram

```mermaid
graph LR
    subgraph external [External Entities]
        OP[Operator CLI/TUI/API]
        BR[Dhan/Upstox Broker APIs]
        DS[Data Sources NSE/Parquet/DuckDB]
    end

    subgraph framework [TradeX Framework]
        FW[Runtime + Kernel]
    end

    OP -->|"Commands, Config, Queries"| FW
    FW -->|"Results, Reports, Logs"| OP
    FW -->|"Orders, Cancellations, Modifications"| BR
    BR -->|"Market Data, Order Updates, Fills"| FW
    FW -->|"Historical Data Requests"| DS
    DS -->|"OHLCV, Instruments, Corporate Actions"| FW
```

## 3. DFD Level 1 — Major System Components

```mermaid
graph TD
    subgraph external [External]
        OP[Operator]
        BROKERS[Broker APIs]
        DATA[Data Sources]
    end

    subgraph framework [TradeX Framework]
        CLI[CLI / TUI / API]
        RT[Runtime Composition Root]
        OMS[OMS Order/Position/Risk]
        EXEC[Execution Engine]
        ANALYTICS[Analytics Strategy/Backtest]
        DATALAKE[Datalake Storage]
        DOM[Domain Entities/Ports/Events]
    end

    OP --> CLI
    CLI --> RT
    RT --> OMS
    RT --> EXEC
    RT --> ANALYTICS
    RT --> DATALAKE
    OMS --> EXEC
    EXEC --> BROKERS
    BROKERS --> EXEC
    BROKERS --> ANALYTICS
    ANALYTICS --> CLI
    ANALYTICS --> DATALAKE
    DATALAKE --> DATA
    DATA --> DATALAKE
    OMS --> DOM
    EXEC --> DOM
    ANALYTICS --> DOM
    CLI --> OP
```

## 4. DFD Level 2A — Brokers Module

```mermaid
graph TD
    subgraph external [External APIs]
        DHAN_API[Dhan REST + WebSocket]
        UPSTOX_API[Upstox REST + WebSocket]
        PAPER[Paper In-Memory]
    end

    subgraph brokers [Broker Subsystem]
        COMMON[Common Transport/Idempotency/Capabilities]
        DHAN_GW[DhanGateway]
        DHAN_CONN[DhanConnection]
        UPSTOX_GW[UpstoxGateway]
        UPSTOX_CONN[UpstoxConnection]
        PAPER_GW[PaperGateway]
    end

    DHAN_API --> DHAN_CONN
    UPSTOX_API --> UPSTOX_CONN
    PAPER --> PAPER_GW
    COMMON --> DHAN_CONN
    COMMON --> UPSTOX_CONN
    DHAN_CONN --> DHAN_GW
    UPSTOX_CONN --> UPSTOX_GW
    DHAN_GW --> RT[Runtime]
    UPSTOX_GW --> RT
    PAPER_GW --> RT
```

## 5. DFD Level 2B — OMS and Execution

```mermaid
graph TD
    subgraph external [External]
        STRAT[Strategies]
        BROKER[Broker Gateway]
        RISK_CFG[Risk Config]
    end

    subgraph oms [Application Layer]
        OM[OrderManager]
        PM[PositionManager]
        RM[RiskManager]
        EE[ExecutionEngine]
        TC[TradingCache]
        RECON[ReconciliationEngine]
    end

    STRAT -->|"OrderCommand via MessageBus"| EE
    EE --> RM
    RM -->|"approved"| EE
    EE -->|"submit"| BROKER
    BROKER -->|"fills/acks"| EE
    EE --> OM
    EE --> PM
    OM --> TC
    PM --> TC
    BROKER -->|"mass_status"| RECON
    RECON --> TC
    RISK_CFG --> RM
```

## 6. DFD Level 2C — Analytics Module

```mermaid
graph TD
    subgraph external [External]
        DATA[Historical/Live Data]
        OP[Operator]
    end

    subgraph analytics [Analytics]
        SE[StrategyEngine]
        BE[BacktestEngine]
        PE[PaperTradingEngine]
        SC[Scanner]
        PM[PortfolioModel]
        IE[IndicatorEngine]
    end

    DATA --> BE
    DATA --> PE
    DATA --> SE
    SC --> PM
    PM -->|"OrderCommand"| SE
    SE -->|"via MessageBus"| EXEC[ExecutionEngine]
    BE --> OP
    PE --> OP
    IE --> SC
```

## 7. DFD Level 2D — Datalake Module

See [07-data-infrastructure.md](07-data-infrastructure.md) §14 for full datalake DFD.

## 8. DFD Level 2E — Runtime Composition Root

```mermaid
graph TD
    subgraph external [External]
        CONFIG[YAML Config]
        EP[Entry Points]
    end

    subgraph runtime [Runtime]
        FACTORY[RuntimeFactory]
        REG[ComponentRegistry]
        LM[LifecycleManager]
        MB[MessageBus]
        DISC[PluginDiscovery]
        TARGET[ExecutionTargetResolver]
    end

    CONFIG --> FACTORY
    EP --> DISC
    DISC --> FACTORY
    FACTORY --> REG
    FACTORY --> LM
    FACTORY --> MB
    FACTORY --> TARGET
    REG --> LM
    LM -->|"start_all"| COMPONENTS[All Components]
```

## 9. Flow §1 — Startup

```
Operator invokes CLI or connect(broker_id)
  → Runtime resolves broker ONCE via entry-point group (BrokerId enum)
  → Composition root wires:
      MessageBus (single instance)
      TradingCache
      RiskEngine (RiskGate port bound)
      ExecutionEngine (FillSource per environment)
      IdempotencyGuard
      Clock (SystemClock or FakeClock)
  → Structural boot checks:
      Single ExecutionEngine wiring
      Clock injection present
      RiskGate port bound (no getattr reach-through)
  → Environment frozen: REPLAY / BACKTEST / PAPER / LIVE
```

### Expected Behavior Contract: Startup

| | |
|---|---|
| Inputs | Config file, broker_id, environment, credentials |
| Outputs | Running runtime with all components in RUNNING state |
| Timing | All initialize() before start(); broker connect before traffic |
| Failure modes | Missing RiskGate → abort; duplicate ExecutionEngine → abort; auth failure → abort |
| State transitions | All components: INITIALIZED → RUNNING; Environment frozen |

## 10. Flow §6 — Quote (Market Data)

```
Broker DataClient → DataEngine → TradingCache.set_quote(instrument_id, quote)
  → MessageBus.publish(QUOTE|TICK) → Strategy handler
```

**Invariant:** cache-then-publish.

### Expected Behavior Contract: Quote

| | |
|---|---|
| Inputs | Venue WS/REST payload → QuoteSnapshot |
| Outputs | Cache updated; QUOTE/TICK published once per accepted update |
| Timing | Timestamp = venue time if present, else Clock.now() |
| Failure modes | Parse failure → log + drop; duplicate seq → ignore; disconnect → BROKER_DISCONNECTED |

## 11. Flow §7 — Order

```
Orchestrator → place(intent, correlation_id) → IdempotencyGuard.check_and_reserve
  → RiskEngine.check_order
      denied  → MessageBus(RISK_REJECTED) — no venue call
      approved → ExecutionEngine → FillSource.submit → Venue
                 ack/reject → Cache upsert (Order FSM) → MessageBus(ORDER_PLACED|ORDER_REJECTED)
                 fill → record_trade (idempotent on trade_id)
                   → Cache FSM → MessageBus(TRADE_APPLIED)
                   → PositionManager.apply_trade → MessageBus(POSITION_*)
```

See [04-execution-and-oms.md](04-execution-and-oms.md) for full contract.

## 12. Flow §9 — Reconciliation

```
BrokerAdapter.mass_status → ExecutionEngine
  → ReconciliationEngine.compare(local, broker) → DriftItems
  → HIGH/MEDIUM drift: Cache upsert + RiskEngine capital refresh
  → MessageBus(RECONCILIATION_DRIFT) → MessageBus(RECONCILIATION_COMPLETED)
```

Triggers: connect/reconnect, periodic mass-status, UNKNOWN outcomes.

## 13. Flow §11 — Four-Mode Parity

| Mode | Data Source | FillSource | Clock |
|------|-------------|------------|-------|
| REPLAY | MessageLog / recorded session | Engine replay | FakeClock |
| BACKTEST | Datalake / Parquet / DuckDB | SimulatedFillSource | FakeClock |
| PAPER | Live DataProvider | PaperFillSource | SystemClock |
| LIVE | Live DataProvider | BrokerFillSource | SystemClock |

**Invariant I12:** Strategy, RiskEngine, ExecutionEngine (minus FillSource), FeaturePipeline, position projection, and event types are identical across all four modes. Environment frozen at boot. Parity gate never skipped in LIVE.

## 14. Flow — FeaturePipeline (Research Pipeline)

```mermaid
sequenceDiagram
    participant MD as MarketDataEngine
    participant FP as FeaturePipeline
    participant MB as MessageBus
    participant S as Strategy

    MD->>FP: Bar
    FP->>FP: compute features + indicators
    FP->>MB: publish(FeatureComputed)
    FP->>MB: publish(BarWithFeatures)
    MB->>S: on_bar (with features)
```

### Expected Behavior Contract: FeaturePipeline

| | |
|---|---|
| Inputs | Bar from MarketDataEngine |
| Outputs | FeatureComputed + enriched Bar on MessageBus |
| Timing | Completes before strategy.on_bar callback |
| Failure modes | Compute error → log + skip bar |

## 15. Flow — Order Placement (End-to-End Sequence)

```mermaid
sequenceDiagram
    participant Op as Operator
    participant CLI as CLI
    participant RT as Runtime
    participant MB as MessageBus
    participant EE as ExecutionEngine
    participant RG as RiskGate
    participant FS as FillSource
    participant BA as BrokerAdapter
    participant Venue as Venue

    Op->>CLI: submit order
    CLI->>RT: place(intent)
    RT->>MB: publish(OrderCommand)
    MB->>EE: on_order_command
    EE->>RG: check_order
    RG-->>EE: approved
    EE->>FS: submit
    FS->>BA: place_order
    BA->>Venue: REST/WS
    Venue-->>BA: ack
    BA-->>FS: OrderId
    FS-->>EE: result
    EE->>EE: Cache FSM update
    EE->>MB: publish(OrderPlaced)
    Venue-->>BA: fill
    BA-->>EE: OrderFilled
    EE->>MB: publish(OrderFilled)
    EE->>MB: publish(PositionUpdated)
    MB->>CLI: update
    CLI->>Op: confirmation
```

## 16. Flow — Market Data Ingestion

```mermaid
sequenceDiagram
    participant Venue as Venue WS
    participant BA as BrokerAdapter
    participant DE as DataEngine
    participant TC as TradingCache
    participant MB as MessageBus
    participant FP as FeaturePipeline

    Venue->>BA: WS message
    BA->>BA: WireMapper.to_quote
    BA->>DE: Quote
    DE->>TC: set_quote
    DE->>MB: publish(Quote)
    MB->>FP: on_quote
```

## 17. Flow — Replay Engine

```mermaid
sequenceDiagram
    participant RE as ReplayEngine
    participant LOG as MessageLog
    participant CL as FakeClock
    participant MB as MessageBus
    participant EE as ExecutionEngine
    participant TC as TradingCache

    RE->>LOG: read_session(session_id)
    loop each message
        RE->>CL: set(message.timestamp)
        RE->>MB: publish(message)
        MB->>EE: handlers (same as live)
        EE->>TC: state update
    end
    RE->>RE: compare snapshot to original
```

## 18. Flow — Analytics Research

```mermaid
sequenceDiagram
    participant Op as Operator
    participant CLI as CLI
    participant AN as AnalyticsEngine
    participant DL as Datalake
    participant SC as Scanner
    participant RP as ReportEngine

    Op->>CLI: scanner momentum
    CLI->>AN: run_scan(config)
    AN->>DL: fetch universe bars
    AN->>SC: scan(universe)
    SC-->>AN: list[Signal]
    AN->>RP: generate_report(signals)
    RP-->>CLI: ScanResult
    CLI->>Op: display
```

## 19. Flow — Reconciliation (Hot Path)

```mermaid
sequenceDiagram
    participant BA as BrokerAdapter
    participant EE as ExecutionEngine
    participant RE as ReconciliationEngine
    participant TC as TradingCache
    participant RM as RiskManager
    participant MB as MessageBus

    BA->>EE: mass_status
    EE->>RE: compare(local, broker)
    RE-->>EE: DriftItems
    loop each HIGH/MEDIUM
        EE->>TC: upsert (FSM-validated)
        EE->>RM: refresh_capital
    end
    EE->>MB: publish(ReconciliationCompleted)
```

## 20. Flow — Component Lifecycle

```mermaid
sequenceDiagram
    participant LM as LifecycleManager
    participant C as Component
    participant MB as MessageBus

    LM->>C: initialize(config)
    LM->>C: start()
    C->>MB: subscribe
    Note over C: RUNNING — process messages
    LM->>C: stop()
    C->>MB: unsubscribe
    LM->>C: reset()
```

## 21. Flow — Backtest Engine

```mermaid
sequenceDiagram
    participant BE as BacktestEngine
    participant CL as FakeClock
    participant DL as Datalake
    participant MB as MessageBus
    participant EE as ExecutionEngine
    participant S as Strategy

    BE->>DL: load bars
    loop each bar
        BE->>CL: advance
        BE->>MB: publish(Bar)
        MB->>S: on_bar
        S->>MB: publish(OrderCommand)
        MB->>EE: on_order_command
        EE->>MB: publish(OrderFilled)
        MB->>S: on_fill
    end
    BE->>BE: compute metrics
```

## 22. Broker API Scheduling and Cache Ownership

### Rate-Limit Call Path

1. Global QuotaScheduler — priority classes with max-wait deadlines
2. Per-broker MultiBucketRateLimiter — tokens from BrokerCapabilities

Both layers apply; callers must not bypass at transport boundary.

### Cache Ownership Summary

| Cache | Owner |
|-------|-------|
| Instrument master | Broker plugin + domain data catalog |
| Token persistence | Per-broker auth |
| Idempotency (orders) | Common broker infrastructure |
| Historical bars | Datalake |
| Quote snapshots | TradingCache via data engine |

## 23. DFD Coverage Summary

| Level | Scope | Document Section |
|-------|-------|------------------|
| 0 | System context | §2 |
| 1 | Major components | §3 |
| 2A | Brokers | §4 |
| 2B | OMS/Execution | §5 |
| 2C | Analytics | §6 |
| 2D | Datalake | §7 |
| 2E | Runtime | §8 |
| 3 | Cross-cutting flows | §9–21 |
