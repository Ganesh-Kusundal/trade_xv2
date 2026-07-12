# Baseline — Current-State Architecture (code-derived)

> ⚠️ **STALE — see `REVIEW.md`.** This snapshot was taken 2026-07-12 at an early point.
> The tree has since moved 190 commits ahead of `main`. Verified-corrected metrics
> (7,472 tests vs "~773"; 261 arch tests vs "56"; ~20 `src/` files >650 LOC despite
> ADR-011; `main` 61 commits behind HEAD) live in `REVIEW.md` §1 and `backlog.md`
> "Backlog Health". Use `REVIEW.md` as the current baseline.

> This document is the Phase 0 deliverable. Every claim is grounded in a file:line
> read of the repository on 2026-07-12. No external documentation was used.

## 1. System Intent (as implemented)

TradeXV2 is a deployable, multi-broker trading system. It ingests market data,
runs strategy/risk evaluation, routes orders to Dhan / Upstox / Paper brokers,
manages positions and portfolio, supports replay/backtest, and exposes
capabilities to humans (Web SPA, FastAPI, Textual TUI, Click CLI) and to agents
(two MCP servers). It is intended to be continuously releasable and safe with
real money.

## 2. Repository Map

```
src/
  domain/            strongly-typed model + ports/events   (clean, no broker imports) ✅
  application/       use-cases (oms, execution, trading, portfolio, strategy_engine, options, ...) ✅
  brokers/           UpstoxBroker (god-facade), DhanBrokerGateway, paper, cli, mcp, events
  infrastructure/    cross-cutting (config, auth, persistence, resilience, idempotency,
                     event_bus, metrics, observability, lifecycle) — internally clean ⚠️ duplicated
  runtime/           composition root + integration glue   🔴 concrete-broker coupling
  datalake/          ingestion, quality, storage, analytics, research, mcp
  market_data/       conventions / MarketSurface
  interface/         ui (Textual), api (FastAPI), agent (tools + MCP)
  config/            Pydantic AppConfig + profiles
tradex/              public package + CLI + session wiring
brokers/             🔴 orphaned shadow copy of src/brokers/dhan/* (2 files)
web/                React/TS SPA
tests/              ~773 tests; 56 architecture/dependency tests
```

## 3. Layered Architecture Assessment

### 3.1 domain — STRONG ✅
- Typed entities: `Order` (`src/domain/entities/order.py:59`), `Position`
  (`src/domain/entities/position.py:30`), `Trade` (`src/domain/entities/trade.py:30`),
  `Portfolio` (`src/domain/portfolio/portfolio.py:24`), `Instrument`
  (`src/domain/instruments/instrument.py:52`), value objects `Money`/`Quantity`.
- Ports (protocols): `BrokerAdapter` = `DataProvider` + `ExecutionProvider`
  (`src/domain/ports/protocols.py:67`, `:184`), `DomainEventBus`
  (`src/domain/events/bus.py:14`), `StrategyEvaluator` (`src/domain/ports/strategy_evaluator.py:12`).
- No inbound imports from brokers/application/infrastructure. Clean.

### 3.2 application — STRONG with two smells ⚠️
- Clean order spine: `TradingOrchestrator.on_candidate`
  (`src/application/trading/trading_orchestrator.py:216`) → `ExecutionPlanner.plan`
  → `OrderPlacer.place` → `OrderManager.place_order`
  (`src/application/oms/order_manager.py:220`) → injected `submit_fn` →
  `make_gateway_submit_fn(gateway)` (`src/application/execution/execution_service.py:53`).
  Transport is passed as a `Callable`, not hardcoded. Good.
- SMELL A — reflection coupling: `trading_orchestrator.py:518-524` reaches into
  `order_manager.risk_manager` via `getattr`. Breaks under rename; no compile-time guard.
