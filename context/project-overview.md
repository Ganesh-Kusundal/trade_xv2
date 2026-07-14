# Project Overview — TradeXV2 / TradeX Trading OS

> Part of the **Six-File Context System**. Read this first. This file is the
> product vision contract: when a spec is ambiguous, resolve against this, not a guess.
> Code-grounded facts come from `docs/architecture/baseline.md` and
> `docs/architecture/target-layering.md`. Keep it in sync with those docs.

## 1. What This Is (one paragraph)

TradeXV2 is a deployable, **multi-broker market analytics and research console** —
a `git`/`kubectl`/`dbt`-style CLI (plus React Web SPA, FastAPI, Textual TUI, and two
MCP servers) for scanning, analyzing, and backtesting strategies against Dhan / Upstox
market data. The broker layer's job is market-data acquisition and lifecycle
(quotes, depth, history, instruments, subscriptions), not order placement — there is
no `order`/`position`/`portfolio` CLI surface. **Execution and order management remain
internal infrastructure**, not a customer-facing product goal: the OMS/RiskManager/
ExecutionEngine kernel exists solely to give backtest, replay, and paper-trading
simulation a single, shared, zero-parity fill path (same code, same results across all
three) so research results are trustworthy — not to route real money. Core principle:
**backtest, replay, and paper analytics must share identical OMS logic** (zero-parity
rule), even though none of them are reachable from a live broker order-placement path.

## 2. Goals (measurable)

1. Analytics-first CLI — the top-level command tree is organized around research
   questions (`scanner`, `pattern`, `support`, `volume`, `market`, `indicator`,
   `strategy`, `backtest`, `report`), not order/position/portfolio.
2. Broker-agnostic market data — no layer except `runtime/` knows which broker is
   live; broker capability is read-only (market data + lifecycle), never execution.
3. Exchange-agnostic datalake — NSE/IST specifics live in a plugin, not `datalake/core`.
4. Zero-parity between backtest, replay, and paper simulation paths (same OMS kernel,
   same code, same results) — this is internal correctness infrastructure for
   research, not a live-trading feature.
5. Every deployable build passes architecture tests + import-linter + coverage gates.
6. Single, stable external Python surface (`tradex`), single CLI, single MCP facade.

## 3. Core User Flow (step-by-step, no gaps)

1. Operator starts a session via CLI (`tradex`) or TUI/Web, selecting a broker profile
   for market-data access (no live-order capability is wired in).
2. `runtime/` resolves the active broker **once at startup** via the `tradex.brokers`
   entry-point group and injects the resolved `BrokerAdapter`'s market-data surface.
3. Market data flows in through `DataProvider` → `MarketSurface` → analytics/strategy
   evaluation (scanners, pattern detection, support/resistance, volume, breadth).
4. Operator inspects results (`tradex scanner breakout`, `tradex analytics symbol X`,
   `tradex support levels X`, `tradex market breadth`, ...) or runs a strategy through
   `tradex backtest` / `tradex analytics replay` / `tradex analytics paper`.
5. Backtest/replay/paper analytics internally construct a broker-free `TradingContext`
   (`application.oms.factory.create_trading_context`) so simulated fills go through
   the identical `OrderManager`/`RiskManager`/`ExecutionEngine` kernel used everywhere
   else in the codebase — this is what makes the simulation trustworthy, not a path to
   real-money execution.
6. Results (equity curve, trade journal, scores, confidence) render via the CLI's
   existing `present()` renderer, or feed the Web/TUI surfaces and MCP tools.

## 4. Features (by category)

- **Market Data**: quotes, depth, history, subscription — broker-agnostic via `DataProvider`.
- **Analytics / Research**: scanner (breakout/volume/momentum/RS), pattern detection,
  support/resistance, volume analytics (profile/spikes/unusual/delivery/delta), market
  breadth, sector rotation/strength, volatility, options Greeks, orderflow, probability,
  ranking, walk-forward, backtest/replay/paper simulation, reports.
- **OMS / Execution kernel (internal only)**: order lifecycle, risk gate, idempotency —
  exists to give backtest/replay/paper a single shared zero-parity fill path; not
  exposed as a CLI command surface.
- **Risk**: pre-trade risk checks inside the shared OMS kernel (used by analytics
  simulation, not a live kill-switch feature).
- **Identity / Auth**: tokens, TOTP, credential resolution (`infrastructure/auth`) —
  scoped to authenticating market-data access.
- **Platform / Infra**: resilience (circuit breaker, rate limiter, retry), persistence,
  config, lifecycle, metrics, observability.
- **Interfaces**: Web (React/TS SPA), FastAPI, Textual TUI, Click CLI, two MCP servers.
- **Datalake**: ingestion, quality monitoring, storage, analytics, research.

## 5. In Scope (what we are building / maintaining)

- Evolutionary refactoring toward `target-layering.md` (no rewrite).
- Plugin model: `tradex.brokers` and (new) `tradex.exchanges` entry-point groups.
- Single event bus, single idempotency service, single config source.
- Architecture-test + import-linter enforcement as CI gates.

## 6. Out of Scope (explicitly NOT building — do not add)

- A second trading language/stack beyond Python+TypeScript.
- Speculative brokers/exchanges not behind a registered plugin.
- New UI component libraries beyond what `web/` already uses.
- Any code that mocks live broker behavior for "tests" (integration tests only).
- Rewriting the domain model — it is the stable core and must not change without an ADR.
- A CLI-facing `order`/`position`/`portfolio` command surface, or any path from the
  CLI/Web/TUI to placing a real order. Execution/order-management may return as a
  separate subsystem or plugin later, but is not part of this product's CLI today.
- Rebuilding or duplicating the OMS/RiskManager/ExecutionEngine zero-parity kernel —
  it already exists and is shared by backtest/replay/paper (see
  `docs/architecture/e2e-spec/21-analytics-research-mode-gap.md`); do not re-propose
  a parity-kernel rewrite for the analytics layer.

## 7. Success Criteria (verifiable, not "looks good")

- `pytest` passes the full suite (7k+ tests) including ~261 architecture/dependency tests.
- `coverage` ≥ 80 overall, ≥ 85 brokers, ≥ 90 OMS.
- import-linter contracts in `pyproject.toml` are green (rules 1–4 CI-blocking).
- An operator can scan a universe, inspect a symbol's analytics (trend/momentum/
  volume/support-resistance), and backtest a strategy end-to-end from the CLI —
  entirely from market data, with zero-parity fills for the simulation.
- `graphify update .` stays current after every code change.

## 8. Source of Truth

- `docs/architecture/baseline.md` — current-state, code-derived.
- `docs/architecture/target-layering.md` — target contract (import-linter rules).
- `docs/architecture/roadmap.md` — 8-phase transformation plan.
- `docs/architecture/backlog.md` — ranked gap inventory (G1–G8).
- `docs/architecture/adr/` — architecture decision records.
