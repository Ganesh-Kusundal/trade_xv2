# Code Reality & Execution Plan

**Generated from source inspection (not documentation).**  
**Date:** 2026-07-10  
**Method:** AST/file inventory + direct reads of production modules under `src/`, `application/`, `brokers/`, `analytics/`, `datalake/`, `api/`, `cli/`, `infrastructure/`, `tradex/`, `runtime/`, `config/`, `.github/workflows/`.

This document **updates** the build plan. Where it conflicts with older design docs, **this wins**.

**Parallelism / multi-agent schedule:** [`DEPENDENCY_GRAPH_AND_PARALLELISM.md`](./DEPENDENCY_GRAPH_AND_PARALLELISM.md)

---

## 0. Corpus snapshot (real)

| Package | Path | ~Files | ~LOC |
|---------|------|--------|------|
| domain | `src/domain/` | 246 | 24k |
| application | `application/` | 119 | 22k |
| brokers | `brokers/` | 464 | 67k |
| analytics | `analytics/` | 144 | 23k |
| datalake | `datalake/` | 96 | 17k |
| infrastructure | `infrastructure/` | 139 | 20k |
| cli | `cli/` | 129 | 23k |
| api | `api/` | 42 | 8k |
| tradex | `tradex/` | 119 | 4.5k |
| config | `config/` | 20 | 4k |
| runtime | `runtime/` | 7 | 0.5k |

**Already good (do not “fix dual resilience” as if full copies remain):**

- `tradex/runtime/resilience/*.py` are **re-export shims** → `infrastructure.resilience` (e.g. `circuit_breaker.py` is 2 lines).
- `tradex/runtime/stream_orchestrator.py` → façade to `application.streaming.orchestrator`.
- `tradex/runtime/historical_coordinator.py` → façade to `application.data.historical_coordinator`.
- OO surface exists: `InstrumentTradingMixin.buy/sell` → `OrderServicePort` only (`src/domain/instruments/instrument_trading.py`).
- OMS has real structure: locks, correlation_id, TRADE→TRADE_APPLIED design, kill switch, margin hooks, loss CB **code** present.

---

## 1. Verified defects (with file evidence)

### P0 — money / recovery

| ID | Defect | Evidence |
|----|--------|----------|
| **R1** | `OrderStore` never written/read by OMS | `application/oms/order_manager.py`: only `self._order_store = order_store`. **Zero** `_order_store.upsert/load`. API still injects store via `api/lifecycle.py` `build_order_store()` → **false durability**. |
| **R2** | `update_daily_pnl` has **no production callers** | Grep across non-test application/src: only definition + comments in `application/oms/_internal/risk_manager.py`. Daily loss + loss CB never see live MTM. |
| **R3** | MARKET/zero-price notional understates risk | `risk_manager.py` L296–299: `qty * price if price > 0 else qty`. |
| **R4** | Phantom capital default | `application/oms/context.py` L248: `capital_fn or (lambda: PHANTOM_CAPITAL_INR)` (₹1e6 in `src/domain/constants/risk.py`). |
| **R5** | Position PnL has **no multiplier** | `src/domain/entities/position.py`: linear `qty * (price - avg)`; no `multiplier` field. |
| **R6** | Trade ledger **mark before apply** | `application/oms/trade_recorder.py` L112–115: `mark_processed` then `apply_trade`. Crash = ledger advanced, order/position incomplete; restart skips re-apply. |
| **R7** | Extended orders bypass full risk | `application/oms/extended_order_service.py`: `check_order` count **0**; `_check_kill_switch` count **8**. |
| **R8** | Upstox subscribe wrong kwargs + swallow | `brokers/upstox/data_provider.py` L165–169: `stream(underlying, exchange, callback, depth=depth)`. Gateway: `stream(symbol, exchange, mode, on_tick)` (`brokers/upstox/gateway.py` L174). Exceptions swallowed → empty handle. |
| **R9** | Dhan gateway missing `get_order` | `brokers/dhan/gateway.py`: `get_orderbook` only. `get_order` exists on `brokers/dhan/execution/orders.py` L159. |
| **R10** | Paper false market | `brokers/paper/paper_gateway.py` L188–194: `np.random` OHLCV; streams stubbed (~L341+). |

### P0 — path fragmentation (one money path not achieved)

