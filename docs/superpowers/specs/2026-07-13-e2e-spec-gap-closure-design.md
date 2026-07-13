# E2E Spec Gap Closure — Design Spec

**Date:** 2026-07-13  
**Status:** Draft  
**Author:** MiMoCode (auto)  
**Scope:** Close the remaining gaps between the E2E architectural specification suite (`docs/architecture/e2e-spec/`) and the current codebase.  
**Reference:** E2E spec docs 00–12, `context/architecture.md`, `context/progress-tracker.md`

---

## 1. Problem Statement

The E2E spec suite (Nautilus-referenced) defines what TradeXV2 must become for real-money NSE/IST trading. A review against the current codebase reveals **3 critical (🔴) gaps** and **4 moderate (⚠️) gaps** that block the system from meeting its safety and parity contracts.

### Critical gaps (must close before any real-money claim)

| ID | Gap | Spec invariant | Risk |
|---|---|---|---|
| G-EXEC | Dual execution paths: `ExecutionService` (live) + `SimulatedOMSAdapter` (paper/replay) + `PaperOrders._place_internal` (legacy bypass) | I1 Zero-Parity | Live and sim produce different order streams; replay cannot validate live behavior |
| G-CLOCK | 126 `datetime.now()` calls across `src/` in execution, risk, and domain paths | I2 Deterministic Time | Replay produces non-deterministic timestamps; risk checks use wall clock |
| G-STORAGE | OMS/ledger/events co-located under `market_data/` alongside Parquet lake; dual DuckDB catalogs | §12 Market Data | Operator deleting "market data" wipes order history; split-brain catalog risk |

### Moderate gaps (should close for spec compliance)

| ID | Gap | Spec invariant | Risk |
|---|---|---|---|
| G-RECON | Reconciliation apply semi-detached (service thread, not inside ExecutionEngine) | I6 Hot-path reconcile | Phantom positions possible between apply and next check_order |
| G-CACHE | `TradingCache` exists but isn't primary read path for Risk/Strategy | §02.2 TradingCache | Risk/Strategy read stale dicts, not cache-then-publish |
| G-DATAFLOW | No `DataEngine` enforcing cache-then-publish ordering | §05 Data Flow | Subscribers may see event before cache is updated |
| G-PAPER-BYPASS | `PaperOrders._place_internal` bypasses OMS idempotency, risk, and event spine entirely | I1 + I8 | Paper trading doesn't exercise the real order path |

---

## 2. Design Principles

1. **Evolutionary, not rewrite.** Move production wiring to existing spec-compliant classes; delete forbidden paths. No new abstractions.
2. **YAGNI ruthlessly.** The spec already defines the target. Don't add features, abstractions, or middleware beyond what the spec requires.
3. **Fail-closed at every gate.** Any dependency fault in a risk check → deny. No "warn and continue" in money paths.
4. **Structural parity, not asserted parity.** Zero-parity must come from a single code path, not from tests asserting two paths produce the same result.
5. **One question at a time.** Each phase delivers one invariant closure; merge only when green.

---

## 3. Proposed Approach

### Phase A — Close Silent Money Bugs (no structural redesign)

**Goal:** Eliminate the dangerous `datetime.now()` calls in execution and domain paths. Ship as small, low-risk PRs.

#### A1: Clock injection in fill builders

**What changes:**
- `application/oms/trade_recorder.py:215` → inject `ClockPort` instead of `datetime.now(timezone.utc)`
- `application/oms/order_validator.py:111,128` → inject `ClockPort`
- `application/oms/_internal/order_lifecycle.py:129` → inject `ClockPort`
- `application/execution/gateway_submit.py:34` → inject `ClockPort`
- `domain/entities/market.py:219,227,264,339,345` → inject `ClockPort` into constructors/factories
- `domain/execution_contracts.py:82,91,100` → inject `ClockPort`
- `application/trading/trading_orchestrator.py:539` → inject `ClockPort`

**What stays:**
- `datetime.now()` in `RealClock` / `SystemClock` implementations (these ARE the clock)
- `datetime.now()` in interface/display code (UI timestamps, health endpoints)
- `datetime.now()` in datalake/analytics (non-execution paths)
- `datetime.now()` in infrastructure (auth tokens, event log flush timers)

**Acceptance:**
- `rg "datetime\.now" src/application/execution/ src/application/oms/ src/domain/entities/ src/domain/execution_contracts.py src/application/trading/trading_orchestrator.py` returns zero matches (excluding comments/strings)
- Architecture grep test: `datetime.now` forbidden in listed execution paths
- Existing tests pass; new tests verify clock-injected paths use `FakeClock`