- SMELL B — two overlapping strategy-execution paths: `LiveStrategyEngine`
  (`src/application/strategy_engine/engine.py:24`) vs `TradingOrchestrator`
  (which does the evaluate→place loop itself). Overlap, not clean separation.

### 3.3 brokers — PARTIAL ⚠️
- Contract exists as a `runtime_checkable` Protocol, satisfied structurally.
- `UpstoxBroker` is a ~50-adapter god-facade
  (`src/brokers/upstox/broker.py:127-281`) with inline "REF-23 future migration"
  debt notes (`broker.py:115-124`).
- Per-broker duplication of idempotency/risk patterns
  (`src/brokers/upstox/orders/*` docstrings: "Mirrors brokers.dhan.orders...").
- Hard-coded broker/exchange specifics leak:
  `src/brokers/upstox/data_provider.py:37` default `broker_id="upstox"`;
  `src/brokers/dhan/gateway.py:345` `nfo_map = {"NIFTY":"NFO",...}`;
  `src/brokers/dhan/orders.py:52` `_DERIVATIVE_SEGMENTS`.

### 3.4 infrastructure — STRONG internals, DUPLICATED surface ⚠️
- Production-grade: `CircuitBreaker`, `TokenBucketRateLimiter`, `RetryExecutor`
  (`src/infrastructure/resilience/`), `IdempotencyService` with Memory/File/Redis
  caches (`src/infrastructure/idempotency/`), `MetricsRegistry`/`Prometheus`
  (`src/infrastructure/metrics/registry.py:18`), observability stack.
- Internally depends only on `domain.ports`/`domain.events`. Clean.
- DUPLICATION:
  - Two event-bus stacks: `event_bus.py` + `async_event_bus.py`
    (`src/infrastructure/event_bus/`, 8 files incl. `processed_trade_repository.py`).
  - Idempotency service + 3 caches + `ProcessedTradeRepository` overlap.
  - Two config regimes: `src/infrastructure/config/settings.py` loaders
    vs `src/config/schema.py` Pydantic `AppConfig`.

### 3.5 runtime / integration — ARCHITECTURAL WEAK POINT 🔴
- Imports concrete brokers directly, bypassing ports:
  `src/runtime/broker_infrastructure.py:10-39` (`brokers.dhan.*`, `brokers.upstox.*`,
  `application.composer.*`, `application.streaming.*`);
  `src/runtime/broker_accessors.py:34-119`; `src/runtime/session_infra.py:35-38`.
- String-based broker branching: `src/runtime/trading_runtime_factory.py:105`
  `gateway = bs._gateway if bs._active_name == "dhan" else bs._upstox_gateway`.
- This is the single biggest blocker to broker-agnosticism (shotgun surgery).

### 3.6 datalake — NOT exchange-agnostic 🔴
- Bakes in NSE / IST specifics throughout:
  - `src/datalake/core/nse_calendar.py` — NSE holidays 2020–2026 hardcoded.
  - `src/datalake/core/constants.py:50` — `NSE_MARKET_OPEN/CLOSE` = 09:15/15:30.
  - `src/datalake/core/schema.py:25` — `"NSE"`, `"open_paisa"`, paise scaling hardcoded.
  - `src/datalake/adapters/analytics_provider.py:78,122` and
    `src/datalake/research/api.py:63,111` — `exchange="NSE"` defaults.
  - `src/datalake/core/option_format.py:78` — `Sets exchange = "NSE"`.
- `MarketSurface` (`src/market_data/market_surface.py:32`) exists to decouple these
  but is largely ignored by the datalake layer.
- Returns raw `pd.DataFrame` / `dict` lists from `DataLakeGateway`
  (`src/datalake/gateway.py:135/:261/:298`) — typed domain model not enforced on the read path.
- Dead module: `src/datalake/research/fast_backtest.py` raises `ImportError`.

