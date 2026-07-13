# Current-State Architecture — TradeXV2 / TradeX Trading OS

> **Audit date:** 2026-07-13 · **Reviewer:** architecture audit (graphify + import-linter + code inspection)
> **Source of truth:** actual working tree at `HEAD = 4d7eb5b5` (graphify graph build commit).
> **Method:** orient with `graphify` (query/explain/path/affected/diagnose), verify with `import-linter`
> and direct code reads. The six-file `context/*.md` and `docs/architecture/*` were treated as
> **untrusted prose** — several claims they make are stale and contradicted below.

---

## 1. Headline Verdict

The system is **structurally disciplined and evolvable, not a rewrite candidate**. Its defining
strength is an **enforced, green import-linter contract (16 contracts, 0 broken)** that makes the
layering rule machine-checked, plus a **pure domain core** and a real **plugin/composition-root**
pattern. The weaknesses are **residual tolerated violations hidden in `ignore_imports`**,
**linter-invisible dynamic broker imports**, **parallel/duplicated infrastructure**, **god objects
exempted from the size gate**, and **pervasive private `getattr` reach-throughs**.

Contradictions with the stale docs (do not plan from the docs alone):
- Docs claim G1 (runtime concrete-broker coupling) is OPEN. **Reality:** import-linter is green;
  concrete-broker imports are confined to `runtime/broker_accessors` + two *dynamic* `importlib`
  sites in `infrastructure` that the linter cannot see.
- Docs claim 3 MCP servers exist. **Reality:** **0 MCP servers exist in `src/`**; references are dead.
- Docs claim G8 (ad-hoc root scripts) is OPEN. **Reality:** **no ad-hoc scripts at repo root**;
  everything lives under `scripts/`.
- Docs claim G7 (`getattr` kill-switch) regressed to 6. **Reality:** **0 `getattr(...,"risk_manager")`
  reach-throughs**; G7 is effectively closed. ~152 *other* private reach-throughs remain.
- Docs claim `main` is 61 commits behind. **Reality:** not re-verified here; branch topology not in scope.

---

## 2. Package Map & Scale (verified)

| Package | LOC | Role |
|---|---|---|
| `brokers/` | 42,291 | Concrete broker adapters (dhan / upstox / paper / common). Largest pkg. |
| `domain/` | 22,581 | Typed entities, ports (Protocols), value objects, events. **Pure.** |
| `interface/` | 21,611 | FastAPI (`api/`), Textual TUI (`ui/`). Presentation over SDK. |
| `analytics/` | 17,994 | Strategy/backtest/replay/indicators/scanners. |
| `infrastructure/` | 16,954 | Adapters: event bus, idempotency, auth, resilience, persistence, observability. |
| `application/` | 16,843 | Use-cases: oms, execution, trading, portfolio, strategy_engine, options. |
| `datalake/` | 9,278 | DuckDB ingestion/quality/storage/analytics/research. |
| `config/` | 2,511 | `AppConfig` Pydantic schema. |
| `runtime/` | 1,975 | Composition root (ONLY sanctioned concrete-broker importer). |
| `tradex/` | 1,136 | Public SDK package + CLI. |
| **Total `src/`** | **153,466** | 1,123 modules |

Tests: **798 test files / 7,629 `def test_` / 62 architecture-test files**. Coverage gates:
overall ≥80, brokers ≥85, OMS ≥90 (from `pyproject.toml`).

---

## 3. Layering & Dependency Model (verified)

The dependency rule is encoded as 16 `import-linter` contracts in `pyproject.toml`
(`[tool.importlinter]`, root_packages = domain/brokers/analytics/datalake/interface/application/
infrastructure/tradex/runtime/config). **`lint-imports` reports `Contracts: 16 kept, 0 broken`.**

Intended direction (also see `context/architecture.md` §3):

```
interface/ ─▶ runtime/ ─▶ application/ ─▶ domain/
                 └────▶ infrastructure/ ─▶ domain/
brokers/ (plugins, only imported by runtime/)
```

Enforced contracts (names): *Domain independence*, *Infrastructure independence*, *Analytics
broker-adapter isolation*, *Trading does not import Analytics (D2)*, *Analytics does not import
Trading OMS/execution (D2 inverse)*, *Broker common isolation*, *Application broker isolation*,
*Analytics does not import interface*, *Dispatcher broker isolation*, *Runtime does not import
interface*, *Runtime broker-implementation isolation*, *Application infrastructure separation*,
*CLI broker-implementation isolation*, *API broker-implementation isolation*, *Tradex public API
broker isolation*, *UI uses connect shims not raw factory*.

