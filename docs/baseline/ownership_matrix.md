# D0.3 — Module Ownership Matrix

> Auto-generated from codebase analysis. Assign team/agent owners as needed.

## Ownership Assignment

| Module | Files | LOC | Primary Owner | Backup Owner | Notes |
|--------|------:|----:|---------------|-------------|-------|
| `src/domain/` | 205 | ~18K | TBD | TBD | Core domain model, must remain import-isolated |
| `src/application/` | 86 | ~9K | TBD | TBD | OMS, trading, streaming, portfolio |
| `src/brokers/` | 305 | ~42K | TBD | TBD | Largest module — broker plugins, services, CLI, MCP |
| `src/infrastructure/` | 120 | ~12K | TBD | TBD | DI, event bus, lifecycle, persistence, gateway |
| `src/analytics/` | 97 | ~11K | TBD | TBD | Indicators, backtest, replay, strategy, scanner |
| `src/datalake/` | 57 | ~6K | TBD | TBD | Parquet storage, DuckDB catalog, data quality |
| `src/interface/` | 157 | ~16K | TBD | TBD | API, CLI (UI), Agent, MCP server |
| `src/config/` | 14 | ~1.5K | TBD | TBD | Pydantic config, feature flags, profiles |
| `src/tradex/` | 5 | ~1.5K | TBD | TBD | CLI entry point, session bootstrap |
| `tests/` | 897 | ~90K | TBD | TBD | Full test pyramid |
| `scripts/` | 49 | ~3K | TBD | TBD | Audit, verify, debug, migration scripts |
| `web/` | — | — | TBD | TBD | React frontend |

## Sub-Module Ownership (Key Areas)

### `src/brokers/` Sub-Modules

| Sub-Module | Files | Description | Owner |
|-----------|------:|-------------|-------|
| `brokers/dhan/` | ~150 | Dhan live broker adapter | TBD |
| `brokers/upstox/` | ~100 | Upstox live broker adapter | TBD |
| `brokers/paper/` | ~10 | Paper trading simulator | TBD |
| `brokers/common/` | ~20 | Shared broker code (ACL, idempotency, validation) | TBD |
| `brokers/certification/` | ~10 | Broker certification suite | TBD |
| `brokers/diagnostics/` | ~6 | Doctor, health, benchmark | TBD |
| `brokers/services/` | ~2 | Single service core (SDK/CLI/MCP) | TBD |
| `brokers/session/` | ~3 | BrokerSession public API | TBD |
| `brokers/runtime/` | ~4 | RuntimeBundle coordinators | TBD |
| `brokers/cli/` | ~5 | Interactive CLI shell | TBD |
| `brokers/mcp/` | ~3 | MCP server (FastMCP) | TBD |
| `brokers/extensions/` | varies | Extension implementations | TBD |

### `src/domain/` Sub-Modules

| Sub-Module | Files | Description | Owner |
|-----------|------:|-------------|-------|
| `domain/instruments/` | 15 | Instrument aggregate | TBD |
| `domain/events/` | 4 | Domain events (types.py is 1008 LOC — needs split) | TBD |
| `domain/orders/` | 6 | Order aggregate | TBD |
| `domain/portfolio/` | 4 | Portfolio aggregate | TBD |
| `domain/ports/` | 28 | Port interfaces (Protocol definitions) | TBD |
| `domain/capabilities/` | varies | Capability system | TBD |
| `domain/capability_manifest/` | varies | Capability catalog (905 LOC — needs split) | TBD |
| `domain/quotes/` | varies | Quote/depth models | TBD |
| `domain/candles/` | varies | Candle/historical models | TBD |
| `domain/value_objects/` | 6 | Value objects (Money, Price, etc.) | TBD |
| `domain/risk/` | 3 | Risk domain | TBD |
| `domain/universe.py` | 1 | Instrument universe (808 LOC — needs split) | TBD |

### `src/application/` Sub-Modules

| Sub-Module | Files | Description | Owner |
|-----------|------:|-------------|-------|
| `application/oms/` | ~15 | Order Management System (TradingContext is 809 LOC) | TBD |
| `application/trading/` | ~5 | Trading orchestrator (807 LOC) | TBD |
| `application/streaming/` | ~6 | Tick routing, candle aggregation | TBD |
| `application/portfolio/` | ~3 | Portfolio service | TBD |
| `application/execution/` | ~7 | Order execution (live/paper/replay) | TBD |
| `application/strategy_engine/` | ~2 | Strategy engine | TBD |
| `application/data/` | ~3 | Historical data coordination | TBD |
| `application/scheduling/` | ~2 | Quota scheduling | TBD |
| `application/composer/` | ~3 | Application composition | TBD |

### `src/infrastructure/` Sub-Modules

| Sub-Module | Files | Description | Owner |
|-----------|------:|-------------|-------|
| `infrastructure/event_bus/` | ~5 | Event bus + DLQ | TBD |
| `infrastructure/lifecycle/` | ~1 | Managed service lifecycle | TBD |
| `infrastructure/gateway/` | ~5 | Gateway factory + bootstrap | TBD |
| `infrastructure/persistence/` | ~2 | SQLite stores | TBD |
| `infrastructure/di.py` | 1 | DI container | TBD |
| `infrastructure/adapters/` | ~3 | Adapter bridges | TBD |
| `infrastructure/security/` | ~3 | Secrets, SSL, webhook auth | TBD |
| `infrastructure/metrics/` | ~3 | Metrics + Prometheus export | TBD |
| `infrastructure/observability/` | ~7 | Alerting, tracing, health | TBD |

## Ownership Rules

1. **Every module must have exactly one primary owner** responsible for:
   - Code review of all changes
   - Architecture compliance
   - Test coverage maintenance
   - Documentation currency

2. **Cross-module changes** require approval from both module owners

3. **Domain layer changes** require architecture review (domain must remain import-isolated)

4. **Public API changes** (SDK, CLI, MCP, REST) require ADR

5. **Owner assignment** should be updated in this file when team changes occur

## How to Claim Ownership

1. Update the "Primary Owner" column with your name/team ID
2. Ensure you have reviewed the module's architecture tests
3. Add yourself to CODEOWNERS if using GitHub
4. Review the module's test coverage in `docs/baseline/test_coverage_map.md`
