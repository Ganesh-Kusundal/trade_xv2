# 15 — Capability Coverage Ledger

Complete inventory of product capabilities to reimplement under NautilusTrader-style architecture. Every row must be COVERED in the owning spec before implementation is considered spec-complete.

**Status:** COVERED = specified with contracts/invariants in owning doc.

## How to use

| Column | Meaning |
|--------|---------|
| Capability | Named product capability (no implementation paths) |
| Primary Spec | Single owning document |
| Status | COVERED |

---

## Core Engine

| Capability | Primary Spec | Status |
|------------|--------------|--------|
| TradingNode (public entry point) | 11 | COVERED |
| MessageBus / EventBus | 03 | COVERED |
| Clock (SystemClock, FakeClock) | 02, 04 | COVERED |
| TradingCache (authoritative state) | 04, 01 | COVERED |
| Component lifecycle (initialize/start/stop/reset) | 03 | COVERED |
| LifecycleManager | 03 | COVERED |
| ComponentRegistry | 01, 11 | COVERED |
| RuntimeFactory / composition root | 01, 14 | COVERED |
| Plugin discovery (brokers, exchanges) | 01, 06 | COVERED |
| Durable event log + deterministic replay | 03, 05 | COVERED |
| Environment freeze at boot | 01, 08 | COVERED |
| Component base class + ComponentState | 02, 03 | COVERED |
| TradingContext | 02, 04 | COVERED |
| ComponentFactory | 11, 14 | COVERED |
| Shared layer (logging, config, types) | 01, 10 | COVERED |

## Execution Modes (Four-Mode Parity)

| Capability | Primary Spec | Status |
|------------|--------------|--------|
| REPLAY mode (event-sourced replay) | 05, 08 | COVERED |
| BACKTEST mode (historical simulation) | 05, 08 | COVERED |
| PAPER mode (live data, simulated fills) | 05, 08 | COVERED |
| LIVE mode (live data, venue fills) | 04, 05, 08 | COVERED |
| ExecutionTarget / FillSource resolution | 04, 01 | COVERED |
| SimulatedFillSource | 04 | COVERED |
| PaperFillSource | 04 | COVERED |
| BrokerFillSource | 04, 06 | COVERED |
| ReplayFillSource | 04 | COVERED |
| Single ExecutionEngine spine (no bypass) | 04, 09, 12 | COVERED |

## OMS and Trading

| Capability | Primary Spec | Status |
|------------|--------------|--------|
| OrderManager + Order FSM | 04, 02 | COVERED |
| PositionManager + PnL projection | 04 | COVERED |
| RiskManager / RiskGate (pre-trade) | 04, 09 | COVERED |
| IdempotencyGuard (correlation_id) | 04, 09 | COVERED |
| ProcessedTradeRepository (fill dedup) | 04, 03 | COVERED |
| ReconciliationEngine (pure compare) | 02, 04, 08 | COVERED |
| TradingOrchestrator | 04, 05 | COVERED |
| MultiStrategyRuntime | 04, 05 | COVERED |
| Order placement / cancel / modify | 04, 08 | COVERED |
| Post-trade monitor + auto-flatten | 09 | COVERED |
| Loss circuit breaker | 09 | COVERED |
| Pluggable RiskRulesEngine | 09 | COVERED |
| Indian market risk (STT, circuit, hours) | 09 | COVERED |
| Kill switch | 09 | COVERED |
| TradingState (READY/DEGRADED/HALTED/RECONCILING) | 09 | COVERED |

## Immutable Research Pipeline

| Capability | Primary Spec | Status |
|------------|--------------|--------|
| Market Data ingestion | 07, 08 | COVERED |
| FeaturePipeline | 05, 01 | COVERED |
| Indicator computation | 05, 02 | COVERED |
| StrategyEngine | 05 | COVERED |
| Signal generation | 05 | COVERED |
| PortfolioModel / rebalancing | 05 | COVERED |
| Risk gate on order path | 09, 08 | COVERED |
| OMS order path | 04, 08 | COVERED |
| Execution Target | 04, 08 | COVERED |

## Strategy and Analytics

| Capability | Primary Spec | Status |
|------------|--------------|--------|
| Strategy protocol (on_bar, on_fill, etc.) | 05, 02 | COVERED |
| StrategyPipeline | 05 | COVERED |
| ReplayEngine | 05, 08 | COVERED |
| BacktestEngine | 05, 08 | COVERED |
| PaperTradingEngine | 05, 08 | COVERED |
| LiveTradingEngine | 05, 08 | COVERED |
| Walk-forward optimization | 05, 11 | COVERED |
| Scanner (momentum, breakout, volume, RS) | 05, 11 | COVERED |
| RankingEngine | 05 | COVERED |
| SectorAnalyzer (rotation, strength, volume) | 05, 11 | COVERED |
| OptionsAnalytics | 05 | COVERED |
| FuturesAnalytics | 05 | COVERED |
| VolatilityAnalytics | 05 | COVERED |
| OrderFlowAnalytics | 05 | COVERED |
| MarketBreadthAnalytics | 05, 11 | COVERED |
| VolumeProfileBuilder | 05 | COVERED |
| ProbabilityEngine | 05 | COVERED |
| Fundamentals analytics | 05, 11 | COVERED |
| Intraday analytics | 05 | COVERED |
| StockAnalytics | 05 | COVERED |
| Indicator library (trend, momentum, volatility, volume, pattern) | 05, 02 | COVERED |
| HalfTrend and built-in strategies | 05 | COVERED |
| ReportEngine (PnL, drawdown, Sharpe) | 05, 11 | COVERED |
| Analytics facade | 05, 11 | COVERED |
| ResearchAPI | 07, 05 | COVERED |