### 3.7 interfaces — STRONG, duplicated MCP ⚠️
- Web (React, `web/src/App.tsx`), FastAPI (`api_server.py:44`), Textual TUI
  (`src/interface/ui/views/tui_app.py`), two Click CLIs (`broker`, `tradex`),
  two MCP servers: `brokers.mcp` (`src/brokers/mcp/server.py:17`, ~24 tools) and
  `agent.mcp` (`src/interface/agent/mcp_server.py:49`).
- 773 tests, 56 architecture/dependency tests, ~18 import-linter contracts.

## 4. Orphaned Shadow Copy 🔴 (silent-failure risk)

`brokers/dhan/gateway.py` and `brokers/dhan/orders.py` at the **repo root** are
divergent duplicates of `src/brokers/dhan/gateway.py` / `src/brokers/dhan/orders.py`.
The root copy imports `from tradex.runtime.capabilities import ...` and
`from brokers.dhan.connection import DhanConnection` — a parallel, drift-prone
implementation. It is kept from shadowing `src/` only by
`src/brokers/_bootstrap.py`, which force-inserts `src/` first on `sys.path` and
deletes a wrongly-cached `domain` module. If path order ever regresses, the stale
root copy is imported silently.

## 5. Reconciliation Gap ⚠️ (silent divergence risk)

`ReconciliationEngine` (`src/domain/reconciliation_engine.py:42`) compares local
`Order`/`Position` against broker state and emits `DriftItem`. But it is a
**separate service**, not on the order-update hot path. The OMS order-book updates
only via `on_order_update` event handlers
(`src/application/oms/order_manager.py:344`). If the broker feed lags or drops
messages, local state silently diverges from broker reality with no automatic heal.

## 6. Engineering Quality (assets to preserve)

- Architecture tests: `tests/architecture/` (layering, domain isolation,
  composition root, module boundaries, file-size, MCP parity).
- import-linter: ~18 contracts in `pyproject.toml` (with `ignore_imports` exceptions
  that document the `runtime/` violations).
- CI: 8 workflows in `.github/` (ci.yml, architecture-enforcement.yml, web.yml,
  production_gate.yml, dhan-regression.yml, mutation_nightly.yml, load-test.yml,
  broker_live_certify.yml).
- Quality gates: ruff, mypy (strict-ish), bandit, safety, coverage
  `fail_under=80` (brokers ≥85, oms ≥90), mutmut 90%.
- Pre-commit: ruff, mypy clean-set, gitleaks, arch tests.

These assets are strong enough to **evolve** the system rather than rewrite it.

## 7. Gap Inventory (ranked, with severity)

| # | Gap | Severity | Evidence |
|---|---|---|---|
| G1 | `runtime/` couples to concrete brokers + string `_active_name` branching | 🔴 | `src/runtime/broker_infrastructure.py:10-39`, `trading_runtime_factory.py:105` |
| G2 | Orphaned shadow `brokers/dhan/*` duplicates `src/brokers/dhan/*` | 🔴 | `brokers/dhan/gateway.py:14`, `src/brokers/_bootstrap.py:11` |
| G3 | Datalake bakes in NSE/IST specifics | 🔴 | `nse_calendar.py`, `constants.py:50`, `analytics_provider.py:78` |
| G4 | Two parallel config systems can drift | ⚠️ | `infrastructure/config/settings.py` vs `config/schema.py` |
| G5 | Duplicated infra (dual event bus, triple idempotency, two MCP, two strategy paths) | ⚠️ | `event_bus/`, `idempotency/`, `brokers.mcp`/`agent.mcp` |
| G6 | Reconciliation off the hot path → silent drift | ⚠️ | `reconciliation_engine.py:42`, `order_manager.py:344` |
| G7 | Reflection `getattr` kill-switch fragility | ⚠️ | `trading_orchestrator.py:518-524` |
| G8 | Ad-hoc scripts (`pytest_runner*.py`, `run_*.sh`, `verify_decomposition.py`) | ⚠️ | repo root |

See `backlog.md` for tracked items, owners, and exit criteria.
