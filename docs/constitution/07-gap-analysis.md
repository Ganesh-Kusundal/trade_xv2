# 07 — Gap Analysis

**Status:** Code vs constitution (2026-07-20)  
**Method:** graphify-first + targeted grep + architecture tests  
**Authority:** Phases 0–F in `docs/constitution/`

---

## Summary

| Severity | Count | Theme |
|---|---|---|
| P0 | 4 | Zero-parity / execution spine fragmentation |
| P1 | 6 | Naming, branching, clock purity |
| P2 | 5 | Layering, DI typing, duplicate engines |
| P3 | 3 | Docs drift, glossary synonyms |

**Recommended Phase H first context:** ExecutionTarget / OMS spine (P0 cluster).

---

## P0 — Must fix before Live capability

### G-P0-1 — No canonical `ExecutionTarget` protocol

| | |
|---|---|
| **Constitution** | `04-component-contracts.md` — `ExecutionTarget` primary seam |
| **As-built** | `FillSource` in `application/execution/fill_source.py` (close but wrong layer/name) |
| **Violation** | P5 (capability not named); contract in application not domain |
| **Fix** | Add `domain/ports/execution_target.py`; `resolve_execution_target()` in runtime |
| **Acceptance** | Architecture test: domain port exists; runtime is sole resolver |

### G-P0-2 — Execution mode string branching outside composition root

| | |
|---|---|
| **Constitution** | `02a` §5 — only `resolve_execution_target` branches on mode |
| **As-built** | `create_execution_adapter(mode: str, ...)` in `oms_backtest_adapter.py`; `RuntimeMode = Literal["trade", "market", "sim"]` in `runtime/factory.py` |
| **Violation** | P12 |
| **Fix** | `ExecutionTargetKind` enum; single `runtime/execution_target.py` resolver |
| **Acceptance** | Grep ratchet: no `mode == "paper"` outside runtime |

### G-P0-3 — Multiple place_order entry surfaces

| | |
|---|---|
| **Constitution** | P1 — one OMS spine |
| **As-built** | Was 20+ files; application tier now 8 via `place_order_spine` |
| **Fix** | `application/execution/spine.py`; composer + facade + use case routed |
| **Status** | ✅ Partial — paper_orders still uses direct OM call (broker wire tier) |
| **Acceptance** | Architecture ratchet tiers + spine grep tests green |

### G-P0-4 — Replay/backtest parallel adapter path

| | |
|---|---|
| **Constitution** | Same pipeline for all targets |
| **As-built** | `SimulatedOMSAdapter` → `ExecutionEngine` + `place_order_spine` |
| **Status** | ✅ Closed (Context 2) |
| **Acceptance** | QA-determinism-1 parity test green |

---

## P1 — High priority

### G-P1-1 — Clock purity violations (P8)

| | |
|---|---|
| **As-built** | Was `datetime.now()` in fill/order/event builders |
| **Fix** | `get_current_clock()` / `VirtualClock` in sim fills, backtest adapter, audit, API |
| **Status** | ✅ Closed for constitution-scoped paths |
| **Scenario** | QA-determinism-3; `test_clock_purity.py` + `test_backtest_clock_purity.py` |

### G-P1-2 — `FillSource` not equivalent to full ExecutionTarget contract

| | |
|---|---|
| **As-built** | `FillSource` only exposes `submit_fn()` — no `cancel`, `modify`, `capabilities()` |
| **Fix** | Extend protocol per `04`; Live target implements full surface |
| **Scenario** | QA-extensibility-2 |

### G-P1-3 — Product identity was split (resolved in Phase 0)

| | |
|---|---|
| **Was** | `project-overview.md` analytics-only vs e2e-spec live-trading |
| **Now** | C+ constitution in `00-vision-and-product.md`; context files pointed |
| **Status** | ✅ Closed by this program Phase 0 |

### G-P1-4 — Paper orders legacy bypass

| | |
|---|---|
| **As-built** | `brokers/paper/paper_orders.py` has `_place_via_oms` and direct paths |
| **Fix** | All paper through ExecutionEngine |
| **Scenario** | QA-resiliency-3 |