## Broker and Venue Adapters

| Capability | Primary Spec | Status |
|------------|--------------|--------|
| BrokerAdapter protocol | 06, 02 | COVERED |
| Gateway → Connection → Sub-Adapters | 06 | COVERED |
| Dhan venue adapter | 06 | COVERED |
| Upstox venue adapter | 06 | COVERED |
| Paper venue adapter | 06 | COVERED |
| Wire mapping (native ↔ domain) | 06 | COVERED |
| Instrument ref isolation | 06 | COVERED |
| Market data streaming (WS) | 06, 07 | COVERED |
| Order streaming | 06 | COVERED |
| Auth (TOTP, OAuth, token store) | 06, 01 | COVERED |
| Rate limiting (per-broker + global quota) | 06, 08 | COVERED |
| Broker reconciliation (mass status) | 06, 04, 08 | COVERED |
| BrokerHealthMonitor | 06, 10 | COVERED |
| StatusMapperRegistry | 06 | COVERED |
| NSE exchange plugin + TradingCalendar | 06, 07 | COVERED |
| MCX exchange support | 02, 06, 07 | COVERED |
| BrokerCapabilities dataclass | 06 | COVERED |
| BaseWireAdapter + SymbolResolver | 06 | COVERED |

## Data Infrastructure

| Capability | Primary Spec | Status |
|------------|--------------|--------|
| Datalake (Parquet + DuckDB) | 07 | COVERED |
| DataLakeGateway (read-only adapter) | 07 | COVERED |
| HistoricalDataCoordinator | 07 | COVERED |
| SourceSelectionPolicy (federated history) | 07 | COVERED |
| Ingestion pipeline (ETL) | 07 | COVERED |
| DataQualityEngine | 07 | COVERED |
| UniverseQualityEngine | 07 | COVERED |
| CorporateActionStore | 07 | COVERED |
| InstrumentMaster | 02, 07 | COVERED |
| Bar aggregation / timeframes | 07, 02 | COVERED |
| MarketDataEngine | 07, 08 | COVERED |
| Unified DataEngine | 07 | COVERED |
| DataCatalog (DuckDB over Parquet) | 07 | COVERED |
| StreamOrchestrator / LiveTickPipeline | 07 | COVERED |
| MCP server (datalake queries) | 07, 11 | COVERED |
| QuotaScheduler (cross-broker) | 06, 08 | COVERED |

## Interfaces

| Capability | Primary Spec | Status |
|------------|--------------|--------|
| Analytics-first CLI | 11 | COVERED |
| Textual TUI | 11 | COVERED |
| FastAPI REST API | 11 | COVERED |
| MCP datalake server | 07, 11 | COVERED |
| Config CLI (get/set/list/validate) | 11 | COVERED |
| Interactive shell | 11 | COVERED |

## Observability and Ops

| Capability | Primary Spec | Status |
|------------|--------------|--------|
| Structured logging (structlog JSON) | 10 | COVERED |
| Metrics collection | 10 | COVERED |
| Distributed tracing (OpenTelemetry) | 10 | COVERED |
| Health / readiness probes | 10, 13 | COVERED |
| Audit sink (append-only) | 10, 09 | COVERED |
| AlertingEngine | 10 | COVERED |
| DeadLetterQueue | 03, 10 | COVERED |
| EventMetrics | 10 | COVERED |

## Quality and Deployment

| Capability | Primary Spec | Status |
|------------|--------------|--------|
| Test pyramid (unit → e2e) | 12 | COVERED |
| Four-mode parity gate | 12 | COVERED |
| AdapterTestHarness | 12, 06 | COVERED |
| Flow contract tests | 12, 08 | COVERED |
| Import boundary contracts | 12, 01 | COVERED |
| God-class degree architecture test | 01, 12 | COVERED |
| Mutation testing (critical paths) | 12 | COVERED |
| Docker multi-stage | 13 | COVERED |
| Helm / K8s deployment | 13 | COVERED |
| CI/CD pipeline | 13, 12 | COVERED |
| Release checklist | 13 | COVERED |
| LIVE post-deploy reconciliation | 13, 08 | COVERED |

## Domain Model

| Capability | Primary Spec | Status |
|------------|--------------|--------|
| Order, Position, Quote, Bar, Trade entities | 02 | COVERED |
| Instrument + InstrumentMaster | 02, 07 | COVERED |
| Message hierarchy (data, order, portfolio, risk, system) | 02, 03 | COVERED |
| Port protocols (Strategy, BrokerAdapter, FillSource, RiskModel, Clock) | 02 | COVERED |
| ReconciliationEngine (pure) | 02 | COVERED |
| StatisticsEngine (backtest metrics) | 02, 05 | COVERED |
| Enums (Environment, BrokerId, ExecutionTargetKind) | 02 | COVERED |
| MarketDepth + OptionChain entities | 02 | COVERED |
| FeeCalculator (STT, Indian fees) | 02, 09 | COVERED |

## Implementation

| Capability | Primary Spec | Status |
|------------|--------------|--------|
| Six-phase build order | 14 | COVERED |
| Target folder organization | 14 | COVERED |
| Per-phase acceptance criteria | 14 | COVERED |
| Framework contract verification checklist | 14 | COVERED |

---

## Coverage summary

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

All capabilities are COVERED. Specs 00–14 are sufficient to reimplement the full product under NautilusTrader-style architecture.