| ID | Defect | Evidence |
|----|--------|----------|
| **R11** | `PlaceOrderUseCase` is **orphan** | Defined `application/execution/place_order_use_case.py`. Production importers: **only** `application/execution/__init__.py`. Not used by api/cli/orchestrator. |
| **R12** | Many parallel place surfaces | Non-test `def place_order` / use cases in: `order_manager`, `execution_service`, `execution_mode_adapter`, `composer/execution`, `api/routers/orders`, `api/v2/domain_endpoints`, `cli/...`, gateways, transports, `domain/services/orders.py`. |
| **R13** | CLI places via OMS directly (good) but not use case | `cli/services/cli_broker_facade.py` L186: `order_manager.place_order(req, submit_fn=...)`. |
| **R14** | API places via `tradex.connect` session | `api/routers/orders.py` ~L295: `session = tradex.connect(broker)` then session/OMS path — not `PlaceOrderUseCase`. |
| **R15** | Instrument path uses OrderServicePort (good intent) | `instrument_trading.py` + `domain/orders/placement.py` `place_via_order_service` → must resolve same process OMS (`tradex/session.py` ~L280 `build_oms_service`). |

### P1 — dual systems / CI / events

| ID | Defect | Evidence |
|----|--------|----------|
| **R16** | Dual paper engines | `analytics/paper/engine.py` **and** `brokers/paper/*` both exist. |
| **R17** | Resilience dual is **mostly fixed** | tradex files are shims. **Do not spend a phase “merging” full copies.** Remaining work: ensure imports prefer `infrastructure.resilience`; delete shims later. |
| **R18** | EventBus append without sync_mode | `infrastructure/event_bus/event_bus.py` ~L398: `self._event_log.append(event)` — no capital-event fsync flag. |
| **R19** | Domain risk policy unused by app RiskEngine | App uses `application/oms/_internal/risk_manager.py`. `domain.risk` not imported by application production code. |
| **R20** | CI ghosts | `.github/workflows/ci.yml`: `frontend/` job (dir **missing**); `tests/e2e/test_multi_broker_failover.py` (**missing**). |
| **R21** | Cancel path may skip full SM | Board finding; verify in `order_manager.cancel_order` when implementing C1.4 — treat as P1 until unit-locked. |

---

## 2. What the code already implements (preserve)

| Capability | Location | Plan implication |
|------------|----------|------------------|
| Domain Instrument OO | `src/domain/instruments/*` | Align with Trading OS blueprint; don’t reinvent |
| OrderServicePort intent | `domain/ports/order_service.py`, placement helpers | **Wire everyone here**, don’t invent fourth path |
| TradingContext wiring | `application/oms/context.py` | Fix recovery/risk feed; keep structure |
| Process OMS registry | `application/oms/process_context.py`, `composition.py` | Enforce live uses registry |
| ExecutionService + mode adapters | `application/execution/*` | Collapse toward one façade calling OMS |
| TradingOrchestrator | `application/trading/trading_orchestrator.py` | Point at OrderService/OMS; add single-order policy |
| SqliteOrderStore + lock | `infrastructure/persistence/sqlite_order_store.py` | **Wire into OrderManager** |
| Processed trade repo | `infrastructure/event_bus/processed_trade_repository.py` | Fix mark order; keep durable file |
| Broker plugins scale | `brokers/dhan`, `upstox`, `paper` | Contract matrix; parity fixes |
| Import-linter contracts | `pyproject.toml` | Keep; add architecture greps |
| Stream/history ownership | already under `application/streaming`, `application/data` | Façades in tradex OK short-term |
| Rich test tree | `tests/`, package tests | Add cold-start + wiring tests; fix CI paths |

---

## 3. Target alignment (blueprint ↔ this tree)

| Blueprint runtime | Current home (code) | Gap |
|-------------------|---------------------|-----|
| Kernel / composition | `runtime/*`, `tradex/runtime/bootstrap`, `cli/services/oms_bootstrap`, `api/lifecycle`, `TradingRuntimeFactory` | **Multiple roots** — unify |
| Broker runtime | `brokers/*` + ports | EP/DP incomplete parity |
| Market data | `application/streaming`, instrument mixins, broker WS | Subscribe bugs; cache ownership fuzzy |
| Trading / OMS | `application/oms` | Store/PnL/ledger order |
| Strategy | `analytics/strategy` + `application/trading` | MultiStrategyRuntime shell |
| Analytics | `analytics/*` | Must not place orders (grep gate) |
| Research replay | `analytics/replay` | ≠ OMS recovery (name in APIs) |
| Infrastructure | `infrastructure/*` | Event durability; store wire |
| SDK | `tradex.session` / `tradex.connect` | Good direction; composition unify |

---

## 4. Updated commit plan (code-first, incremental)

### Rules (unchanged)

- Small commits; red→green preferred  
- Message: `phase0/...`  
- Module EXIT only when behavior tests pass  
- **No cosmetic-only module closure**

