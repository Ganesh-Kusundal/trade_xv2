# TradeX Framework — Engineering Specifications

Professional engineering documentation for reimplementing TradeX as a NautilusTrader-style algorithmic trading platform: message-driven core, research-to-live parity, venue adapters, and analytics-first surfaces for Indian exchanges (NSE/BSE/MCX).

## Mission

These specs define the **target product** for a greenfield reimplementation. They cover every capability the platform delivers today, reorganized under [NautilusTrader](https://nautilustrader.io/) engine patterns:

- Event-driven MessageBus as the sole inter-component channel
- Clock + Cache + deterministic replay
- Same ExecutionEngine across Replay, Backtest, Paper, and Live
- Venue adapters (Dhan, Upstox, Paper) discovered via entry points
- Immutable pipeline: Market Data → Features → Indicators → Strategies → Signals → Risk → OMS → Execution Target

Completeness is tracked in [15-capability-coverage.md](15-capability-coverage.md) (147 capabilities, all COVERED).

## Start Here

**[IMPLEMENTATION-SPEC.md](IMPLEMENTATION-SPEC.md)** — Unified implementation specification synthesized from goal.md and all numbered specs (00–15). Single source of truth for building the framework.

## Reading Order

| # | Document | Purpose |
|---|----------|---------|
| — | [Implementation Spec](IMPLEMENTATION-SPEC.md) | **Unified spec** — synthesize from all documents below |
| 00 | [Scope and Vision](00-scope-and-vision.md) | Product definition, four-mode parity, Nautilus alignment |
| 01 | [Architecture HLD](01-architecture-hld.md) | Layers, Nautilus concept map, immutable pipeline |
| 02 | [Domain Model](02-domain-model.md) | Entities, messages, ports, replay events |
| 03 | [Message Bus and Lifecycle](03-message-bus-and-lifecycle.md) | EventBus, durable log, deterministic replay |
| 04 | [Execution and OMS](04-execution-and-oms.md) | Four ExecutionTargets, orchestrator, single spine |
| 05 | [Strategy and Analytics](05-strategy-and-analytics.md) | FeaturePipeline, Replay/Backtest/Paper/Live engines |
| 06 | [Broker Adapter Framework](06-broker-adapter-framework.md) | Venue adapters, health monitor, rate limits |
| 07 | [Data Infrastructure](07-data-infrastructure.md) | Datalake, quality, corporate actions, MCP |
| 08 | [Flows and DFDs](08-flows-and-dfds.md) | Four-mode flows, research pipeline, order spine |
| 09 | [Risk and Safety](09-risk-and-safety.md) | RiskGate, circuit breaker, LIVE safety |
| 10 | [Observability and Ops](10-observability-and-ops.md) | Logging, metrics, tracing, alerting |
| 11 | [Configuration and DX](11-configuration-and-dx.md) | Analytics-first CLI, TradingNode, interfaces |
| 12 | [Testing and Quality](12-testing-and-quality.md) | Four-mode parity gate, AdapterTestHarness |
| 13 | [Deployment](13-deployment.md) | Docker, Helm, CI/CD, LIVE checklist |
| 14 | [Implementation Guide](14-implementation-guide.md) | Build phases, folder layout, acceptance |
| 15 | [Capability Coverage](15-capability-coverage.md) | Completeness ledger |
| — | [Goal (Legacy)](goal.md) | Original design exploration (superseded by IMPLEMENTATION-SPEC.md) |

## Document Map by Concern

| Concern | Primary | Supporting |
|---------|---------|------------|
| What we reimplement | 00, 15 | 14 |
| Nautilus-style engine | 01, 03 | 08 |
| Four-mode parity | 04, 05, 08 | 12 |
| Research pipeline | 05, 07 | 01, 08 |
| Trading correctness | 04, 09 | 08, 12 |
| Venue connectivity | 06 | 07, 08 |
| Analytics surface | 05, 11 | 07 |
| Production readiness | 10, 13 | 12 |

## Glossary

| Term | Definition |
|------|------------|
| **Research-to-Live Parity** | Same strategy, OMS, risk, and FSM across Replay/Backtest/Paper/Live; only FillSource, Clock, and DataSource differ |
| **TradingNode** | Public entry point — configure, start, stop, submit orders |
| **MessageBus** | Central typed event dispatcher; sole inter-component channel |
| **Clock** | SystemClock (live/paper) or FakeClock (backtest/replay); nanosecond UTC |
| **TradingCache** | Authoritative in-memory state for orders, positions, quotes |
| **FillSource / ExecutionTarget** | Simulated, Paper, or Broker — the only mode-specific execution piece |
| **FeaturePipeline** | Market Data → computed features → indicators |
| **ReplayEngine** | Event-sourced deterministic replay through same engine |
| **VenueAdapter** | Pluggable broker gateway (Dhan, Upstox, Paper) |
| **RiskGate** | Mandatory pre-trade check before venue I/O |

## Conventions

- Specs describe the **target system**, not as-built documentation.
- No implementation file paths in published specs — capability names and contracts only.
- Every major flow includes an **Expected Behavior Contract** table.
- Diagrams use mermaid or ASCII architecture boxes.