**Verified facts:**
- **Domain is PURE** — zero inward imports (grep of `src/domain` for any `application/infrastructure/
  brokers/interface/runtime` import → none). ✅
- **`tradex` no longer imports concrete brokers** — the "Tradex public API broker isolation" contract
  passes; routing goes through `runtime.broker_discovery` + `infrastructure.adapter_factory`.
- **`runtime` is the sanctioned concrete-broker importer** via `runtime/broker_accessors.py`, but the
  contract still needs 5 `ignore_imports` exceptions for it (see §6).

---

## 4. Runtime Flows (verified via graphify path/explain)

### 4.1 Order execution
`CANDIDATE_GENERATED` event → `TradingOrchestrator.on_candidate` (`application/trading/
trading_orchestrator.py:223`) → `CandidateEvaluator` (feature fetch + `StrategyEvaluator`,
`:331-341`) → `ExecutionPlanner.plan` (`execution_planner.py:54`, called `:300`; SignalDTO →
`OmsOrderCommand` with gating/quantity) → `OrderPlacer.place` (`order_placer.py:87`, called `:318`).
OrderPlacer has a 3-tier fallback (`:119-130`): `order_command_fn` (ADR-012) → `ExecutionService.
place_order` → `PlaceOrderUseCase.execute` → `OrderManager.place_order` (`oms/order_manager.py:220`).
Risk + broker submit happen in `OrderManager`: `OrderValidator.build_and_validate` (`:241`) then
`OrderLifecycle.submit_to_broker` (`_internal/order_lifecycle.py:94`) → `submit_fn(request)` (`:134`).

### 4.2 Market data
Broker feeds (`DhanMarketFeed` `brokers/dhan/websocket/market_feed.py:41`, `DhanOrderStream`,
`UpstoxPortfolioStream`) publish ticks/order events onto the `EventBus`. Strategy evaluation path:
`DataProvider`/`FeatureFetcher` (`domain/ports/protocols.py:67`) → `CandidateEvaluator.fetch_features`
(`trading_orchestrator.py:331`) → `StrategyEvaluator.evaluate_candidate` → `StrategyPipeline`
(`trading/multi_strategy_runtime.py:27`). `MarketSurface` (`domain/capabilities/market_surface.py:30`)
is the declarative coverage source of truth (not on the live tick→strategy hot line).

### 4.3 Reconciliation (hot-path status)
`ReconciliationService` (`application/oms/reconciliation_service.py:35`) runs a **detached daemon
thread** (`_loop`, `:164`). It IS wired to the hot path: `context.py:311-318` subscribes
`request_reconciliation` to `TRADE_APPLIED` and `ORDER_UPDATED` (coalesced `:135-143`). Drift emits
`RECONCILIATION_DRIFT` (`reconciliation_service.py:263`; enum `domain/events/types.py:88`). **There is
NO `POSITION_DRIFT` event** — only `RECONCILIATION_DRIFT`. Broker-side adapters exist in
`brokers/dhan/portfolio/reconciliation.py:47`, `brokers/upstox/reconciliation`, `brokers/common/
recon_local.py`.

### 4.4 Risk gate
Pre-trade approval: `OrderValidator.build_and_validate` (`oms/order_validator.py:85`) checks placement
gate (`:97`) then `RiskManagerPort.check_order` (`:132`; port `domain/ports/risk_manager.py`).
Kill-switch via injected `RiskManagerPort` (`trading_orchestrator.py:148`, `_is_kill_switch_active`
`:519`). `RiskGate` (`domain/risk/policy.py:160`) composes policies. **G7 (`getattr` kill-switch) is
closed — 0 `getattr(...,"risk_manager")` reach-throughs.**

### 4.5 Strategy spines & zero-parity
**One canonical spine:** `TradingOrchestrator`. `LiveStrategyEngine` was removed/dead
(`application/strategy_engine/__init__.py:3`). `MultiStrategyRuntime` only builds a `StrategyPipeline`
— not a competing execution spine. Zero-parity holds: backtest/replay/live share `StrategyPipeline` +
`MarketSurface`; live uses `OrderManager`→`submit_fn`, replay uses `EventLogReplayService`.

---

## 5. Domain Model (verified)

- **Entities/value objects:** `domain/entities/*` (instrument, order, position, trade, market, account),
  `domain/value_objects/*`, `domain/orders/*`, `domain/portfolio/*`.
- **Ports (Protocols):** `domain/ports/*` — `BrokerAdapter`, `DataProvider`, `ExecutionProvider`,
  `BrokerTransport`, `EventBusPort`, `RiskManagerPort`, `StrategyEvaluator`, `ClockPort`,
  `ExchangeAdapter`, `TradingCalendar`.
