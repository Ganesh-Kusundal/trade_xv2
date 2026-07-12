# Project Overview — TradeXV2 / TradeX Trading OS

> Part of the **Six-File Context System**. Read this first. This file is the
> product vision contract: when a spec is ambiguous, resolve against this, not a guess.
> Code-grounded facts come from `docs/architecture/baseline.md` and
> `docs/architecture/target-layering.md`. Keep it in sync with those docs.

## 1. What This Is (one paragraph)

TradeXV2 is a deployable, **multi-broker algorithmic trading system** that ingests
market data, evaluates strategies against risk, routes orders to Dhan / Upstox / Paper
brokers, manages positions and portfolio, supports replay/backtest, and exposes
capabilities to humans (React Web SPA, FastAPI, Textual TUI, Click CLI) and to agents
(two MCP servers). It is intended to be **continuously releasable and safe with real
money**. Core principle: **backtest, replay, and live execution must share identical
logic** (zero-parity rule).

## 2. Goals (measurable)

1. Broker-agnostic execution — no layer except `runtime/` knows which broker is live.
2. Exchange-agnostic datalake — NSE/IST specifics live in a plugin, not `datalake/core`.
3. Zero-parity between backtest, replay, and live paths (same code, same results).
4. Every deployable build passes architecture tests + import-linter + coverage gates.
5. Local OMS state is reconciled against broker truth on the order-update hot path.
6. Single, stable external Python surface (`tradex`), single CLI, single MCP facade.

## 3. Core User Flow (step-by-step, no gaps)

1. Operator starts a session via CLI (`tradex`) or TUI/Web, selecting a broker profile.
2. `runtime/` resolves the active broker **once at startup** via the `tradex.brokers`
   entry-point group and injects the resolved `BrokerAdapter` into the application layer.
3. Market data flows in through `DataProvider` → `MarketSurface` → strategy evaluation.
4. `TradingOrchestrator.on_candidate` → `ExecutionPlanner.plan` → `OrderPlacer.place`
   → `OrderManager.place_order` → injected `submit_fn` → `make_gateway_submit_fn`.
5. Pre-trade `RiskGate` approves/rejects (replaces the old `getattr` kill-switch
   reach-through). Order is idempotent (single `IdempotencyService`).
6. ExecutionProvider submits to the broker; `on_order_update` events keep the local
   order-book current.
7. `ReconciliationPolicy` heals drift between local `Order`/`Position` and broker state.
8. Portfolio/P&L, observability (tracing/audit), and the human/agent surfaces reflect
   the new state.

## 4. Features (by category)

- **Market Data**: quotes, depth, history, subscription — broker-agnostic via `DataProvider`.
- **Execution / OMS**: order lifecycle, risk gate, idempotency, reconciliation.
- **Portfolio**: positions, P&L, tradebook.
- **Strategy / Analytics**: `LiveStrategyEngine` signal evaluation, option math.
- **Risk**: pre-trade + kill-switch gate (`RiskGate` port).
- **Identity / Auth**: tokens, TOTP, credential resolution (`infrastructure/auth`).
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

## 7. Success Criteria (verifiable, not "looks good")

- `pytest` passes the full suite (7k+ tests) including ~261 architecture/dependency tests.
- `coverage` ≥ 80 overall, ≥ 85 brokers, ≥ 90 OMS.
- import-linter contracts in `pyproject.toml` are green (rules 1–4 CI-blocking).
- A signed-in operator can place, reconcile, and close an order on the active broker.
- `graphify update .` stays current after every code change.

## 8. Source of Truth

- `docs/architecture/baseline.md` — current-state, code-derived.
- `docs/architecture/target-layering.md` — target contract (import-linter rules).
- `docs/architecture/roadmap.md` — 8-phase transformation plan.
- `docs/architecture/backlog.md` — ranked gap inventory (G1–G8).
- `docs/architecture/adr/` — architecture decision records.
