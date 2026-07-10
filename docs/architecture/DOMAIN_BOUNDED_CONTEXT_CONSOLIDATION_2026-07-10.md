# Domain Bounded-Context Consolidation (2026-07-10)

**Branch:** `refactor/structural-cleanup`  
**Scope:** `src/domain/` package layout only — no production behavior change; import paths and file locations.

## Result

| Metric | Before | After |
|--------|--------|-------|
| Domain subpackages | ~38 | **29** |
| Pure re-export facades | 4 (`composition`, `derivatives`, `accounts`, `positions`) | **0** |
| Confusing `execution` / `executions` pair | Yes | **No** (only `executions/` remains) |
| `domain/utils/` dumping ground | Yes | **Gone** → `value_objects/price.py` |

## What moved / deleted

### Step 1 — Pure re-export facades deleted
- **`domain/composition/`** — re-exported `Session`/`Universe`/`TradingSession`; zero callers.
- **`domain/derivatives/`** — re-exported futures/options types; zero callers.

### Step 2 — `domain/utils/` → owner
- **`domain/utils/price.py`** → **`domain/value_objects/price.py`**
- Free functions: `snap_to_tick`, `is_tick_aligned`, `to_wire_float` (live next to `Money`/`TickSize`).
- Callers updated in Dhan/Upstox brokers, OMS risk manager, domain tests.

### Step 3 — `execution` vs `executions`
| Package | Role | Decision |
|---------|------|----------|
| `domain/execution/sizing.py` | Pre-trade qty math (`compute_order_quantity`) | **Moved → `domain/orders/sizing.py`**; package deleted |
| `domain/executions/` | `Execution` fill aggregate + `GatewayResult` | **Kept** |

Sizing is order-construction policy, not an execution record. Canonical import:

```python
from domain.orders.sizing import compute_order_quantity
```

(`application.execution.position_sizing` remains a thin re-export.)

### Step 4 — Single-file package triage

| Package | Verdict | Action |
|---------|---------|--------|
| `accounts/` | Pure re-export of `aggregates.AccountAggregate` | **Deleted**; tests → `domain/tests/test_account_aggregate.py` |
| `positions/` | Pure re-export of `aggregates.PositionAggregate` | **Deleted**; tests → `domain/tests/test_position_aggregate.py` |
| `exchanges/` | `ExchangeSession` belongs with venue types | **Merged → `domain/market/`** |
| `factories/` | `InstrumentFactory` is instrument construction | **Moved → `domain/instruments/instrument_factory.py`** |
| `market/` | Real callers (`Exchange`) | **Kept** (now + `ExchangeSession`) |
| `providers/` | `ProviderRegistry` composition root | **Kept** |
| `futures/` | Real `FutureChain` aggregate used by `Instrument` | **Kept** |
| `analytics/` | Skeleton aggregate; only package tests | **Left** (room to grow) |
| `quotes/` | `QuoteStream` real but only package tests | **Left** |
| `scanners/` | Domain ABC; production scanners live in `analytics.scanner` | **Left** |
| `sessions/` | User `TradingSession` VO; only package tests | **Left** (name collides with `market.exchange.TradingSession` — future cleanup) |
| `specifications/` | Domain ABC; only package tests | **Left** |

**Held off (per plan):** `instruments/` bulk, `ports/`, `InstrumentAggregate` → `Instrument` migration.

## Canonical import cheatsheet (post-cleanup)

```python
from domain.aggregates import AccountAggregate, PositionAggregate
from domain.market import Exchange, ExchangeSession
from domain.instruments.instrument_factory import InstrumentFactory
from domain.orders.sizing import compute_order_quantity
from domain.value_objects.price import snap_to_tick, is_tick_aligned, to_wire_float
from domain.executions.execution import Execution
from domain.executions.result import GatewayResult
```

## Verification

```bash
venv/bin/python -m pytest tests/unit/ tests/architecture/ -q
# 476 passed, 5 skipped (architecture source-not-found skips; pre-existing)
```

Note: `src/domain/futures/tests/test_future.py` has pre-existing failures (`Future` constructor API drift vs re-export tests). Not part of this pass.

## Remaining single-file packages (intentional leave)

`analytics`, `futures`, `providers`, `quotes`, `scanners`, `sessions`, `specifications` — each has a coherent concept; re-evaluate when callers appear or when implementing the named BC for real.

## Next batch (not started)

- `brokers/` layout review (Batch 3)
- `InstrumentAggregate` → `Instrument` consolidation (separate plan; 15+ analytics call sites)
