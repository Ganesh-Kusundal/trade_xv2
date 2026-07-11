# Architecture Diagrams — TradeXV2 Trading OS

## 1. High-Level Architecture

```mermaid
graph TB
    subgraph "Interface Layer"
        SDK["tradex SDK<br/>(Python)"]
        CLI["CLI<br/>(tradex cli)"]
        API["REST API<br/>(FastAPI)"]
        MCP["MCP Server<br/>(Unified)"]
        UI["Web UI<br/>(React/Vite)"]
        AGENT["AI Agent<br/>(LLM)"]
    end
    
    subgraph "Application Layer"
        OMS["OMS<br/>Order Management"]
        EXEC["Execution Service"]
        STREAM["Stream Orchestrator"]
        PORT["Portfolio Service"]
        TRADE["Trading Orchestrator"]
        DATA["Data Coordinator"]
    end
    
    subgraph "Domain Layer"
        INST["Instrument Context"]
        ORD["Order Context"]
        POS["Position Context"]
        ACCT["Account Context"]
        MD["Market Data Context"]
        ANL["Analytics Context"]
        DL["DataLake Context"]
        EVENTS["Domain Events"]
    end
    
    subgraph "Infrastructure Layer"
        EB["Event Bus"]
        DI["DI Container"]
        GW["Gateway Factory"]
        AUTH["Auth Manager"]
        RES["Resilience<br/>(Circuit Breaker, Retry)"]
        CACHE["Cache Layer"]
        OBS["Observability"]
    end
    
    subgraph "Broker Plugins"
        DHAN["Dhan Plugin"]
        UPSTOX["Upstox Plugin"]
        PAPER["Paper Plugin"]
        FUTURE["Future Plugin..."]
    end
    
    SDK --> OMS
    CLI --> OMS
    API --> OMS
    MCP --> DATA
    UI --> API
    AGENT --> MCP
    
    OMS --> ORD
    EXEC --> ORD
    STREAM --> MD
    PORT --> POS
    TRADE --> OMS
    TRADE --> STREAM
    DATA --> DL
    
    ORD --> EB
    MD --> EB
    POS --> EB
    
    EB --> EB
    DI --> EB
    
    EXEC --> GW
    STREAM --> GW
    DATA --> GW
    
    GW --> DHAN
    GW --> UPSTOX
    GW --> PAPER
    GW --> FUTURE
    
    DHAN --> AUTH
    UPSTOX --> AUTH
    DHAN --> RES
    UPSTOX --> RES
    
    OMS --> OBS
    EXEC --> OBS
```

## 2. Dependency Flow (Hexagonal Architecture)

```mermaid
graph LR
    subgraph "Domain (Innermost)"
        D1["Domain Entities"]
        D2["Domain Events"]
        D3["Port Interfaces"]
        D4["Value Objects"]
    end
    
    subgraph "Application"
        A1["Use Cases"]
        A2["Application Services"]
        A3["Domain Event Handlers"]
    end
    
    subgraph "Infrastructure (Outermost)"
        I1["Event Bus"]
        I2["Broker Gateways"]
        I3["Database"]
        I4["Cache"]
        I5["HTTP Client"]
        I6["WebSocket Client"]
    end
    
    subgraph "Interface"
        F1["REST API"]
        F2["CLI"]
        F3["MCP"]
        F4["SDK"]
    end
    
    D1 --> D3
    D2 --> D3
    D4 --> D1
    
    A1 --> D1
    A1 --> D2
    A1 --> D3
    A2 --> A1
    A3 --> D2
    A3 --> D3
    
    I1 --> D2
    I1 --> D3
    I2 --> D3
    I3 --> D3
    I4 --> D3
    I5 --> D3
    I6 --> D3
    
    F1 --> A1
    F1 --> A2
    F2 --> A1
    F2 --> A2
    F3 --> A2
    F4 --> A2
    
    style D1 fill:#e1f5fe
    style D2 fill:#e1f5fe
    style D3 fill:#e1f5fe
    style D4 fill:#e1f5fe
```

**Dependency Rule:** Arrows point inward only. Domain never imports Application, Infrastructure, or Interface.

## 3. Broker Plugin Architecture