### G-P1-5 — ExecutionComposer parallel to ExecutionEngine

| | |
|---|---|
| **As-built** | `application/composer/execution.py` async place path |
| **Fix** | Composer delegates to `place_order_spine` via `CallableExecutionTarget` |
| **Status** | ✅ Closed — `_place_via_oms` routes through spine |
| **Rule** | 2-local-fix → redesign (constitution decision-making) |

### G-P1-6 — Runtime mode enum doesn't match capability matrix

| | |
|---|---|
| **As-built** | `RuntimeMode = "trade" \| "market" \| "sim"` |
| **Target** | `ExecutionTargetKind = REPLAY \| BACKTEST \| PAPER \| LIVE` |
| **Fix** | Align enums in Phase H |

---

## P2 — Medium priority

### G-P2-1 — `deps.py` returns untyped/`Any` getters

| | |
|---|---|
| **Constitution** | `06` — typed DI |
| **Fix** | Protocol return types on all hot-path getters |

### G-P2-2 — Dual backtest engines

| | |
|---|---|
| **As-built** | `BacktestEngine` + `FastBacktestEngine` |
| **Fix** | Document ownership; converge or explicit capability flag |

### G-P2-3 — Datalake direct duckdb.connect drift sites

| | |
|---|---|
| **As-built** | 8 exempt sites in architecture ratchet |
| **Fix** | Route through pool per analytics roadmap P1 |

### G-P2-4 — Domain `_session_trading.py` place helpers

| | |
|---|---|
| **As-built** | Session object exposes `.buy()/.sell()` reaching placement |
| **Fix** | Session delegates to orchestrator/ExecutionEngine only |

### G-P2-5 — Interface imports broker services directly

| | |
|---|---|
| **As-built** | UI commands call `brokers.services` (post ponytail W2.2) |
| **Fix** | Accept for read-only market data; block for order placement bypass |

---

## P3 — Lower priority

### G-P3-1 — Glossary synonyms in code (`Trade` entity vs `Fill`)

### G-P3-2 — `docs/architecture/*` not superseded (ignored per program charter)

### G-P3-3 — `web/` SPA not implemented (documented in vision)

---

## Runtime Model Conformance

| Rule (`02a`) | Status |
|---|---|
| Single asyncio loop primary | ✅ Mostly |
| OMS single-writer | ⚠️ Multiple entry surfaces |
| Only runtime imports brokers | ✅ Mostly (interface warnings) |
| Boot lifecycle documented | ⚠️ Partial in factory.py |
| Fail-closed boot | ✅ Config validation exists |

---

## Ranked Phase H Backlog

| Rank | Gap ID | Context | Action | Type | Status |
|---|---|---|---|---|---|
| 1 | G-P0-1, G-P0-2 | ExecutionTarget | Add protocol + runtime resolver | Contract | ✅ |
| 2 | G-P0-4 | OMS/Replay | Wire replay through ExecutionEngine | Integration | ✅ |
| 3 | G-P0-3 | OMS | Shrink place_order allowlist | Redesign | ✅ partial |
| 4 | G-P1-1 | Cross-cutting | Clock injection sweep | Local fixes → redesign if >2 | ✅ |
| 5 | G-P1-5 | Execution | Composer → place_order_spine | Redesign | ✅ |
| 6 | G-P2-1 | Interface | Typed deps | Local | pending |

---

## Acceptance for Phase G complete

- [x] All P0 gaps identified with evidence
- [x] Ranked backlog for Phase H
- [x] Each gap maps to constitution principle (P1–P12) or QA scenario
- [x] graphify queries run for execution/OMS paths

---

## Evidence References

| Path | Finding |
|---|---|
| `src/application/execution/fill_source.py` | FillSource = de facto target, wrong name/layer |
| `src/application/execution/oms_backtest_adapter.py:44` | String mode branch |
| `src/runtime/factory.py:26` | RuntimeMode ≠ ExecutionTargetKind |
| `src/application/execution/execution_engine.py` | Correct unified engine (keep) |
| `tests/architecture/test_place_order_path_inventory.py` | 20+ place_order surfaces |
| `tests/component/execution/test_parity_characterization.py` | Parity tests exist (extend) |