### Corrections vs older plan

| Old claim | Reality | New action |
|-----------|---------|------------|
| Merge dual resilience implementations | Already shims | **C1.5 demoted** to optional shim cleanup / import standardize |
| PlaceOrderUseCase is the path | Orphan | **Must adopt or delete**; adopt in api/cli/orchestrator |
| Phase 0 ignores path fan-out | R11–R15 block G1 | Add **C0.9** inventory gate + **C1.1** real redirects |

---

### Phase 0 — Make existing OMS honest (files we will touch)

| Commit | Scope (real files) | Done when |
|--------|-------------------|-----------|
| **C0.0** | Commit this plan + cross-links | Doc on branch |
| **C0.1a** | Tests: MARKET notional, F&O multiplier PnL | red |
| **C0.1b** | `src/domain/entities/position.py` + `application/oms/_internal/risk_manager.py` (+ small notional helper under `src/domain/risk/` or `execution/sizing`) | green |
| **C0.2a/b** | `context.py` / composition: refuse phantom in live; tests | live boot without capital fails |
| **C0.3a/b** | Wire `PositionManager` / portfolio → `RiskManager.update_daily_pnl` on TRADE_APPLIED/LTP; tests prove daily loss trips | green |
| **C0.4a/b** | `OrderManager`: upsert on place/update; `TradingContext` hydrate from `SqliteOrderStore` on boot; multi-process cold-start test | store non-empty after place; restart restores |
| **C0.5a/b** | `trade_recorder.py`: apply → mark; crash test | green |
| **C0.6** | `event_bus.py` + `BufferedEventLog`: sync/fsync for TRADE/ORDER_* | unit |
| **C0.7a** | `brokers/dhan/gateway.py`: `get_order` → orders adapter | unit/contract |
| **C0.7b** | `brokers/upstox/data_provider.py`: correct `mode=`/`on_tick=`; no bare except | contract |
| **C0.8** | `.github/workflows/ci.yml`: remove/fix frontend job; remove missing e2e path; add cold-start path that exists | CI config valid |
| **C0.9** | Architecture test: list place_order call sites; assert allowlist shrinks over phases | baseline committed |

**Phase 0 exit command (adjust as tests land):**

```bash
pytest application/oms/tests -q --tb=line
# plus new tests for store hydrate, daily pnl, notional, dhan get_order, upstox subscribe
```

**Modules EXIT_MET after Phase 0:** M02 (core honesty), M20 (wired), M19 (capital fsync), M10/M11 (P0 only), M01 (PnL/notional), M28 (CI paths).

---

### Phase 1 — Single money path (collapse real call graph)

| Commit | Scope | Done when |
|--------|-------|-----------|
| **C1.1a** | Make `PlaceOrderUseCase` (or `OrderServicePort` impl) the **only** app entry; implement adapter used by Instrument + session | one implementation |
| **C1.1b** | `api/routers/orders.py` + `api/v2/domain_endpoints.py` → use case / process OMS; stop ad-hoc connect per request if avoidable | API test |
| **C1.1c** | `cli/services/cli_broker_facade.py` → same service | CLI test |
| **C1.1d** | `TradingOrchestrator` → same service | e2e candidate→order |
| **C1.1e** | `application/composer/execution.py` align or delete bypass | no bare gateway place from composer |
| **C1.2** | `extended_order_service.py` → full `RiskManager.check_order` | tests |
| **C1.3** | Paper: `paper_validate` uses lake/fixture; keep random only as `paper_toy` explicit | `brokers/paper/paper_gateway.py` |
| **C1.3c** | Redirect or delete `analytics/paper/engine.py` dual book | single book process test |
| **C1.4** | `cancel_order` / fill through `OrderStateValidator`; PARTIALLY_CANCELLED | unit |
| **C1.6** | Orchestrator one order/symbol/cycle | unit |
| **C1.7** | Unify composition: `TradingRuntimeFactory` / `OmsBootstrap` / `api/lifecycle` / `tradex.open_session` share one `build_trading_stack` | process OMS identity test |

**Phase 1 exit:** G1 true in code (grep + tests): no production place except OrderService/OMS spine.

---

### Phase 2 — Remaining modules (depth, not cosmetics)

Driven by **code gaps**, not doc wishlist:

