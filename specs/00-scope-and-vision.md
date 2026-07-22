# 00 — Scope and Vision

## 1. Product Definition

TradeX is a **professional, event-driven algorithmic trading platform** for Indian exchanges (NSE/BSE/MCX), reimplemented under [NautilusTrader](https://nautilustrader.io/) engine patterns: message-driven core, Clock + Cache, venue adapters, deterministic replay, and **research-to-live parity**.

The platform is a **framework**, not merely an application: the engine owns the lifecycle and invokes user strategies, scanners, and portfolio models through typed messages.

### Reimplementation Scope

This specification covers reimplementing the **full product capability surface**:

- Analytics-first research (scanners, indicators, ranking, sector, options, futures, volatility, orderflow, breadth, volume profile, probability, fundamentals, walk-forward)
- Four execution modes: **Replay, Backtest, Paper, Live**
- OMS with zero-parity spine (single ExecutionEngine, no bypass paths)
- Venue adapters: Dhan, Upstox, Paper
- Datalake with quality, corporate actions, MCP
- Interfaces: analytics-first CLI, TUI, FastAPI, MCP

### Framework vs Application

| Application | Framework (Nautilus-style) |
|-------------|------------------------------|
| User code calls the system | Engine calls user code (strategies, actors) |
| Separate backtest and live code | Research-to-live parity: same engine, different FillSource |
| Observability bolted on | MessageBus is the observability spine |
| Hard-coded venue logic | Venue adapters via entry points |

## 2. Nautilus Alignment

TradeX adopts NautilusTrader **engine patterns** (not its full multi-asset venue catalog):

| Nautilus Concept | TradeX Equivalent |
|------------------|-------------------|
| TradingNode | TradingNode — configure, start, stop, run |
| MessageBus | MessageBus — typed publish/subscribe |
| Clock | SystemClock / FakeClock — nanosecond UTC |
| Cache | TradingCache — orders, positions, quotes |
| Actors / Strategies | Strategy protocol + StrategyEngine |
| Venue Adapters | BrokerAdapter plugins (Dhan, Upstox, Paper) |
| Event-sourced replay | ReplayEngine + durable MessageLog |
| Research-to-live parity | Same ExecutionEngine across four modes |
| Portfolio | PositionManager + PortfolioModel |

Market focus remains **Indian equities and derivatives** (NSE/BSE/MCX). Crypto, FX, betting, and prediction markets are out of scope.

### What We Adapt from NautilusTrader

| NautilusTrader | TradeX Adaptation | Reason |
|----------------|-------------------|--------|
| Rust/Cython core | Pure Python | Team size, iteration speed |
| Multi-asset global venues | NSE/BSE/MCX only | Product focus |
| Custom storage engine | DuckDB + Parquet | Analytics fit, zero ops overhead |
| Library-only | Click CLI + FastAPI + TUI + MCP | Analytics-first product |
| FIX protocol | REST + WebSocket (broker SDKs) | Indian broker APIs |
| Generic risk | Indian market rules (STT, margins, circuit limits) | Domain accuracy |

## 3. Core Design Philosophy

### First Principles

1. **Research-to-live parity** — Replay, Backtest, Paper, and Live share identical OMS, risk, and FSM logic
2. **Single ExecutionEngine spine** — no alternate order paths (no bypass adapters)
3. **Message-driven everything** — all inter-component communication via MessageBus
4. **Dependency inversion** — domain ports; venue logic in plugins only
5. **Deterministic replay** — event log reproduces identical state byte-for-byte
6. **Observability is structural** — every message and order transition is traceable
7. **Zero-allocation hot paths** — frozen dataclasses, pre-allocated buffers on order/fill path
8. **Type safety first** — Protocol, TypedDict, frozen dataclasses, Pydantic at config boundaries
9. **Plugin over configuration** — brokers/exchanges via entry points; no central switch statements

### Immutable Research Pipeline

```
Market Data → FeaturePipeline → Indicators → Strategies → Signals
  → PortfolioModel → RiskGate → OMS → ExecutionEngine → ExecutionTarget
```

This pipeline is identical across all four modes. Only DataSource, Clock, and FillSource differ at composition time.

## 4. Four Execution Modes

| Mode | Data Source | FillSource | Clock | Purpose |
|------|-------------|------------|-------|---------|
| **REPLAY** | Event log / recorded session | Same engine replay | FakeClock | Audit, debug, regression |
| **BACKTEST** | Datalake / Parquet / DuckDB | SimulatedFillSource | FakeClock | Historical strategy research |
| **PAPER** | Live DataProvider | PaperFillSource | SystemClock | Live-data simulation |
| **LIVE** | Live DataProvider | BrokerFillSource | SystemClock | Real venue execution |

Environment is frozen at boot. Parity gate never skipped in LIVE.

## 5. Goals (Measurable)

| Goal | Measure |
|------|---------|
| Four-mode parity | Same ExecutionEngine FSM in Replay/Backtest/Paper/Live |
| No bypass paths | Zero alternate order-placement paths outside ExecutionEngine |
| Full capability coverage | All capabilities in coverage ledger marked COVERED |
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

## 6. Core User Flow

1. Operator selects mode (Replay/Backtest/Paper/Live) and venue plugin
2. TradingNode wires MessageBus, Clock, TradingCache, RiskEngine, ExecutionEngine, FillSource
3. Structural boot checks; Environment frozen
4. For Live/Paper: venue connects, reconciliation completes
5. Market data: VenueAdapter → MarketDataEngine → FeaturePipeline → Indicators → Strategies
6. Signals → PortfolioModel → OrderCommand via MessageBus
7. Order spine: IdempotencyGuard → RiskGate → ExecutionEngine → FillSource → venue
8. Fills: ExecutionEngine → Cache FSM → PositionManager → MessageBus
9. Analytics results via CLI/TUI/API; research reports from ReportEngine

## 7. Features (by Category)

### Research and Analytics
- FeaturePipeline, indicator library, built-in strategies
- Scanners (momentum, breakout, volume, relative strength)
- Ranking, sector rotation/strength/volume, market breadth
- Options, futures, volatility, orderflow, volume profile, probability analytics
- Backtest, walk-forward, replay, paper, live engines
- Fundamentals, intraday, stock analytics, reports

### Execution
- Four-mode ExecutionTarget resolution
- TradingOrchestrator, MultiStrategyRuntime
- Order FSM, fill dedup, reconciliation

### Market Data and Storage
- Live streaming + historical datalake
- Corporate actions, data quality, source selection
- NSE exchange calendar

### Risk and Safety
- Pre-trade RiskGate, loss circuit breaker, kill switch
- Post-trade monitor, auto-flatten, audit log

### Interfaces
- Analytics-first CLI, Textual TUI, FastAPI, MCP

## 8. In Scope

Everything listed in [15-capability-coverage.md](15-capability-coverage.md) — 147 capabilities across engine, OMS, analytics, adapters, datalake, interfaces, observability, quality, and deployment.

## 9. Out of Scope

- Multi-tenant SaaS hosting
- Mobile applications
- Social/copy trading
- Cryptocurrency, FX, betting, prediction markets (initial release)
- Automated tax reporting
- Managed cloud brokerage accounts

## 10. Success Criteria

| Criterion | Verification |
|-----------|--------------|
| Four-mode parity | Parity gate: identical FSM in all modes |
| Single spine | Architecture test: no bypass order path |
| Full coverage | 147/147 capabilities COVERED in ledger |
| Risk before I/O | Integration test: RISK_REJECTED never reaches venue |
| Idempotent orders | Duplicate correlation_id → prior result |
| Deterministic replay | Event log replay → identical cache |
| LIVE safety | Parity gate + `--confirm` + reconciliation before traffic |
| Analytics CLI | All command groups functional |

## 11. The Framework Contract

1. **Inversion of Control** — Implement Strategy, Scanner, PortfolioModel; engine invokes them
2. **Research-to-Live Parity** — Write strategy once; run in Replay/Backtest/Paper/Live unchanged
3. **Pluggable Venues** — Add brokers via entry points; no central switch
4. **Deterministic Replay** — Every message timestamped; replay rebuilds state
5. **Safety by Default** — RiskGate and IdempotencyGuard mandatory
6. **Single Spine** — All orders through ExecutionEngine; no bypass

## 12. Architecture Decisions

| ADR | Decision | Rationale |
|-----|----------|-----------|
| ADR-001 | MessageBus as central communication | Replay, testing, observability, decoupling |
| ADR-002 | Gateway → Connection → Sub-Adapters | Eliminates god classes; independent adapter tests |
| ADR-003 | FillSource as zero-parity seam | Single execution path; mode-agnostic OMS |
| ADR-004 | Standard component lifecycle | Predictable startup/shutdown; health checks |
| ADR-005 | Declarative YAML config | Single source of truth for assembly |
| ADR-006 | DuckDB + Parquet storage | Columnar analytics; zero server overhead |
| ADR-007 | Instrument ref isolation | Callers use canonical IDs; wire types stay in plugins |
| ADR-008 | Python-only core | Iteration speed over raw performance |