```mermaid
graph TB
    subgraph "Broker Plugin System"
        REG["Plugin Registry<br/>(entry_points)"]
        
        subgraph "Dhan Plugin"
            DH_CORE["DhanBrokerPlugin"]
            DH_AUTH["DhanAuth"]
            DH_DATA["DhanDataProvider"]
            DH_EXEC["DhanExecutionProvider"]
            DH_STREAM["DhanStreamManager"]
        end
        
        subgraph "Upstox Plugin"
            UP_CORE["UpstoxBrokerPlugin"]
            UP_AUTH["UpstoxAuth"]
            UP_DATA["UpstoxDataProvider"]
            UP_EXEC["UpstoxExecutionProvider"]
            UP_STREAM["UpstoxStreamManager"]
        end
        
        subgraph "Paper Plugin"
            PA_CORE["PaperBrokerPlugin"]
            PA_DATA["PaperDataProvider"]
            PA_EXEC["PaperExecutionProvider"]
        end
    end
    
    subgraph "Common Contracts"
        BA["BrokerAdapter Protocol"]
        DP["DataProvider Protocol"]
        EP["ExecutionProvider Protocol"]
        LIFECYCLE["Lifecycle Hooks"]
    end
    
    REG --> DH_CORE
    REG --> UP_CORE
    REG --> PA_CORE
    
    DH_CORE --> BA
    DH_DATA --> DP
    DH_EXEC --> EP
    DH_CORE --> LIFECYCLE
    
    UP_CORE --> BA
    UP_DATA --> DP
    UP_EXEC --> EP
    UP_CORE --> LIFECYCLE
    
    PA_CORE --> BA
    PA_DATA --> DP
    PA_EXEC --> EP
    PA_CORE --> LIFECYCLE
```

## 4. Event Flow Architecture

```mermaid
graph TB
    subgraph "Event Producers"
        P1["Instrument Context"]
        P2["Order Context"]
        P3["Position Context"]
        P4["Market Data Context"]
        P5["Execution Context"]
        P6["Analytics Context"]
    end
    
    subgraph "Event Bus"
        EB["EventBus<br/>(pub/sub + dedup)"]
        DLQ["Dead Letter Queue"]
        LOG["Event Log"]
        ALERT["Alerting Engine"]
    end
    
    subgraph "Event Consumers"
        C1["OMS Service"]
        C2["Portfolio Service"]
        C3["Streaming Service"]
        C4["Analytics Service"]
        C5["Replay Engine"]
        C6["Observability"]
    end
    
    P1 -->|"InstrumentLoaded"| EB
    P2 -->|"OrderFilled"| EB
    P3 -->|"PositionClosed"| EB
    P4 -->|"QuoteUpdated"| EB
    P5 -->|"FillReceived"| EB
    P6 -->|"SignalGenerated"| EB
    
    EB --> C1
    EB --> C2
    EB --> C3
    EB --> C4
    EB --> C5
    EB --> C6
    
    EB -->|"failed events"| DLQ
    EB -->|"all events"| LOG
    EB -->|"capital events"| ALERT
```

## 5. Startup Flow

```mermaid
sequenceDiagram
    participant User as User/CLI
    participant SDK as tradex SDK
    participant DI as DI Container
    participant CFG as Configuration
    participant GW as Gateway Factory
    participant BRK as Broker Plugin
    participant AUTH as Auth Manager
    participant EB as Event Bus
    
    User->>SDK: tradex.connect("dhan")
    SDK->>DI: Initialize container
    DI->>CFG: Load config from .env
    CFG-->>DI: Config validated
    
    SDK->>GW: bootstrap_gateway("dhan")
    GW->>BRK: discover plugin
    BRK-->>GW: BrokerPlugin instance
    
    GW->>BRK: create_adapter()
    BRK->>BRK: Initialize transport
    BRK-->>GW: BrokerAdapter
    
    GW->>AUTH: structural_readiness_probe()
    AUTH-->>GW: Token present?
    
    alt Token valid
        GW->>AUTH: authenticated_readiness_probe()
        AUTH->>BRK: Read-only API call
        BRK-->>AUTH: Probe result
        AUTH-->>GW: Probe passed
        GW-->>SDK: BootstrapResult(READY)
    else Token expired
        GW->>AUTH: Force refresh token
        AUTH->>BRK: Refresh token
        BRK-->>AUTH: New token
        GW->>AUTH: Re-probe
        AUTH-->>GW: Probe passed
        GW-->>SDK: BootstrapResult(READY)
    else Auth failed
        GW-->>SDK: BootstrapResult(REAUTH_REQUIRED)
    end
    
    SDK->>EB: Initialize event bus
    SDK-->>User: Session ready
```