- **Events:** `domain/events/*` — immutable `DomainEvent` subclasses keyed by `EventType`
  (`domain/events/types.py`).
- **Purity:** confirmed (§3). No broker-specific types leak into `domain` via imports; the only
  concern is **duplicate domain types defined inside broker packages** (§6).

---

## 6. External Surfaces (verified)

| Surface | Status | Evidence |
|---|---|---|
| CLI #1 `tradex` | present | `tradex = tradex.cli:tradex` (`pyproject.toml:34`) |
| CLI #2 `broker` | present | `broker = brokers.cli.broker:broker` (`pyproject.toml:33`) |
| FastAPI | present | `interface/api/main.py:289`, served by `scripts/run_api_server.py:45` |
| TUI (Textual) | present | `interface/ui/main.py` |
| MCP servers | **0 exist** | no `FastMCP`/`mcp.server` in `src/`; `broker-mcp` entry-point is dead; `scripts/verify/test_mcp_integration.py:13` imports missing `datalake.mcp.server` |
| SDK (`tradex`) | present | `src/tradex/`; but `__init__.py:43-56` imports `domain.instruments.*` directly (not fully decoupled) |

The "single CLI / single MCP / single SDK" target is **partially met**: two CLIs remain; MCP is
absent (docs are wrong about 3 servers); SDK exists but bleeds into `domain` internals.

---

## 7. Cross-Cutting Infrastructure

- **Event bus:** `infrastructure/event_bus/` — sync `EventBus` (`event_bus.py:49`, 587 LOC) +
  `AsyncEventBus` (`async_event_bus.py:56`) which **wraps the sync bus** (`event_bus()` → `EventBus`,
  `:218`) + `factory.py` (`AsyncEventBusFactory`) + `processed_trade_repository.py` (437) + dead-letter
  queue. Effectively **one core + one thin async wrapper**, but `ProcessedTradeRepository` is a
  separate durable track.
- **Idempotency:** **3 distinct implementations** — (a) `infrastructure/idempotency/`
  (`IdempotencyService`, `service.py:61`; `MemoryIdempotencyCache`, `memory_cache.py:34`); (b)
  `brokers/common/idempotency.py` (`IdempotencyCache` `:54`, TTL cache — duplicates (a)); (c)
  `application/oms/idempotency_guard.py:19` (`IdempotencyGuard` — third ad-hoc guard).
- **Config:** **2 live systems** — `AppConfig` (`config/schema.py:22`, `from_env` `:65`) and
  `SettingsLoaderBase` (`infrastructure/config/settings.py:46`) + `DhanSettingsLoader`
  (`brokers/dhan/config/settings.py:112`) + `UpstoxSettingsLoader` (`brokers/upstox/auth/config.py:152`).
- **Auth:** `infrastructure/auth/` — tokens, TOTP, credential resolution.
- **Resilience:** `infrastructure/resilience/` — circuit breaker, rate limiter, retry.
- **Observability:** `infrastructure/observability/` — tracing, audit, alerting (`alerting.py` 598 LOC).

---

## 8. Code-Smell Metrics (verified)

| Metric | Count | Notes |
|---|---|---|
| `getattr(x, "_private")` reach-throughs | **152** | mostly `interface/` + `infrastructure/`; 5 touch `order_manager`/`context` |
| `broad except Exception:` | 100+ | rarely silently swallowed (0 empty `except: pass`) |
| builtin `print()` (vs logging) | **174** | +611 `console.print` (rich, acceptable) |
| `import *` (star) | **39** | e.g. `brokers/services/core.py:25-31` |
| `global` statements | **34** | e.g. `interface/api/deps.py:48`, `runtime/event_loop.py:54` |
| TODO/FIXME/HACK/XXX | 3-4 | plus **12 `ponytail:`** markers |
| exceptions outside `TradeXV2Error` taxonomy | **10** | e.g. `WebhookAuthError(Exception)`, `CapabilityMismatchError(RuntimeError)` |
| God objects >650 LOC | 4 raw (20 exempted) | replay/engine 826, depth_feed_base 722, oms/context 688, api/schemas 678 |

Full evidence in `AUDIT-prioritized-findings.md`.

---

## 9. What Is Genuinely Good (preserve)

- **Green, enforced layering contract** (import-linter) — rare and valuable; keep it the gate.
- **Pure domain core** — no inward imports; stable, typed.
- **Plugin/composition-root pattern** — `runtime` is the sanctioned broker importer.
- **Single canonical execution spine** + zero-parity path shared by backtest/replay/live.
- **Risk gate as an injected port** (G7 closed).
- **Reconciliation on the order-update hot path** via event subscription.
- **Large, real integration test suite** (7,629 tests) — enables safe refactoring.
