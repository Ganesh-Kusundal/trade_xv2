# Target Architecture & Layering

> The contract that every later phase refactors toward. Adapted from `baseline.md`.
> This is the single source of truth for the import-linter rules written in Phase 1.

## 1. Dependency Rule (enforced by import-linter)

```
interfaces/      ──▶  runtime/ (composition root ONLY touches concretes)
runtime/         ──▶  infrastructure/ (adapters)  +  application/ (use-cases)
infrastructure/  ──▶  application/  (implements domain ports)
application/     ──▶  domain/  (entities, ports, events)
domain/          ──▶  (NOTHING inward — depends only on stdlib + itself)
```

Hard rules:
1. `domain` may not import from `application`, `infrastructure`, `runtime`, `brokers`, `interface`.
2. `application` may not import from `infrastructure`, `runtime`, `brokers`, `interface`.
3. `infrastructure` may not import from `runtime`, `interface`. It imports `domain` ports only.
4. `runtime` is the ONLY layer permitted to import concrete brokers/plugins. All broker
   selection happens here via plugin discovery — never via string branching anywhere else.
5. `interface` may import `application` and `runtime`; it may never import `brokers` directly.

Violations of rules 1–4 are CI-blocking (import-linter contract). Rule 5 is a warning.

## 2. Bounded Contexts

| Context | Home | Responsibility |
|---|---|---|
| Market Data | `domain` + `infrastructure/providers` | quotes, depth, history, subscription (broker-agnostic) |
| Instruments | `domain/instruments` | canonical instrument model, symbol↔id mapping |
| Execution / OMS | `application/oms`, `application/execution` | order lifecycle, risk gate, idempotency, reconciliation |
| Portfolio | `application/portfolio`, `domain/portfolio` | positions, P&L, tradebook |
| Risk | `application/oms/risk` (port) | pre-trade + kill-switch gate |
| Strategy / Analytics | `application/strategy_engine`, `application/options` | signal evaluation, option math |
| Identity / Auth | `infrastructure/auth` | tokens, TOTP, credential resolution |
| Platform / Infra | `infrastructure/*` | resilience, persistence, config, lifecycle, metrics, observability |
| Observability | `infrastructure/observability` | tracing, audit, alerting |
| Exchange (NEW) | `domain/ports` + plugin | trading calendar, exchange-specific conventions |

## 3. Stable Contracts First

Order of stabilization (do not implement before contracts freeze — Phase 1):
1. `BrokerAdapter` Protocol (`DataProvider` + `ExecutionProvider`) — already exists
   (`src/domain/ports/protocols.py:67,184`). Freeze as-is; no new methods without ADR.
2. `ExchangeAdapter` Protocol (NEW) — abstracts trading calendar, session hours,
   symbol/exchange naming, tick-size, lot-size, currency/paise conventions.
3. `TradingCalendar` Protocol (NEW) — `is_trading_day`, `session_bounds`, `expected_bars`.
4. `DomainEventBus` Protocol — already exists; one canonical implementation (Phase 1 ADR).
5. `RiskGate` Protocol (NEW) — replaces the `getattr` kill-switch reach-through.
6. `ReconciliationPolicy` — wires drift healing into the order-update hot path.

## 4. Plugin Model

### 4.1 Broker plugins
- Discovered via the `tradex.brokers` entry-point group (already declared in
  `pyproject.toml:60-72`).
- A plugin is any object satisfying `BrokerAdapter`. Registration returns
  `(broker_id, BrokerAdapter)`; selection is by `broker_id` enum, **never** by
  string equality scattered across modules.
- `runtime/` resolves the active broker once, at startup, and injects the resolved
  adapter into the application layer as a `Callable`/`Protocol`. No other layer knows
  which broker is live.

### 4.2 Exchange plugins (NEW)
- New entry-point group `tradex.exchanges`.
- Each exchange plugin provides `ExchangeAdapter` + `TradingCalendar`.
- Datalake imports exchange conventions ONLY through the active `ExchangeAdapter`.
  NSE/IST defaults move OUT of `src/datalake/core/*` into the NSE exchange plugin.
- Until an exchange plugin is registered, datalake/capabilities raise
  `ExchangeNotConfigured` rather than silently defaulting to `"NSE"`.

## 5. Event Model
- One canonical `EventBus` (sync) with an `AsyncEventBus` facade over the same core.
  The current dual `event_bus.py` / `async_event_bus.py` are merged into one core +
  one thin async wrapper (Phase 1 ADR).
- Events are immutable `DomainEvent` subclasses with `EventType` (`domain/events/types.py`).
- Every publish path captures handler failures to a `DeadLetterQueue` by default.
- Idempotency: a single `IdempotencyService` (Memory/File/Redis caches unified),
  replacing the duplicate `ProcessedTradeRepository`.

## 6. Public SDK & Surfaces
- **One** external Python surface: the `tradex` package (already the public package).
- **One** CLI: consolidate `broker` + `tradex` into `tradex` (Phase 4).
- **One** MCP server: merge `brokers.mcp` + `agent.mcp` into a single facade that
  reuses the same guardrail/validation path (Phase 4). Tool schemas are stable contracts.
- Web/API/TUI remain as presentation layers over the SDK.

## 7. Target Package Skeleton (evolutionary, not a rewrite)

```
src/domain/            (unchanged core; + ports for Exchange/TradingCalendar/RiskGate)
src/application/       (unchanged; RiskGate injected, single strategy spine)
src/infrastructure/    (adapters; single event bus, single idempotency, single config)
src/runtime/           (composition root; ONLY place with concrete broker/exchange imports)
src/interface/         (web/api/tui/agent over SDK)
src/plugins/
  brokers/dhan/        (moves out of src/brokers as entry-point plugin)
  brokers/upstox/
  brokers/paper/
  exchanges/nse/       (NSE calendar + conventions extracted from datalake)
```

Note: `src/brokers/` becomes `src/plugins/brokers/` (or a separate installable
package) so the broker code is physically a plugin, not a first-class layer. The
orphaned repo-root `brokers/` shadow copy is deleted (see ADR-001 / backlog G2).
