# TradeXV2 — Complete Architecture Documentation

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Layers](#architecture-layers)
3. [Component Diagrams](#component-diagrams)
4. [Data Flow Diagrams](#data-flow-diagrams)
5. [Core Domain Types](#core-domain-types)
6. [Broker Adapter Architecture](#broker-adapter-architecture)
7. [Order Management System (OMS)](#order-management-system-oms)
8. [Resilience Patterns](#resilience-patterns)
9. [CLI/TUI Architecture](#clitui-architecture)
10. [Analytics & Backtesting](#analytics--backtesting)
11. [Data Lake Architecture](#data-lake-architecture)
12. [Infrastructure Components](#infrastructure-components)
13. [Feature Matrix](#feature-matrix)

---

## System Overview

TradeXV2 is a Python-based, broker-agnostic algorithmic trading framework for Indian exchanges (NSE, BSE, MCX). It supports DhanHQ and Upstox broker adapters with a complete OMS, event bus, risk management, portfolio, strategy, backtesting, and replay stack.

### Key Design Principles

- **Single Source of Truth**: All domain types live in `domain/` package
- **Import Direction Rules**: Strict layer boundaries enforced by import-linter
- **OMS-First Execution**: All orders flow through OrderManager for risk checks
- **Thread Safety**: RLock-protected state mutations throughout
- **Lifecycle Management**: All background services owned by LifecycleManager

---

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLI / TUI Layer                             │
│  cli/commands/*  │  cli/views/tui_app.py  │  cli/widgets/*          │
├─────────────────────────────────────────────────────────────────────┤
│                      Application Layer                              │
│  application/execution/*  │  application/oms/*  │  application/composer/* │
├─────────────────────────────────────────────────────────────────────┤
│                      Domain Layer                                   │
│  domain/entities.py  │  domain/types.py  │  domain/ports/*         │
├─────────────────────────────────────────────────────────────────────┤
│                   Broker Infrastructure Layer                       │
│  brokers/common/*  │  brokers/dhan/*  │  brokers/upstox/*          │
├─────────────────────────────────────────────────────────────────────┤
│                    Infrastructure Layer                             │
│  infrastructure/lifecycle/*  │  infrastructure/event_bus/*         │
├─────────────────────────────────────────────────────────────────────┤
│                    Analytics Layer                                  │
│  analytics/backtest/*  │  analytics/scanner/*  │  analytics/replay/* │
├─────────────────────────────────────────────────────────────────────┤
│                    Data Lake Layer                                   │
│  datalake/store/*  │  datalake/gateway.py  │  datalake/loader.py   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Component Diagrams

### High-Level Component Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          CLI / TUI                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│  │  commands/   │  │   views/    │  │  widgets/   │                  │
│  │  broker.py   │  │  tui_app.py │  │ market_    │                  │
│  │  orders.py   │  │  tui.tcss   │  │ console.py │                  │
│  │  portfolio.py│  │             │  │ oms_       │                  │
│  └──────┬──────┘  └──────┬──────┘  │ console.py │                  │
│         │                │          └──────┬─────┘                  │
│         └────────────────┼─────────────────┘                        │
│                          ▼                                          │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              BrokerService (cli/services/)                    │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │   │
│  │  │ broker_     │  │  oms_       │  │ observability│         │   │
│  │  │ service.py  │  │  service.py │  │ _setup.py   │          │   │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘          │   │
│  └─────────┼────────────────┼────────────────┼──────────────────┘   │
│            │                │                │                       │
└────────────┼────────────────┼────────────────┼──────────────────────┘
             │                │                │
             ▼                ▼                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Application Layer                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │
│  │   execution/     │  │      oms/       │  │   composer/     │     │
│  │ execution_      │  │ order_manager.py│  │   (future)      │     │
│  │ service.py      │  │ risk_manager.py │  │                 │     │
│  │ gateway_submit.py│  │ context.py     │  │                 │     │
│  │ factory.py      │  │ oms_gateway_   │  │                 │     │
│  └────────┬────────┘  │ proxy.py       │  └────────┬────────┘     │
│           │           └────────┬────────┘           │              │
│           └────────────────────┼────────────────────┘              │
└────────────────────────────────┼────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Domain Layer                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    domain/                                    │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │    │
│  │  │entities.py│ │ types.py │ │ requests.py│ │ market.py │      │    │
│  │  │ Order    │ │ Side     │ │ OrderReq  │ │ Quote    │       │    │
│  │  │ Position │ │ OrderType│ │ SliceReq  │ │ Depth    │       │    │
│  │  │ Trade    │ │ Product  │ │ OrderPrev │ │ Instrument│      │    │
│  │  │ Holding  │ │ Exchange │ │           │ │          │       │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │    │
│  │  │account.py│ │alerts.py │ │derivatives│ │ports/    │       │    │
│  │  │ Balance  │ │ Alert    │ │OptionChain│ │broker_   │       │    │
│  │  │ FundLimit│ │ PnlExit  │ │FutureChain│ │gateway.py│       │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                 Broker Infrastructure Layer                          │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    brokers/common/                            │    │
│  │  ┌─────────────────┐  ┌─────────────────┐                   │    │
│  │  │   resilience/    │  │     oms/        │                   │    │
│  │  │ circuit_breaker  │  │ order_manager   │                   │    │
│  │  │ rate_limiter     │  │ _internal/      │                   │    │
│  │  │ retry.py         │  │ risk_manager    │                   │    │
│  │  │ retry_async.py   │  │ position_mgr    │                   │    │
│  │  │ backoff.py       │  │ daily_pnl_reset │                   │    │
│  │  └─────────────────┘  └─────────────────┘                   │    │
│  │  ┌─────────────────┐  ┌─────────────────┐                   │    │
│  │  │  gateway/        │  │  observability/  │                  │    │
│  │  │ MarketDataGateway│  │ event_metrics   │                   │    │
│  │  │ gateway_interfaces│ │ http_server     │                   │    │
│  │  └─────────────────┘  └─────────────────┘                   │    │
│  │  ┌─────────────────┐  ┌─────────────────┐                   │    │
│  │  │    auth/         │  │  connection/     │                  │    │
│  │  │ token_refresh   │  │ connection_pool  │                   │    │
│  │  │ totp_client     │  │ bootstrap.py     │                   │    │
│  │  └─────────────────┘  └─────────────────┘                   │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │
│  │    dhan/         │  │   upstox/        │  │    paper/       │     │
│  │ DhanBroker       │  │ UpstoxBroker     │  │ PaperGateway    │     │
│  │ DhanMarketFeed   │  │ market_data/     │  │ MockBroker      │     │
│  │ DhanOrderStream  │  │ orders/          │  │                 │     │
│  │ PollingMarketFeed│  │ portfolio/       │  │                 │     │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘     │
└──────────────────────────────────────────────────────────────────────┘
```

### Intelligent Gateway Routing

```
┌──────────────────────────────────────────────────────────────────────┐
│                    IntelligentGateway                                │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Routing Strategy                          │    │
│  │  ┌─────────────────┐  ┌─────────────────┐                   │    │
│  │  │  Upstox Primary  │  │   Dhan Primary   │                  │    │
│  │  │  - ltp()         │  │  - history()     │                  │    │
│  │  │  - ltp_batch()   │  │  - depth()       │                  │    │
│  │  │  - quote()       │  │  - option_chain()│                  │    │
│  │  │  - quote_batch() │  │  - future_chain()│                  │    │
│  │  └─────────────────┘  └─────────────────┘                   │    │
│  │                                                              │    │
│  │  ┌─────────────────────────────────────────────────────┐    │    │
│  │  │              Fallback & Degraded Mode                │    │    │
│  │  │  - Health-aware routing via BrokerHealthMonitor      │    │    │
│  │  │  - TTL-based cache for read operations               │    │    │
│  │  │  - Write operations raise BrokerDegradedError        │    │    │
│  │  └─────────────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐                           │
│  │   Dhan Gateway   │  │  Upstox Gateway  │                          │
│  │  (REST + WS)     │  │  (REST + WS)     │                         │
│  └─────────────────┘  └─────────────────┘                           │
└──────────────────────────────────────────────────────────────────────┘
```

### OMS Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Order Management System                           │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                  ExecutionService                            │    │
│  │  ┌─────────────────────────────────────────────────────┐    │    │
│  │  │                  place_order()                       │    │    │
│  │  │  ┌─────────────────────────────────────────────┐    │    │    │
│  │  │  │           OrderManager                       │    │    │    │
│  │  │  │  ┌─────────────────────────────────────┐    │    │    │    │
│  │  │  │  │        Idempotency Check             │    │    │    │    │
│  │  │  │  │  - Check correlation_id              │    │    │    │    │
│  │  │  │  │  - Check pending_correlation set     │    │    │    │    │
│  │  │  │  └─────────────────────────────────────┘    │    │    │    │
│  │  │  │  ┌─────────────────────────────────────┐    │    │    │    │
│  │  │  │  │          Risk Check                   │    │    │    │    │
│  │  │  │  │  - RiskManager.check_order()         │    │    │    │    │
│  │  │  │  │  - kill_switch                        │    │    │    │    │
│  │  │  │  │  - position_pct                       │    │    │    │    │
│  │  │  │  │  - gross_exposure_pct                 │    │    │    │    │
│  │  │  │  │  - daily_loss_pct                     │    │    │    │    │
│  │  │  │  └─────────────────────────────────────┘    │    │    │    │
│  │  │  │  ┌─────────────────────────────────────┐    │    │    │    │
│  │  │  │  │        Broker Transport              │    │    │    │    │
│  │  │  │  │  - submit_fn(request)                │    │    │    │    │
│  │  │  │  │  - transport_only=True               │    │    │    │    │
│  │  │  │  └─────────────────────────────────────┘    │    │    │    │
│  │  │  │  ┌─────────────────────────────────────┐    │    │    │    │
│  │  │  │  │        Event Publishing              │    │    │    │    │
│  │  │  │  │  - ORDER_PLACED                      │    │    │    │    │
│  │  │  │  │  - RISK_APPROVED                     │    │    │    │    │
│  │  │  │  │  - RISK_REJECTED                     │    │    │    │    │
│  │  │  │  └─────────────────────────────────────┘    │    │    │    │
│  │  │  └─────────────────────────────────────────────┘    │    │    │
│  │  └─────────────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │
│  │ OrderStateValidator│ │ OrderAuditLogger │ │OrderPositionUpdater│   │
│  │ - validate_     │  │ - log_new_order  │ │ - apply_trade   │     │
│  │   transition()  │  │ - log_state_     │ │ - update_       │     │
│  │                 │  │   change()       │ │   position()    │     │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Diagrams

### Order Placement Flow

```
┌─────────┐    ┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│   CLI   │───▶│BrokerService│───▶│ExecutionService│──▶│OrderManager │
└─────────┘    └─────────────┘    └──────────────┘    └──────┬──────┘
                                                              │
                                                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Order Processing Pipeline                          │
│                                                                      │
│  1. Idempotency Check                                               │
│     ├─ Check correlation_id in _orders_by_correlation               │
│     └─ Check correlation_id in _pending_correlation                 │
│                                                                      │
│  2. Build Order Object                                              │
│     ├─ Create Order dataclass with status=OPEN                     │
│     └─ Assign correlation_id                                       │
│                                                                      │
│  3. Risk Check (RiskManager)                                        │
│     ├─ kill_switch_active? → BLOCK                                  │
│     ├─ position_pct exceeded? → BLOCK                              │
│     ├─ gross_exposure_pct exceeded? → BLOCK                        │
│     └─ daily_loss_pct exceeded? → BLOCK                            │
│                                                                      │
│  4. Broker Transport (submit_fn)                                    │
│     ├─ transport_only=True (skip duplicate risk checks)            │
│     ├─ HTTP REST call to broker API                                │
│     └─ Return OrderResponse                                         │
│                                                                      │
│  5. Record Result                                                   │
│     ├─ Update _orders dict                                         │
│     ├─ Update _orders_by_correlation dict                          │
│     └─ Publish ORDER_PLACED event                                  │
└──────────────────────────────────────────────────────────────────────┘
```

### Market Data Flow

```
┌─────────┐    ┌─────────────┐    ┌──────────────────┐    ┌─────────────┐
│  TUI    │───▶│IntelligentGateway│──▶│   Broker Gateway  │──▶│  Exchange   │
│  Widget │    │  (Routing)   │    │ (Dhan/Upstox)    │    │   API      │
└─────────┘    └──────────────┘    └──────────────────┘    └─────────────┘
                     │
                     ├─ ltp()/quote() → Upstox Primary
                     ├─ history() → Dhan Primary
                     ├─ depth() → Dhan Primary
                     ├─ option_chain() → Dhan Primary
                     └─ future_chain() → Dhan Primary
                     │
                     ▼
            ┌──────────────────┐
            │  BrokerHealth    │
            │  Monitor         │
            │  - is_healthy()  │
            │  - record_       │
            │    success()     │
            │  - record_       │
            │    failure()     │
            └──────────────────┘
```

### Event Bus Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Event Bus Architecture                             │
│                                                                      │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐│
│  │   Publisher      │     │   EventBus      │     │   Subscriber    ││
│  │   (OrderManager) │────▶│                 │────▶│   (PositionMgr) ││
│  └─────────────────┘     │  - publish()    │     └─────────────────┘│
│                          │  - subscribe()  │                         │
│  ┌─────────────────┐     │  - _lock (RLock)│     ┌─────────────────┐│
│  │   Publisher      │────▶│                 │────▶│   Subscriber    ││
│  │   (Broker Feed)  │     └─────────────────┘     │   (AuditLogger) ││
│  └─────────────────┘                              └─────────────────┘│
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    DomainEvent                                │    │
│  │  - event_type: str                                          │    │
│  │  - payload: dict                                           │    │
│  │  - symbol: str                                             │    │
│  │  - source: str                                             │    │
│  │  - correlation_id: str | None                              │    │
│  │  - timestamp: datetime                                     │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    EventType Enum                            │    │
│  │  - ORDER_PLACED, ORDER_UPDATED, ORDER_CANCELLED            │    │
│  │  - RISK_APPROVED, RISK_REJECTED                             │    │
│  │  - TRADE, TRADE_APPLIED                                     │    │
│  │  - POSITION_UPDATED                                         │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### Resilience Pattern Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Resilience Pipeline                                │
│                                                                      │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐              │
│  │ Rate Limiter │───▶│   Circuit   │───▶│   Retry     │              │
│  │ (TokenBucket)│    │   Breaker   │    │  Executor   │              │
│  └─────────────┘    └─────────────┘    └─────────────┘              │
│        │                    │                    │                   │
│        ▼                    ▼                    ▼                   │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐              │
│  │  Acquire    │    │ Allow       │    │  Execute    │              │
│  │  tokens     │    │ request?    │    │  with retry │              │
│  └─────────────┘    └─────────────┘    └─────────────┘              │
│        │                    │                    │                   │
│        ▼                    ▼                    ▼                   │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐              │
│  │  Block if   │    │  State:     │    │ Exponential │              │
│  │  no tokens  │    │ CLOSED/     │    │ Backoff     │              │
│  │             │    │ OPEN/       │    │             │              │
│  │             │    │ HALF_OPEN   │    │             │              │
│  └─────────────┘    └─────────────┘    └─────────────┘              │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Core Domain Types

### Entity Hierarchy

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Domain Entities (domain/)                          │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    orders.py                                 │    │
│  │  Order, OrderResponse, Trade, FieldMapping                   │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    positions.py                              │    │
│  │  Position, Holding                                           │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    account.py                                │    │
│  │  Balance, FundLimits                                         │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    market.py                                 │    │
│  │  Quote, MarketDepth, DepthLevel, Instrument                  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    derivatives.py                            │    │
│  │  OptionContract, OptionLeg, OptionStrike, OptionChain       │    │
│  │  FutureContract, FutureChain                                 │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    alerts.py                                 │    │
│  │  ConditionalAlert, ConditionalAlertRequest                  │    │
│  │  MarketIntelligenceSnapshot, PnlExitPolicy, PnlExitResult  │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### Type Definitions

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Domain Types (domain/types.py)                     │
│                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │
│  │     Side         │  │   OrderType     │  │   ProductType   │     │
│  │  - BUY           │  │  - MARKET       │  │  - INTRADAY     │     │
│  │  - SELL          │  │  - LIMIT        │  │  - DELIVERY     │     │
│  └─────────────────┘  │  - SL           │  │  - MARGIN       │     │
│                        │  - SL-M         │  └─────────────────┘     │
│  ┌─────────────────┐  └─────────────────┘                           │
│  │  OrderStatus    │                                                │
│  │  - OPEN          │  ┌─────────────────┐  ┌─────────────────┐     │
│  │  - PENDING       │  │   Validity      │  │ ExchangeSegment │     │
│  │  - EXECUTED      │  │  - DAY          │  │  - NSE          │     │
│  │  - CANCELLED     │  │  - IOC          │  │  - BSE          │     │
│  │  - REJECTED      │  │  - GTD          │  │  - NFO          │     │
│  │  - TRIGGERED     │  │  - GTC          │  │  - MCX          │     │
│  └─────────────────┘  │  - GTT          │  │  - CDS          │     │
│                        └─────────────────┘  │  - INDEX        │     │
│  ┌─────────────────┐                        └─────────────────┘     │
│  │ InstrumentType  │                                                │
│  │  - EQ            │  ┌─────────────────┐                          │
│  │  - FUT           │  │ ConnectionStatus│                          │
│  │  - OPT           │  │  - CONNECTED    │                          │
│  │  - COM           │  │  - DISCONNECTED │                          │
│  │  - CUR           │  │  - RECONNECTING │                          │
│  └─────────────────┘  └─────────────────┘                          │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Broker Adapter Architecture

### Dhan Adapter Structure

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Dhan Broker Adapter (brokers/dhan/)                │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Gateway Layer                             │    │
│  │  ┌─────────────────┐  ┌─────────────────┐                   │    │
│  │  │  gateway.py      │  │  connection.py   │                  │    │
│  │  │  DhanGateway     │  │  DhanConnection  │                  │    │
│  │  │  (MarketData-   │  │  (Auth, HTTP,    │                  │    │
│  │  │   Gateway ABC)   │  │   WebSocket)     │                  │    │
│  │  └─────────────────┘  └─────────────────┘                   │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Service Layer                             │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │    │
│  │  │ market_data  │  │   orders    │  │ portfolio   │         │    │
│  │  │ .py         │  │   .py       │  │ .py         │         │    │
│  │  │ ltp()       │  │ place_order │  │ positions() │         │    │
│  │  │ quote()     │  │ cancel_order│  │ holdings()  │         │    │
│  │  │ history()   │  │ get_order   │  │ funds()     │         │    │
│  │  │ depth()     │  │ book()      │  │ trades()    │         │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │    │
│  │                                                              │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │    │
│  │  │  options    │  │   futures   │  │ historical  │         │    │
│  │  │  .py        │  │   .py       │  │ .py         │         │    │
│  │  │ option_    │  │ future_     │  │ history()   │         │    │
│  │  │ chain()    │  │ chain()     │  │ candles()   │         │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    WebSocket Services                        │    │
│  │  ┌─────────────────┐  ┌─────────────────┐                   │    │
│  │  │ DhanMarketFeed   │  │ DhanOrderStream  │                  │    │
│  │  │ - subscribe()    │  │ - subscribe()    │                  │    │
│  │  │ - on_tick()      │  │ - on_order()     │                  │    │
│  │  └─────────────────┘  └─────────────────┘                   │    │
│  │                                                              │    │
│  │  ┌─────────────────┐  ┌─────────────────┐                   │    │
│  │  │ PollingMarket-  │  │ TokenRefresh-   │                   │    │
│  │  │ Feed (fallback) │  │ Scheduler       │                   │    │
│  │  └─────────────────┘  └─────────────────┘                   │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Support Layer                              │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │    │
│  │  │ http_client  │  │ token_      │  │ totp_client │         │    │
│  │  │ .py          │  │ manager.py  │  │ .py         │         │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │    │
│  │                                                              │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │    │
│  │  │ segments    │  │ resolver.py │  │ settings.py │         │    │
│  │  │ .py         │  │             │  │             │         │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### Upstox Adapter Structure

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Upstox Broker Adapter (brokers/upstox/)            │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Gateway Layer                             │    │
│  │  ┌─────────────────┐  ┌─────────────────┐                   │    │
│  │  │  gateway.py      │  │  broker.py       │                  │    │
│  │  │  UpstoxGateway   │  │  UpstoxBroker    │                  │    │
│  │  │  (MarketData-   │  │  (Capability-    │                  │    │
│  │  │   Gateway ABC)   │  │   based)         │                  │    │
│  │  └─────────────────┘  └─────────────────┘                   │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Capability Modules                        │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │    │
│  │  │ capabilities/│  │ market_data/ │  │ orders/     │         │    │
│  │  │ - market_    │  │ - v2/        │  │ - place     │         │    │
│  │  │   data       │  │ - v3/        │  │ - modify    │         │    │
│  │  │ - orders     │  │ - websocket/ │  │ - cancel    │         │    │
│  │  │ - portfolio  │  │              │  │ - gtts      │         │    │
│  │  │ - kill_switch│  └─────────────┘  └─────────────┘         │    │
│  │  │ - alerts     │                                           │    │
│  │  │ - margin     │  ┌─────────────┐  ┌─────────────┐         │    │
│  │  │ - gtts       │  │ portfolio/  │  │ kill_switch/ │        │    │
│  │  │ - news       │  │ - holdings  │  │ - get_status │        │    │
│  │  └─────────────┘  │ - positions │  │ - set_status │        │    │
│  │                    │ - funds     │  └─────────────┘         │    │
│  │                    └─────────────┘                           │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Support Layer                              │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │    │
│  │  │ auth/        │  │ config/      │  │ instruments/ │        │    │
│  │  │ - oauth2     │  │ - settings   │  │ - loader     │        │    │
│  │  │ - token      │  │              │  │              │        │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Order Management System (OMS)

### OMS Component Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                    OMS Components                                     │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    application/oms/                          │    │
│  │                                                              │    │
│  │  ┌─────────────────────────────────────────────────────┐    │    │
│  │  │                    OrderManager                       │    │    │
│  │  │  - place_order()      │ - cancel_order()             │    │    │
│  │  │  - upsert_order()     │ - record_trade()             │    │    │
│  │  │  - on_order_update()  │ - on_trade()                 │    │    │
│  │  │                                                              │    │
│  │  │  Internal State:                                         │    │
│  │  │  - _orders: dict[str, Order]                             │    │    │
│  │  │  - _orders_by_correlation: dict[str, Order]              │    │    │
│  │  │  - _pending_correlation: set[str]                        │    │    │
│  │  │  - _lock: threading.RLock                                │    │    │
│  │  └─────────────────────────────────────────────────────┘    │    │
│  │                                                              │    │
│  │  ┌─────────────────────────────────────────────────────┐    │    │
│  │  │                    RiskManager                       │    │    │
│  │  │  - check_order(order) → RiskResult                   │    │    │
│  │  │  - kill_switch_active: bool                          │    │    │
│  │  │  - daily_pnl: Decimal                                │    │    │
│  │  │  - capital_fn: Callable → Decimal                    │    │    │
│  │  │  - _lock: threading.RLock                            │    │    │
│  │  │                                                              │    │
│  │  │  Risk Gates:                                               │    │    │
│  │  │  - kill_switch → BLOCK                                    │    │    │
│  │  │  - position_pct → BLOCK                                   │    │    │
│  │  │  - gross_exposure_pct → BLOCK                             │    │    │
│  │  │  - daily_loss_pct → BLOCK                                 │    │    │
│  │  └─────────────────────────────────────────────────────┘    │    │
│  │                                                              │    │
│  │  ┌─────────────────────────────────────────────────────┐    │    │
│  │  │                    PositionManager                   │    │    │
│  │  │  - get_position(symbol) → Position                   │    │    │
│  │  │  - apply_trade(trade) → None                         │    │    │
│  │  │  - _positions: dict[str, Position]                   │    │    │
│  │  │  - _lock: threading.RLock                            │    │    │
│  │  └─────────────────────────────────────────────────────┘    │    │
│  │                                                              │    │
│  │  ┌─────────────────────────────────────────────────────┐    │    │
│  │  │                    TradingContext                     │    │    │
│  │  │  - order_manager: OrderManager                       │    │    │
│  │  │  - position_manager: PositionManager                 │    │    │
│  │  │  - risk_manager: RiskManager                         │    │    │
│  │  │  - start_reconciliation()                            │    │    │
│  │  │  - stop_reconciliation()                             │    │    │
│  │  └─────────────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Internal Collaborators (application/oms/_internal/)│ │
│  │                                                              │    │
│  │  ┌─────────────────┐  ┌─────────────────┐                   │    │
│  │  │ OrderStateValidator│ │ OrderAuditLogger │                  │    │
│  │  │ - validate_     │  │ - log_new_order  │                  │    │
│  │  │   transition()  │  │ - log_state_     │                  │    │
│  │  │                 │  │   change()       │                  │    │
│  │  └─────────────────┘  └─────────────────┘                   │    │
│  │                                                              │    │
│  │  ┌─────────────────┐  ┌─────────────────┐                   │    │
│  │  │OrderPositionUpdater│ │  RiskManager    │                  │    │
│  │  │ - apply_trade   │  │ - check_order   │                  │    │
│  │  │ - update_avg_   │  │ - update_daily_ │                  │    │
│  │  │   price()       │  │   pnl()         │                  │    │
│  │  └─────────────────┘  └─────────────────┘                   │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### OMS Gateway Proxy

```
┌──────────────────────────────────────────────────────────────────────┐
│                    OMS Gateway Proxy (B4)                             │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    OMSGatewayProxy                           │    │
│  │                                                              │    │
│  │  Purpose: Enforce kill switch on ALL order operations       │    │
│  │                                                              │    │
│  │  ┌─────────────────────────────────────────────────────┐    │    │
│  │  │  Market Data Operations (Pass-through)               │    │    │
│  │  │  - ltp()        → gateway.ltp()                     │    │    │
│  │  │  - quote()      → gateway.quote()                   │    │    │
│  │  │  - history()    → gateway.history()                 │    │    │
│  │  │  - depth()      → gateway.depth()                   │    │    │
│  │  │  - option_chain() → gateway.option_chain()          │    │    │
│  │  └─────────────────────────────────────────────────────┘    │    │
│  │                                                              │    │
│  │  ┌─────────────────────────────────────────────────────┐    │    │
│  │  │  Order Operations (Risk-Enforced)                    │    │    │
│  │  │  - place_order() → risk_manager.check_order()       │    │    │
│  │  │                   → gateway.place_order()           │    │    │
│  │  │  - cancel_order() → risk_manager.check_cancel()     │    │    │
│  │  │                    → gateway.cancel_order()         │    │    │
│  │  │  - modify_order() → risk_manager.check_modify()     │    │    │
│  │  │                    → gateway.modify_order()         │    │    │
│  │  └─────────────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Resilience Patterns

### Circuit Breaker States

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Circuit Breaker State Machine                      │
│                                                                      │
│                         ┌─────────────────┐                         │
│                         │     CLOSED      │                         │
│                         │  (Normal Ops)   │                         │
│                         └────────┬────────┘                         │
│                                  │                                   │
│                    failure_count >= threshold                        │
│                                  │                                   │
│                                  ▼                                   │
│                         ┌─────────────────┐                         │
│                         │      OPEN       │                         │
│                         │  (Fast Fail)    │                         │
│                         └────────┬────────┘                         │
│                                  │                                   │
│                    open_duration_ms elapsed                          │
│                                  │                                   │
│                                  ▼                                   │
│                         ┌─────────────────┐                         │
│                         │   HALF_OPEN     │                         │
│                         │  (Probe)        │                         │
│                         └────────┬────────┘                         │
│                                  │                                   │
│           ┌──────────────────────┼──────────────────────┐           │
│           │                      │                      │           │
│      success_count           any failure            timeout          │
│      >= threshold                                  reached          │
│           │                      │                      │           │
│           ▼                      ▼                      ▼           │
│     ┌──────────┐          ┌──────────┐          ┌──────────┐       │
│     │ CLOSED   │          │   OPEN   │          │   OPEN   │       │
│     └──────────┘          └──────────┘          └──────────┘       │
└──────────────────────────────────────────────────────────────────────┘
```

### Rate Limiter Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Rate Limiter (Token Bucket)                        │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    TokenBucketRateLimiter                     │    │
│  │                                                              │    │
│  │  Configuration:                                              │    │
│  │  - rate_per_second: float = 10.0                            │    │
│  │  - capacity: int = 10                                       │    │
│  │                                                              │    │
│  │  State:                                                      │    │
│  │  - _tokens: float = capacity                                │    │
│  │  - _last_refill_nanos: float                                │    │
│  │  - _capacity: float                                         │    │
│  │  - _lock: threading.Lock                                    │    │
│  │                                                              │    │
│  │  Methods:                                                    │    │
│  │  - acquire(tokens=1, timeout=None) → bool                  │    │
│  │  - reset() → None                                           │    │
│  │  - available_tokens → float (read-only)                     │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    MultiBucketRateLimiter                    │    │
│  │                                                              │    │
│  │  Manages multiple buckets by category:                      │    │
│  │  - "orders"  → TokenBucketRateLimiter                       │    │
│  │  - "quotes"  → TokenBucketRateLimiter                       │    │
│  │  - "data"    → TokenBucketRateLimiter                       │    │
│  │                                                              │    │
│  │  Methods:                                                    │    │
│  │  - acquire(category, tokens, timeout) → bool               │    │
│  │  - reduce_rate(category, factor) → None                    │    │
│  │  - increase_rate(category, factor) → None                  │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### Retry with Exponential Backoff

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Retry Executor                                    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    RetryExecutor                             │    │
│  │                                                              │    │
│  │  Configuration:                                              │    │
│  │  - max_retries: int = 3                                     │    │
│  │  - base_delay: float = 1.0                                  │    │
│  │  - max_delay: float = 30.0                                  │    │
│  │  - exponential_base: float = 2.0                            │    │
│  │                                                              │    │
│  │  Strategy:                                                   │    │
│  │  delay = min(base_delay * (exponential_base ** attempt),   │    │
│  │              max_delay) * random_jitter                      │    │
│  │                                                              │    │
│  │  Methods:                                                    │    │
│  │  - execute(fn, *args, **kwargs) → T                        │    │
│  │  - execute_with_fallback(fn, fallback_fn) → T              │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## CLI/TUI Architecture

### CLI Command Structure

```
┌──────────────────────────────────────────────────────────────────────┐
│                    CLI Commands (cli/commands/)                        │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Core Commands                             │    │
│  │  - broker.py    │ - orders.py     │ - portfolio.py          │    │
│  │  - account.py   │ - positions.py  │ - holdings.py           │    │
│  │  - market.py    │ - watchlist.py  │ - settings.py           │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Analytics Commands                        │    │
│  │  - analytics.py        │ - analytics_backtest.py            │    │
│  │  - analytics_scanner.py│ - analytics_replay.py              │    │
│  │  - analytics_research.py│ - analytics_optimize.py           │    │
│  │  - analytics_sector.py │ - analytics_stock.py               │    │
│  │  - analytics_strategies.py │ - analytics_walkforward.py     │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Diagnostic Commands                       │    │
│  │  - doctor.py      │ - validate.py      │ - benchmark.py     │    │
│  │  - events.py      │ - quality_report.py │ - protocol.py     │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### TUI Widget Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                    TUI Widgets (cli/widgets/)                         │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Trading Widgets                           │    │
│  │  - market_console.py     │ Real-time market data            │    │
│  │  - oms_console.py        │ Order management                 │    │
│  │  - broker_console.py     │ Broker status                    │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Diagnostic Widgets                        │    │
│  │  - diagnostics_console.py │ System health                   │    │
│  │  - performance_console.py │ Metrics                         │    │
│  │  - event_ws_console.py    │ WebSocket events                │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    TUI Application                           │    │
│  │  - tui_app.py          │ Main application                   │    │
│  │  - tui.tcss            │ Textual CSS styles                 │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Analytics & Backtesting

### Analytics Module Structure

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Analytics (analytics/)                             │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Core Analytics                            │    │
│  │  - core/             │ - features/        │ - indicators/   │    │
│  │  - probability/      │ - ranking/         │ - volatility/   │    │
│  │  - volume_profile/   │ - orderflow/       │ - sector/       │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Backtesting                               │    │
│  │  - backtest/engine.py       │ Backtesting engine            │    │
│  │  - backtest/optimizer.py    │ Strategy optimization         │    │
│  │  - backtest/comparator.py   │ Compare backtest results      │    │
│  │  - backtest/models.py       │ Backtest models               │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Strategy & Scanner                        │    │
│  │  - strategy/         │ - scanner/          │ - stocks/      │    │
│  │  - futures/          │ - options/          │ - paper/       │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Visualization                             │    │
│  │  - views/            │ - visualizations/   │ - reports/     │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### Backtesting Engine

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Backtesting Engine (analytics/backtest/)           │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    engine.py                                 │    │
│  │                                                              │    │
│  │  Class: BacktestEngine                                      │    │
│  │                                                              │    │
│  │  Methods:                                                    │    │
│  │  - run(strategy, data, params) → BacktestResult            │    │
│  │  - run_walk_forward(strategy, data, windows) → WFResult    │    │
│  │                                                              │    │
│  │  Components:                                                 │    │
│  │  - DataHandler      │ Feeds historical data                │    │
│  │  - StrategyRunner   │ Executes strategy logic              │    │
│  │  - PortfolioTracker │ Tracks positions and PnL             │    │
│  │  - RiskManager      │ Pre-trade risk checks                │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    optimizer.py                              │    │
│  │                                                              │    │
│  │  Class: StrategyOptimizer                                   │    │
│  │                                                              │    │
│  │  Methods:                                                    │    │
│  │  - grid_search(strategy, data, param_grid) → OptResult     │    │
│  │  - optimize(strategy, data, objective) → OptResult          │    │
│  │                                                              │    │
│  │  Optimization Targets:                                       │    │
│  │  - sharpe_ratio    │ - total_return    │ - max_drawdown     │    │
│  │  - win_rate        │ - profit_factor   │ - calmar_ratio     │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Data Lake Architecture

### Data Lake Components

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Data Lake (datalake/)                              │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Storage Layer                             │    │
│  │  - store/parquet_store.py    │ Parquet storage              │    │
│  │  - store/__init__.py         │ Storage exports              │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Data Management                           │    │
│  │  - loader.py           │ Data loading                        │    │
│  │  - updater.py          │ Data updates                        │    │
│  │  - normalize.py        │ Data normalization                  │    │
│  │  - converter.py        │ Format conversion                   │    │
│  │  - schema.py           │ Data schemas                        │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Query Layer                               │    │
│  │  - gateway.py          │ Data access gateway                │    │
│  │  - api/                │ REST API endpoints                 │    │
│  │  - duckdb_utils.py     │ DuckDB utilities                   │    │
│  │  - fast_backtest.py    │ Optimized backtesting              │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Specialized Stores                        │    │
│  │  - journal.py          │ Trade journal (WAL SQLite)        │    │
│  │  - catalog.py          │ Data catalog                       │    │
│  │  - scan_store.py       │ Scanner results                    │    │
│  │  - backtest_cache_store.py │ Backtest cache                 │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Monitoring                                │    │
│  │  - monitor.py          │ Data monitoring                    │    │
│  │  - health_check.py     │ Health checks                      │    │
│  │  - quality.py          │ Data quality                        │    │
│  │  - validation.py       │ Data validation                    │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### Parquet Store Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Parquet Store (datalake/store/parquet_store.py)    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    ParquetStore                              │    │
│  │                                                              │    │
│  │  Methods:                                                    │    │
│  │  - load(symbol, timeframe, date_range) → DataFrame         │    │
│  │  - save(symbol, timeframe, df) → None                      │    │
│  │  - resample(symbol, from_tf, to_tf) → DataFrame            │    │
│  │  - list_symbols() → list[str]                               │    │
│  │  - delete(symbol, timeframe, date_range) → None            │    │
│  │                                                              │    │
│  │  Storage Structure:                                          │    │
│  │  data/                                                      │    │
│  │  ├── {symbol}/                                              │    │
│  │  │   ├── 1min/                                              │    │
│  │  │   │   ├── 2024-01.parquet                                │    │
│  │  │   │   ├── 2024-02.parquet                                │    │
│  │  │   │   └── ...                                            │    │
│  │  │   ├── 5min/                                              │    │
│  │  │   ├── 15min/                                             │    │
│  │  │   ├── 1hour/                                             │    │
│  │  │   └── daily/                                             │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Infrastructure Components

### Lifecycle Manager

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Lifecycle Manager (infrastructure/lifecycle/)       │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    LifecycleManager                          │    │
│  │                                                              │    │
│  │  Purpose: Own every background service for deterministic    │    │
│  │           startup and shutdown                              │    │
│  │                                                              │    │
│  │  Methods:                                                    │    │
│  │  - register(service: ManagedService) → None                │    │
│  │  - start_all() → None                                      │    │
│  │  - stop_all() → None                                       │    │
│  │  - get_health() → dict[str, HealthStatus]                  │    │
│  │                                                              │    │
│  │  Managed Services:                                           │    │
│  │  - TokenRefreshScheduler                                    │    │
│  │  - ReconciliationService                                    │    │
│  │  - DailyPnlResetScheduler                                   │    │
│  │  - DhanMarketFeed                                           │    │
│  │  - DhanOrderStream                                          │    │
│  │  - PollingMarketFeed                                        │    │
│  │  - HttpObservabilityServer                                  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    ManagedService Protocol                   │    │
│  │                                                              │    │
│  │  Interface:                                                  │    │
│  │  - start() → None                                          │    │
│  │  - stop() → None                                           │    │
│  │  - health() → HealthStatus                                 │    │
│  │                                                              │    │
│  │  HealthStatus:                                               │    │
│  │  - state: HealthState (HEALTHY, DEGRADED, FAILED)          │    │
│  │  - message: str | None                                     │    │
│  │  - last_check: datetime                                    │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### Event Bus

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Event Bus (infrastructure/event_bus/)              │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    EventBus                                  │    │
│  │                                                              │    │
│  │  Thread-safe pub/sub with dead-letter queue                 │    │
│  │                                                              │    │
│  │  Methods:                                                    │    │
│  │  - publish(event: DomainEvent) → None                      │    │
│  │  - subscribe(event_type, handler) → Subscription            │    │
│  │  - unsubscribe(subscription) → None                        │    │
│  │                                                              │    │
│  │  Implementation:                                             │    │
│  │  - _subscribers: dict[str, list[Callable]]                 │    │
│  │  - _lock: threading.RLock                                  │    │
│  │  - _dead_letter_queue: list[DomainEvent]                   │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    DomainEvent                               │    │
│  │                                                              │    │
│  │  Fields:                                                     │    │
│  │  - event_type: str                                          │    │
│  │  - payload: dict                                            │    │
│  │  - symbol: str | None                                      │    │
│  │  - source: str                                              │    │
│  │  - correlation_id: str | None                              │    │
│  │  - timestamp: datetime                                     │    │
│  │                                                              │    │
│  │  Factory:                                                    │    │
│  │  - DomainEvent.now(type, payload, ...) → DomainEvent       │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    ProcessedTradeRepository                  │    │
│  │                                                              │    │
│  │  Purpose: Idempotency ledger for trade events              │    │
│  │                                                              │    │
│  │  Methods:                                                    │    │
│  │  - is_processed(key: TradeIdKey) → bool                   │    │
│  │  - mark_processed(key: TradeIdKey) → None                 │    │
│  │                                                              │    │
│  │  TradeIdKey:                                                 │    │
│  │  - trade_id: str                                            │    │
│  │  - order_id: str                                            │    │
│  │  - exchange: str                                            │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### Observability

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Observability (brokers/common/observability/)       │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    EventMetrics                              │    │
│  │                                                              │    │
│  │  Purpose: Count events for Prometheus export                │    │
│  │                                                              │    │
│  │  Methods:                                                    │    │
│  │  - inc(name, label, amount=1) → None                       │    │
│  │  - get(name, label) → int                                  │    │
│  │  - to_prometheus() → str                                   │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    HttpObservabilityServer                   │    │
│  │                                                              │    │
│  │  Endpoints:                                                  │    │
│  │  - GET /healthz    │ Liveness probe (200 if process up)    │    │
│  │  - GET /readyz     │ Readiness probe (503 if degraded)     │    │
│  │  - GET /metrics    │ Prometheus text format                 │    │
│  │                                                              │    │
│  │  Metrics Include:                                            │    │
│  │  - daily_pnl: float                                        │    │
│  │  - kill_switch_active: bool                                │    │
│  │  - orders_placed: int                                      │    │
│  │  - orders_rejected: int                                    │    │
│  │  - trades_processed: int                                   │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Feature Matrix

### Broker Features

| Feature | Dhan | Upstox | Paper |
|---------|------|--------|-------|
| Market Data (LTP, Quote, History) | ✅ | ✅ | ✅ |
| Market Depth | ✅ | ✅ | ✅ |
| Option Chain | ✅ | ✅ | ❌ |
| Future Chain | ✅ | ❌ | ❌ |
| Order Placement | ✅ | ✅ | ✅ |
| Order Modification | ✅ | ✅ | ✅ |
| Order Cancellation | ✅ | ✅ | ✅ |
| Slice Orders | ✅ | ✅ | ❌ |
| Cover Orders | ✅ | ✅ | ❌ |
| GTT/Forever Orders | ✅ | ✅ | ❌ |
| Conditional Alerts | ✅ | ✅ | ❌ |
| Positions | ✅ | ✅ | ✅ |
| Holdings | ✅ | ✅ | ❌ |
| Funds | ✅ | ✅ | ✅ |
| Trades | ✅ | ✅ | ✅ |
| WebSocket Streaming | ✅ | ✅ | ❌ |
| Kill Switch | ✅ | ✅ | ✅ |
| Token Refresh | ✅ | ✅ | N/A |
| Rate Limiting | ✅ | ✅ | N/A |
| Circuit Breaker | ✅ | ✅ | N/A |

### OMS Features

| Feature | Status |
|---------|--------|
| Idempotent Order Placement | ✅ |
| Pre-trade Risk Checks | ✅ |
| Kill Switch | ✅ |
| Position Limits | ✅ |
| Gross Exposure Limits | ✅ |
| Daily Loss Limits | ✅ |
| Order State Validation | ✅ |
| Audit Logging | ✅ |
| Event Publishing | ✅ |
| Trade Idempotency | ✅ |
| Reconciliation | ✅ |
| Daily PnL Reset | ✅ |

### Analytics Features

| Feature | Status |
|---------|--------|
| Backtesting Engine | ✅ |
| Strategy Optimization | ✅ |
| Walk-Forward Analysis | ✅ |
| Market Scanner | ✅ |
| Technical Indicators | ✅ |
| Volume Profile | ✅ |
| Order Flow Analysis | ✅ |
| Probability Analysis | ✅ |
| Sector Analysis | ✅ |
| Volatility Analysis | ✅ |
| Replay Engine | ✅ |
| Paper Trading | ✅ |
| Visualization | ✅ |

### CLI/TUI Features

| Feature | Status |
|---------|--------|
| TUI Dashboard | ✅ |
| Broker Management | ✅ |
| Order Management | ✅ |
| Position Tracking | ✅ |
| Portfolio View | ✅ |
| Market Data Display | ✅ |
| Diagnostics | ✅ |
| Health Checks | ✅ |
| Metrics Display | ✅ |
| WebSocket Events | ✅ |

---

## Import Direction Rules

### Layer Boundaries (Enforced by import-linter)

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Import Direction Rules                             │
│                                                                      │
│  Allowed Imports:                                                    │
│                                                                      │
│  domain/ ← (no imports from brokers, analytics, cli, application)   │
│                                                                      │
│  infrastructure/ ← (no imports from brokers, analytics, cli,        │
│                      application)                                    │
│                                                                      │
│  brokers/common/ ← (no imports from brokers/dhan, brokers/upstox,   │
│                      analytics)                                      │
│                                                                      │
│  analytics/ ← (no imports from brokers.dhan, brokers.upstox,        │
│                brokers.paper)                                        │
│                                                                      │
│  application/ ← (no imports from brokers except test modules)       │
│                                                                      │
│  Forbidden Imports:                                                   │
│                                                                      │
│  - cli/ cannot be imported by lower layers                          │
│  - brokers.dhan/ cannot be imported by brokers/common/              │
│  - brokers.upstox/ cannot be imported by brokers/common/            │
│  - Cross-broker imports are forbidden                               │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Configuration

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `RISK_FAIL_OPEN` | Allow legacy placeholder capital | `0` (fail closed) |
| `DHAN_CLIENT_ID` | Dhan broker client ID | Required for Dhan |
| `DHAN_ACCESS_TOKEN` | Dhan API access token | Required for Dhan |
| `UPSTOX_ACCESS_TOKEN` | Upstox API access token | Required for Upstox |
| `PRE_PROD_GATE` | Enable pre-prod test gate | `0` |
| `DHAN_INTEGRATION` | Enable Dhan integration tests | `0` |
| `UPSTOX_INTEGRATION` | Enable Upstox integration tests | `0` |

### Rate Limiting Defaults

| Category | Rate/Second | Capacity |
|----------|-------------|----------|
| Orders | 10 | 10 |
| Quotes | 20 | 20 |
| Data | 5 | 5 |

### Circuit Breaker Defaults

| Parameter | Value |
|-----------|-------|
| Failure Threshold | 5 |
| Success Threshold | 3 |
| Open Duration | 30 seconds |

---

## Testing Architecture

### Test Markers

| Marker | Purpose |
|--------|---------|
| `unit` | Module-owned unit tests |
| `contract` | Broker/module contract tests |
| `dhan` | DhanHQ integration tests |
| `integration` | External broker API tests |
| `sandbox` | Order placement tests |
| `live_readonly` | Read-only live tests |
| `performance` | Latency benchmarks |
| `upstox` | Upstox-specific tests |
| `chaos` | Deterministic failure tests |
| `e2e` | End-to-end flow tests |

### Test Structure

```
tests/
├── chaos/                    # B10 chaos tests
│   ├── test_token_expiry.py
│   ├── test_kill_switch_flips.py
│   ├── test_concurrent_orders.py
│   └── ...
├── integration/              # OMS event-replay tests
│   └── fixtures/
├── unit/                     # Unit tests
└── e2e/                      # End-to-end tests
```

---

## API Endpoints

### HTTP Observability Server

| Endpoint | Method | Purpose | Response |
|----------|--------|---------|----------|
| `/healthz` | GET | Liveness probe | 200 if process up |
| `/readyz` | GET | Readiness probe | 200 if ready, 503 if degraded |
| `/metrics` | GET | Prometheus metrics | Text format |

### Data Lake API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/symbols` | GET | List available symbols |
| `/api/data/{symbol}` | GET | Fetch historical data |
| `/api/quotes` | GET | Fetch current quotes |
| `/api/positions` | GET | Fetch current positions |
| `/api/holdings` | GET | Fetch holdings |
| `/api/funds` | GET | Fetch fund limits |

---

## Deployment

### Production Readiness Checklist

1. ✅ Central OMS on live CLI path
2. ✅ Risk manager with kill switch
3. ✅ Thread-safe state mutations (RLock)
4. ✅ LifecycleManager owns all background services
5. ✅ HTTP observability (healthz, readyz, metrics)
6. ✅ Chaos test suite
7. ✅ Dead-code elimination
8. ✅ Real capital sizing
9. ✅ Import direction enforcement
10. ✅ Production readiness gate

---

*This document was generated from the actual codebase structure. All components, files, and relationships are accurate as of the current codebase state.*
