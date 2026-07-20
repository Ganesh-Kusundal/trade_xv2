# 08 — Incremental Implementation

**Status:** Playbook  
**First context:** ExecutionTarget / OMS spine (see `07-gap-analysis.md` rank 1–3)

---

## Per-Context Workflow

Every bounded context rebuild follows these 12 steps:

| Step | Activity | Output |
|---|---|---|
| 1 | Architecture review vs constitution | Gap IDs scoped to context |
| 2 | Design review | Contract delta (if any) |
| 3 | Domain review | Glossary + aggregate check |
| 4 | API/contract lock | Protocol frozen in `04` |
| 5 | Runtime flow vs `02a` | Thread/sync confirmation |
| 6 | Tests first | `venv/bin/pytest` failing tests |
| 7 | Implementation | Minimal diff |
| 8 | Integration | Component + e2e tests green |
| 9 | Runtime validation | Manual smoke via `venv/bin/python` |
| 10 | Performance validation | Cited QA scenarios from `01a` |
| 11 | Docs update | Constitution + `context/progress-tracker.md` |
| 12 | Acceptance review | Gap closed or explicitly deferred |

**Environment:** Always `venv/bin/pytest`, `venv/bin/python`. Never system Python.

---

## Context 1 — ExecutionTarget / OMS Spine (COMPLETE)

### Scope

Close G-P0-1, G-P0-2, begin G-P0-3, G-P0-4.

### Design (locked)

1. `ExecutionTargetKind` enum in domain (`REPLAY`, `BACKTEST`, `PAPER`, `LIVE`).
2. `ExecutionTarget` protocol in `domain/ports/execution_target.py` — canonical name; `FillSource` remains backward-compatible alias.
3. `resolve_execution_target()` in `runtime/execution_target.py` — **sole** mode branch.
4. `create_execution_adapter()` delegates to resolver (no duplicate branch logic).
5. `ExecutionEngine` accepts `ExecutionTarget`.
6. Architecture ratchet test for resolver exclusivity.

### Files touched

| File | Change |
|---|---|
| `src/domain/ports/execution_target.py` | NEW — enum + protocol |
| `src/domain/ports/__init__.py` | Export |
| `src/runtime/execution_target.py` | NEW — resolver |
| `src/application/execution/fill_source.py` | Document alias; adapters implement ExecutionTarget |
| `src/application/execution/oms_backtest_adapter.py` | Delegate create_execution_adapter |
| `src/application/execution/execution_engine.py` | Accept ExecutionTarget type |
| `tests/architecture/test_execution_target_resolver.py` | NEW — ratchet |
| `tests/component/execution/test_execution_target_resolver.py` | NEW — integration |

### QA scenarios validated

- QA-extensibility-2 (new target = new impl + factory)
- QA-determinism-1 (after replay wired — follow-up)
- QA-testability-1 (architecture tests green)

### Exit criteria

- [x] `ExecutionTarget` protocol in domain
- [x] `resolve_execution_target` in runtime only
- [x] `create_execution_adapter` has zero independent mode branches
- [x] Architecture ratchet test green
- [x] Existing parity characterization tests still green

### Follow-up contexts (not this sprint)

| Context | Gaps | Depends on |
|---|---|---|
| Replay/Backtest | G-P0-4 | Context 1 |
| OMS allowlist shrink | G-P0-3 | Context 1 |
| Clock purity | G-P1-1 | — |
| Composer merge | G-P1-5 | Context 1 |

---

## Context 2 — Replay / Backtest (COMPLETE)

Wire `analytics/replay` and `analytics/backtest` through `ExecutionEngine` + resolved target.

### Changes

- `SimulatedOMSAdapter` holds `ExecutionEngine` built via `resolve_execution_target`
- Default `place_order` path uses `ExecutionEngine.place_order` (no parallel OMS bypass)
- `runtime/execution_target.build_execution_engine()` for analytics entry
- Bar-timestamp override via custom `submit_fn` retained (FakeClock follow-up)

### Exit criteria

- [x] SimulatedOMSAdapter routes through ExecutionEngine by default
- [x] `build_execution_engine` available at composition root
- [x] Component + architecture tests green (`venv/bin/pytest`)

### Remaining (Context 2 follow-up)

- (none — clock purity moved to Context 4)

**Gate for Context 3:** optional — Market Data deferred.

---

## Context 3 — OMS Spine Consolidation (COMPLETE)

Close G-P0-3: single `place_order_spine` helper.

### Changes

- `application/execution/spine.py` — `place_order_spine(order_manager, command, target)`
- `CallableExecutionTarget` for composer quota path
- `ExecutionComposer._place_via_oms` → spine
- `PlaceOrderUseCase` accepts optional `execution_target`
- `cli_broker_facade` → `build_execution_engine`
- Tiered architecture ratchet in `test_place_order_path_inventory.py`

### Exit criteria

- [x] Spine module exists and is used by composer
- [x] Application/interface allowlist ≤ 8 entries
- [x] 59+ order-path tests green

---

## Context 4 — Clock Purity (COMPLETE)

Close G-P1-1: injected clock on order/fill/event paths.

### Changes

- `make_simulated_submit_fn` defaults to `get_current_clock().now()`
- `OmsBacktestAdapter._execute_side` wraps placement in `VirtualClock(bar_ts)`
- Removed timestamp `submit_fn` override from backtest hot path
- Swept `datetime.now()` → clock in API orders/trades, audit logger, analytics models
- Extended `test_clock_purity.py` coverage; added `test_backtest_clock_purity.py`

### Exit criteria

- [x] Architecture clock purity test green
- [x] Backtest adapter order timestamp matches bar time
- [x] Simulated fill uses injected clock

---

## Context 5 — Market Data (DEFERRED)

Datalake duckdb pool routing. Lower blast radius after execution spine stable.

---

## Commit & Verification Checklist

After each context:

```bash
venv/bin/pytest tests/architecture/ tests/component/execution/ -q
graphify update .
# Update context/progress-tracker.md
```

---

## Deferred ADRs

| Topic | When |
|---|---|
| Rename FillSource → ExecutionTarget fully | After all imports migrated |
| Execution target entry-point group | When third-party simulators needed |
| Live product surface enablement | Separate product milestone |