| Commit | Code focus |
|--------|------------|
| **C2.1** | `application/streaming/*` + broker subscribe error propagation (no silent empty) |
| **C2.2** | `application/data/historical_coordinator.py` fail taxonomy tests |
| **C2.3** | `brokers/common/capabilities_validator.py` expand; Upstox slice capability honesty |
| **C2.4** | Contract matrix tests for dhan/upstox/paper fakes |
| **C2.5** | `datalake/quality/*` gate for paper_validate/backtest |
| **C2.6** | `analytics/replay` + `domain/trading_costs` forced on PnL |
| **C2.7** | Event codecs + DLQ payload/redrive (`infrastructure/event_bus/*`) |
| **C2.8** | Readyz = recon gate (`api` health + lifecycle) |
| **C2.9** | Indicator dual: `src/domain/indicators` vs `analytics/indicators` — one pure SSOT + tests |
| **C2.10** | `config` + `runtime/production_config.py`: single env name `TRADEX_ENV` |
| **C2.11** | `cli` doctor checks store wire + capital + ledger |
| **C2.12** | Shrink remaining **non-shim** `tradex/runtime` (e.g. `extensions/registry.py`, `factory.py`) by move or thin |
| **C2.13** | CI architecture greps: no `analytics` → place_order; no new gateway place from strategies |

---

## 5. Call-graph target (from current code)

**Today (simplified, verified):**

```text
api.orders ──tradex.connect──► session/OMS or gateway
cli ──► order_manager.place_order + submit_fn(gateway)
Instrument.buy ──► OrderServicePort.place
ExecutionService ──► order_manager
composer.execution ──► async place_order (separate)
PlaceOrderUseCase ──► (unused)
ExtendedOrderService ──► broker (kill switch only)
```

**Target:**

```text
api / cli / Instrument / Orchestrator / Agent tools
        └──► OrderServicePort / PlaceOrderUseCase
                └──► OrderManager (+ Risk + Store)
                        └──► ExecutionProvider (plugin)
```

---

## 6. Module board (status from code, not aspiration)

| ID | Module | Code status now | Next EXIT work |
|----|--------|-----------------|----------------|
| M01 | domain | Strong OO; PnL/notional gaps | C0.1 |
| M02 | oms | Solid skeleton; store/PnL/ledger/extended broken | C0.2–0.5, C1.2, C1.4 |
| M03 | execution | Files exist; use case orphan | C1.1* |
| M04 | trading | Orchestrator real; multi-strategy shell | C1.6 |
| M05 | streaming | Under application; broker subscribe bugs | C0.7b, C2.1 |
| M06 | historical | Under application; large | C2.2 |
| M07 | composition | **Fragmented** (api/cli/tradex/runtime) | C1.7 |
| M08 | portfolio/sched | Thin; PnL feed missing | C0.3 |
| M09 | brokers.common | Present; weak validator | C2.3 |
| M10 | dhan | Large; get_order gap | C0.7a, C2.4 |
| M11 | upstox | subscribe bug | C0.7b, C2.4 |
| M12 | paper | Random history | C1.3 |
| M13–16 | analytics | Present | C2.5–2.6, C2.9 |
| M17 | analytics.paper | Dual engine file exists | C1.3c |
| M18 | datalake | Present | C2.5 |
| M19 | event bus/log | Present; weak capital sync | C0.6, C2.7 |
| M20 | persistence | Store exists **unwired** | C0.4 |
| M21 | resilience | **Canonical infra; tradex shim** | optional cleanup |
| M22 | lifecycle/health | Present | C2.8 |
| M24–26 | api/cli/tradex | Multi place paths | C1.1, C1.7 |
| M27 | config | Env dual risk | C2.10 |
| M28 | tests/CI | Ghosts | C0.8, C0.9 |

---

## 7. Explicit non-goals this week

- Security multi-tenant program (deferred)  
- Full Trading OS package rename (`trading_os/`)  
- Rewriting dhan/upstox god modules before contract tests  
- “Merge resilience” as if two full trees still exist  
- Web frontend  

---

## 8. First commits to make (ordered)

1. **C0.0** — add this file; point TARGET_SYSTEM_DESIGN / MODULE_PROGRAM “reality override” here  
2. **C0.1a** — failing tests for notional + multiplier  
3. **C0.1b** — implement  
4. Continue C0.2 → C0.9 without skipping store/PnL/ledger  

Do **not** start C1.1 until Phase 0 exit: an unwired store + dead daily PnL makes “one path” cosmetic.

---

## 9. Document precedence

1. **This file** — code reality + commit plan  
2. `trading-os/TRADING_OS_BLUEPRINT.md` — long-horizon institutional target  
3. `MODULE_PROGRAM.md` — module depth sheets (status column updated by this reality)  
4. `TARGET_SYSTEM_DESIGN.md` — flows/spine; commit tables overridden where this file differs  
5. Older reports under `docs/reports/` — historical findings only  

---

*End of code-grounded plan.*