## 6. Order Lifecycle Flow

```mermaid
sequenceDiagram
    participant Strategy as Strategy
    participant SDK as tradex SDK
    participant OMS as OMS
    participant VALID as Order Validator
    participant EXEC as Execution Service
    participant BROK as Broker Adapter
    participant POS as Position Manager
    participant EB as Event Bus
    
    Strategy->>SDK: session.buy(instrument, qty, price)
    SDK->>OMS: OrderIntent
    
    OMS->>OMS: Generate OrderRequest
    OMS->>VALID: Validate order
    VALID-->>OMS: Validation passed
    
    OMS->>EB: Publish OrderRequested
    OMS->>EXEC: Submit OrderRequest
    
    EXEC->>EXEC: Generate idempotency key
    EXEC->>EXEC: Check circuit breaker
    EXEC->>BROK: place_order(request)
    
    alt Order accepted
        BROK-->>EXEC: OrderResponse(ACCEPTED)
        EXEC->>EB: Publish OrderSubmitted
        EXEC-->>OMS: Success
        
        BROK-->>EB: FillNotification (WebSocket)
        EB->>OMS: FillReceived event
        OMS->>POS: Apply fill to position
        POS-->>EB: PositionUpdated
        OMS->>EB: Publish OrderFilled
    else Order rejected
        BROK-->>EXEC: OrderResponse(REJECTED)
        EXEC->>EB: Publish ExecutionError
        EXEC-->>OMS: Error
        OMS->>EB: Publish OrderRejected
    else Network error
        BROK-->>EXEC: Exception
        EXEC->>EXEC: Retry with backoff
        EXEC->>BROK: Retry place_order
    end
```

## 7. Package Dependency Rules

```mermaid
graph TB
    subgraph "ALLOWED dependencies"
        A1["tradex"] --> A2["application"]
        A1 --> A3["domain"]
        A2 --> A3
        A4["infrastructure"] --> A3
        A5["brokers"] --> A3
        A5 --> A4
        A6["analytics"] --> A3
        A7["datalake"] --> A3
        A8["interface"] --> A2
        A8 --> A3
        A9["config"] --> A3
    end
    
    subgraph "FORBIDDEN dependencies"
        F1["domain"] -.-x A2
        F1 -.-x A4
        F1 -.-x A5
        F1 -.-x A6
        F1 -.-x A7
        F1 -.-x A8
        A2 -.-x A5
        A2 -.-x A4
        A6 -.-x A5
        A7 -.-x A5
    end
    
    style F1 fill:#ffebee
```

**Import Linter Rules:**
1. `domain` never imports `application`, `infrastructure`, `brokers`, `analytics`, `datalake`, `interface`, `tradex`
2. `application` never imports `infrastructure`, `brokers`
3. `analytics` never imports `brokers`
4. `datalake` never imports `brokers`
5. `brokers` never imports `application`, `tradex`
6. All cross-context communication goes through ports and events

## 8. CI Pipeline Architecture

```mermaid
graph LR
    subgraph "Pre-commit (Local)"
        PC1["ruff lint"]
        PC2["ruff format"]
        PC3["mypy (strict subset)"]
        PC4["Architecture tests"]
        PC5["Exception hierarchy check"]
    end
    
    subgraph "CI Pipeline"
        CI1["Lint & Format"]
        CI2["Type Check"]
        CI3["Unit Tests"]
        CI4["Integration Tests"]
        CI5["Architecture Tests"]
        CI6["E2E Tests"]
        CI7["Chaos Tests"]
        CI8["Performance Tests"]
    end
    
    subgraph "Quality Gates"
        G1["Coverage ≥ 85%"]
        G2["No arch violations"]
        G3["No import cycles"]
        G4["All tests pass"]
    end
    
    PC1 --> CI1
    PC3 --> CI2
    CI1 --> CI3
    CI2 --> CI3
    CI3 --> CI4
    CI3 --> CI5
    CI4 --> CI6
    CI4 --> CI7
    CI6 --> CI8
    
    CI3 --> G1
    CI5 --> G2
    CI5 --> G3
    CI6 --> G4
    CI7 --> G4
```