#### A2: PaperOrders legacy bypass retirement

**What changes:**
- `brokers/paper/paper_orders.py` → delete `_place_internal` (lines 244-362), the legacy no-OMS path
- Paper orders route through `_place_via_oms` exclusively
- `_place_via_oms` uses `SimulatedFillSource` (not its own fill closure)

**What stays:**
- `PaperOrders.place_order` as the entry point (thin adapter)
- `_place_via_oms` as the single internal path

**Acceptance:**
- `PaperOrders._place_internal` no longer exists
- Paper place_order goes through `OrderManager.place_order` → `RiskManager.check_order` → `IdempotencyGuard`
- Existing paper tests pass

### Phase B — Structural Zero-Parity (Nautilus-aligned)

**Goal:** Promote `ExecutionEngine` to the single production entry. Delete `ExecutionService` mode branching and `SimulatedOMSAdapter`.

#### B1: Wire ExecutionEngine as the single production entry

**What changes:**
- `runtime/trading_runtime_factory.py` → instantiate `ExecutionEngine(fill_source=BrokerFillSource(gateway), trading_context=ctx)` for live mode
- `interface/ui/services/cli_broker_facade.py:177` → use `ExecutionEngine` instead of `ExecutionService(mode="live")`
- `application/execution/execution_service.py` → delete mode branching; if kept, thin wrapper that delegates to `ExecutionEngine`

**What stays:**
- `ExecutionEngine` class (already spec-compliant)
- `FillSource` protocol + `BrokerFillSource` / `SimulatedFillSource`

**Acceptance:**
- Single `place_order` entry: `ExecutionEngine`
- Live and paper both go through `ExecutionEngine` with different `FillSource`
- `ExecutionService.mode` branching is deleted
- `ExecutionModeAdapter` / `SimulatedOMSAdapter` are deleted
- `OmsBacktestAdapter` uses `ExecutionEngine(fill_source=SimulatedFillSource(...))`

#### B2: Reconcile apply inside ExecutionEngine

**What changes:**
- `ExecutionEngine.apply_mass_status` becomes the sole reconcile apply path (it already exists at `execution_engine.py`)
- `ReconciliationService._run_once` delegates apply to `ExecutionEngine` (already partially done at line 207)
- Remove the separate `DhanReconciliationService._repair_local_oms` as the primary apply; it becomes a fallback for broker-specific normalization only

**Acceptance:**
- After broker mass-status, `ExecutionEngine.apply_mass_status` is called (not a detached timer applying independently)
- `RECONCILIATION_COMPLETED` event published by `ExecutionEngine`, not the service

#### B3: TradingCache as primary read path

**What changes:**
- `RiskManager` reads from `TradingCache` instead of `OrderManager` dicts
- `TradingOrchestrator` / `StrategyPipeline` read from `TradingCache`
- `ExecutionEngine` writes to `TradingCache` on every order/fill mutation

**Acceptance:**
- `TradingCache` is the only read path for risk and strategy
- `OrderManager`/`PositionManager` dicts are write-only (or deleted if redundant)

### Phase C — Risk Parity (spec §07)

Already done (TradingState + Throttler + fail-closed instrument lookup + daily PnL self-heal). No code changes needed. Verify with existing tests.

### Phase D — Market Data Storage Split (spec §12)

**Goal:** Separate lake (Parquet) from state (SQLite) from code (`src/market_data`).

#### D1: Config spine

- Add `DataPaths` to `AppConfig` (or domain value object): `lake_root`, `state_root`, `catalog_path`
- Wire composition root to inject paths
- Default to current locations for zero-downtime

#### D2: Physical split

- Create `data/lake/` and `data/state/`
- Move Parquet + `catalog.duckdb` → `data/lake/`
- Move `oms_orders.sqlite`, `execution_ledger.sqlite`, `events/`, `live_snapshot.json` → `data/state/`
- Leave `market_data/` as compat symlink for one release

#### D3: Naming cleanup

- Rename `domain.capabilities.MarketSurface` → `MarketCoverage`
- Move `src/market_data/market_surface.py` into exchange plugin or domain
- Delete `src/market_data/` package

---

## 4. Architecture Decisions

### AD-1: ExecutionEngine is the sole place_order entry

**Decision:** All order placement goes through `ExecutionEngine` with a `FillSource` dependency. No mode branching, no adapter wrappers.

**Rationale:** The spec (doc 06 §5) explicitly forbids separate `SimulatedOMSAdapter.place_order`. The `ExecutionEngine` already exists and is spec-compliant. Promoting it to production is a wiring change, not a rewrite.

**Tradeoff:** Requires deleting `ExecutionService` mode branching and `SimulatedOMSAdapter`. This is ~200 lines of production code + test updates, but eliminates the forbidden dual path.

### AD-2: Clock injection is mandatory in execution paths

**Decision:** All timestamps in `Order`, `Trade`, `ExecutionContract`, and `DomainEvent` construction must come from an injected `ClockPort`. `datetime.now()` is forbidden in these paths.

**Rationale:** The spec (I2) and Nautilus `TestClock`/`LiveClock` pattern require deterministic replay. Wall clock in execution paths breaks this invariant.

**Tradeoff:** Some infrastructure paths (auth tokens, event log flush) legitimately use wall clock. The rule is scoped to execution/risk/domain paths, not global.

### AD-3: Reconciliation apply lives in ExecutionEngine

**Decision:** `ExecutionEngine.apply_mass_status` is the sole reconcile apply path. The `ReconciliationService` triggers and orchestrates but does not apply.

**Rationale:** The spec (I6) requires hot-path reconcile inside the engine. A detached service applying drift creates phantom positions between ticks.

**Tradeoff:** The `ReconciliationService` becomes thinner (trigger + orchestrate only). Broker-specific normalization stays in broker adapters but funnels through `ExecutionEngine`.

---

## 5. Risk Assessment

| Risk | Mitigation |
|---|---|
| Deleting `ExecutionService` breaks existing callers | Grep for all import sites before deletion; update each |
| Clock injection changes break existing tests | Run full suite after each A1–A7 sub-step |
| Paper trading regression after `_place_internal` deletion | Paper tests exercise `_place_via_oms` path; add regression test |
| Storage split breaks CWD-relative paths | Defaults point at current locations; physical move is Phase 2 |
| `TradingCache` as read path misses data | Keep `OrderManager`/`PositionManager` as write-through until cache is verified |

---

## 6. Testing Strategy

### Per-phase tests

- **Phase A:** Architecture grep test for `datetime.now` in execution paths; unit tests for clock-injected builders using `FakeClock`
- **Phase B:** Integration test: single `ExecutionEngine` with `BrokerFillSource` → order placed, filled, reconciled. Integration test: `SimulatedFillSource` → identical risk decisions and position projections
- **Phase D:** Config injection test; path resolution test; compat symlink test

### Spec acceptance tests (from doc 11 §3)

1. **Replay determinism:** same catalog + `FakeClock` ⇒ identical order stream (timestamps included)
2. **Risk deny never hits venue:** mock `FillSource`; kill-switch on ⇒ zero submit calls
3. **Reconcile heals phantom position:** inject local-only open position; mass-status empty ⇒ flat before next `check_order`
4. **Idempotent place:** double place same `correlation_id` ⇒ one venue submit
5. **Illegal order transition:** FILLED → OPEN raises `IllegalTransitionError`
6. **Clock purity:** CI grep forbids `datetime.now` in execution/risk/domain paths

---

## 7. Success Criteria

1. Single `ExecutionEngine` is the production entry for all modes (live, paper, backtest)
2. Zero `datetime.now()` in execution/risk/domain timestamp construction
3. `ReconciliationService` orchestrates; `ExecutionEngine.apply_mass_status` applies
4. `TradingCache` is the primary read path for risk and strategy
5. `data/lake/` and `data/state/` separated (or config-ready for separation)
6. All 6 spec acceptance tests pass
7. Full test suite green (existing 7k+ tests)

---

## 8. Open Questions

1. **Should `ExecutionService` be deleted or kept as a thin wrapper?** The spec says the engine is the entry. `ExecutionService` adds mode branching that the spec forbids. Recommend: delete, update callers.
2. **Should `PaperOrders._place_via_oms` keep its own fill closure, or use `SimulatedFillSource`?** Recommend: use `SimulatedFillSource` for consistency, but this requires `SimulatedFillSource` to accept market fill logic (slippage model). Current `SimulatedFillSource` wraps `make_simulated_submit_fn` — verify it handles paper market fills.
3. **Storage split: compat symlink or hard cut?** Recommend: compat symlink for one release, then hard cut.

---

## 9. Non-Goals

- Rewriting in Rust/Cython
- Multi-process cluster
- New UI components
- New broker adapters
- Changing the domain model (stable core)
