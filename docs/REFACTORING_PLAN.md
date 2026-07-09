# Structural Cleanup — Phased Refactoring Plan

> **Branch:** `refactor/structural-cleanup`
> **Checkpoint:** `ee8fe75`
> **Date:** 2026-07-10
> **Total findings:** 87 (15 critical, 37 high, 30 medium, 5 low)

---

## Execution Model

### Multi-Agent Team Roles

| Agent | Scope | Runs In |
|---|---|---|
| **Agent-α (Delete)** | Dead code, empty packages, shims | Phase 1–2 |
| **Agent-β (Consolidate)** | Duplicate modules, indicator/scanner merge | Phase 2–3 |
| **Agent-γ (Restructure)** | Infrastructure absorption, dependency fixes | Phase 3–5 |
| **Agent-δ (Refactor)** | God class decomposition, SOLID fixes | Phase 4–6 |
| **Agent-ε (Validate)** | Test repair, regression gatekeeper | All phases |
| **Agent-ζ (Guard)** | Import linter, architecture tests, CI | All phases |

### Regression Gate Protocol

Every phase ends with:
```bash
# 1. Architecture tests (boundary enforcement)
PYTHONPATH="src:." pytest tests/architecture/ -x -q

# 2. Import smoke tests
PYTHONPATH="src:." pytest tests/architecture/test_imports.py -x -q

# 3. Module-owned unit tests
PYTHONPATH="src:." pytest tests/unit/ src/domain/tests/ -x -q

# 4. Import linter (dependency direction)
PYTHONPATH="src:." lint-imports --config pyproject.toml

# 5. Full regression (if phases 3+)
PYTHONPATH="src:." pytest tests/ -x -q --timeout=120
```

---

## Phase Dependency Graph

```
┌─────────────────────────────────────────────────────────────┐
│                    PHASE DEPENDENCY MAP                     │
└─────────────────────────────────────────────────────────────┘

  Phase 0                    Phase 1
  (Branch+Commit) ────────► (Delete Dead Code)
       │                         │
       │                    ┌────┴────┐
       │                    ▼         ▼
       │              Phase 2a    Phase 2b
       │            (Delete       (Delete
       │            shims)        empty pkgs)
       │                    │         │
       │                    └────┬────┘
       │                         ▼
       │                    Phase 2c
       │                  (Consolidate
       │                  indicators)
       │                         │
       │                    ┌────┴────┐
       │                    ▼         ▼
       │              Phase 3a    Phase 3b
       │            (Absorb      (Consolidate
       │            infra→       scanners)
       │            runtime)          │
       │                    │         │
       │                    └────┬────┘
       │                         ▼
       │                    Phase 3c
       │                  (Fix import
       │                  linter rules)
       │                         │
       │              ┌──────────┼──────────┐
       │              ▼          ▼          ▼
       │         Phase 4a   Phase 4b   Phase 4c
       │         (Break      (Break     (Break
       │         Instrument) Stream)    BrokerSvc)
       │              │          │          │
       │              └──────────┼──────────┘
       │                         ▼
       │                    Phase 5a
       │                  (Fix dep
       │                  direction)
       │                         │
       │                    ┌────┴────┐
       │                    ▼         ▼
       │              Phase 5b    Phase 5c
       │            (Fix SRP     (Fix ISP
       │            violations)  violations)
       │                    │         │
       │                    └────┬────┘
       │                         ▼
       │                    Phase 6
       │                  (Runtime state
       │                  cleanup)
       │                         │
       │                         ▼
       │                    Phase 7
       │                  (Over-engineering
       │                  cleanup)
       │                         │
       │                         ▼
       │                    Phase 8
       │                  (Documentation
       │                  & governance)
       │                         │
       ▼                         ▼
  ┌─────────────────────────────────────┐
  │     FINAL REGRESSION SUITE         │
  │     Full pytest + lint-imports     │
  └─────────────────────────────────────┘
```

---

## PHASE 0: Branch & Checkpoint ✅ COMPLETE

**Status:** Done
**Branch:** `refactor/structural-cleanup`
**Commit:** `ee8fe75`

---

## PHASE 1: Delete Dead Code

> **Risk:** LOW — Removing code with zero imports
> **Agents:** Agent-α (primary), Agent-ζ (validate)
> **Duration:** 1–2 hours
> **Can parallelize with:** Nothing (first phase)

### 1.1 Delete `providers/` package (deprecated)

| File | Reason |
|---|---|
| `providers/__init__.py` | Deprecated, 0 external imports |
| `providers/dhan/__init__.py` | Deprecated |
| `providers/dhan/data_provider.py` | `DeprecationWarning` in constructor, replaced by `brokers.dhan.adapter` |
| `providers/dhan/execution_provider.py` | Deprecated alongside data provider |

**Validation:**
```bash
# Confirm no imports
grep -r "from providers" --include="*.py" . | grep -v __pycache__ | grep -v providers/
# Should return 0 results

# Run domain isolation test (ensures nothing broke)
PYTHONPATH="src:." pytest tests/architecture/test_domain_isolation.py -x -q
```

**Commit:** `refactor(dead): delete deprecated providers/ package`

### 1.2 Delete `interfaces/` package (empty shell)

| File | Reason |
|---|---|
| `interfaces/__init__.py` | Empty |
| `interfaces/cli/__init__.py` | Empty |
| `interfaces/rest/__init__.py` | Empty |
| `interfaces/sdk/__init__.py` | Empty |

**Validation:**
```bash
grep -r "from interfaces" --include="*.py" . | grep -v __pycache__ | grep -v interfaces/
PYTHONPATH="src:." pytest tests/architecture/test_imports.py -x -q
```

**Commit:** `refactor(dead): delete empty interfaces/ package`

### 1.3 Delete `shared/` package (2-file re-export shim)

| File | Reason |
|---|---|
| `shared/__init__.py` | Empty |
| `shared/types.py` | Re-exports 4 types from `tradex.runtime.capabilities` — no module imports `shared.*` |

**Validation:**
```bash
grep -r "from shared" --include="*.py" . | grep -v __pycache__ | grep -v shared/
PYTHONPATH="src:." pytest tests/architecture/test_imports.py -x -q
```

**Commit:** `refactor(dead): delete shared/ re-export shim`

### 1.4 Delete `plugins/` package (empty + duplicates)

| File | Reason |
|---|---|
| `plugins/__init__.py` | Empty |
| `plugins/dhan/__init__.py` | Empty |
| `plugins/paper/__init__.py` | Empty |
| `plugins/upstox/__init__.py` | Empty |
| `plugins/indicators/__init__.py` | Duplicates `analytics/indicators/` |
| `plugins/indicators/atr.py` | Duplicate of `src/domain/indicators/atr.py` |
| `plugins/indicators/macd.py` | Duplicate of `src/domain/indicators/macd.py` |
| `plugins/indicators/rsi.py` | Duplicate of `src/domain/indicators/rsi.py` |
| `plugins/indicators/vwap.py` | Duplicate of `src/domain/indicators/vwap.py` |

**Validation:**
```bash
grep -r "from plugins" --include="*.py" . | grep -v __pycache__ | grep -v plugins/
PYTHONPATH="src:." pytest tests/architecture/test_imports.py -x -q
```

**Commit:** `refactor(dead): delete plugins/ package (empty + duplicate indicators)`

### 1.5 Delete empty placeholder directories

| Directory | Reason |
|---|---|
| `application/backtest/` | Empty |
| `application/scanner/` | Empty |
| `tradex/runtime/ports/` | Empty |
| `analytics_cache/` | Empty |
| `runtime-dev/` | Empty |

**Commit:** `refactor(hygiene): remove empty placeholder directories`

### 1.6 Delete empty port/interface files

| File | Reason |
|---|---|
| `src/domain/ports/data_provider.py` | 0 bytes |
| `src/domain/ports/execution_provider.py` | 0 bytes |
| `src/domain/ports/execution_context.py` | 0 bytes |
| `src/domain/ports/provider_registry.py` | 0 bytes |
| `src/domain/ports/session_context.py` | 0 bytes |
| `src/domain/ports/subscription_handle.py` | 0 bytes |
| `src/domain/composition/__init__.py` | Empty package |
| `src/domain/derivatives/__init__.py` | Empty package |

**Commit:** `refactor(dead): remove empty interface stubs`

### PHASE 1 GATE
```bash
PYTHONPATH="src:." pytest tests/architecture/ -x -q
PYTHONPATH="src:." lint-imports --config pyproject.toml
```

---

## PHASE 2: Delete Shims & Consolidate Duplicates

> **Risk:** LOW-MEDIUM — Removing backward-compat shims, merging identical code
> **Agents:** Agent-α (shims), Agent-β (indicators), Agent-ζ (validate)
> **Duration:** 2–4 hours
> **Depends on:** Phase 1 ✅

### 2.1 Delete datalake root-level shims

These files are `from datalake.core.X import *` backward-compat shims. All consumers should import from the canonical location.

| Shim File | Canonical Location |
|---|---|
| `datalake/schema.py` | `datalake.core.schema` |
| `datalake/nse_calendar.py` | `datalake.core.nse_calendar` |
| `datalake/migrations.py` | `datalake.core.migrations` |
| `datalake/option_format.py` | `datalake.core.option_format` |
| `datalake/pit_joins.py` | `datalake.core.pit_joins` |
| `datalake/validation.py` | `datalake.quality.validation` |

**Before deleting:**
```bash
# Find all imports from the shim paths
grep -r "from datalake.schema import\|from datalake.nse_calendar import\|from datalake.migrations import\|from datalake.option_format import\|from datalake.pit_joins import\|from datalake.validation import" --include="*.py" . | grep -v __pycache__ | grep -v "datalake/core/"
```

**If found:** Update imports to canonical paths, then delete shims.

**Commit:** `refactor(datalake): remove backward-compat shims, update imports`

### 2.2 Delete datalake/research duplicate files

| Duplicate | Canonical Location |
|---|---|
| `datalake/fast_backtest.py` | `datalake.research.fast_backtest` or `analytics.backtest.fast_backtest` |
| `datalake/run_backtest.py` | `datalake.research.run_backtest` |
| `datalake/scan_store.py` | `datalake.research.scan_store` |
| `datalake/scanner_universe.py` | `datalake.research.scanner_universe` |
| `datalake/options_analytics_sql.py` | `datalake.analytics.options_analytics_sql` |
| `datalake/options_greeks.py` | `datalake.analytics.options_greeks` |

**Before deleting:** Check if root-level files are `__main__` entry points or have different logic.

**Commit:** `refactor(datalake): deduplicate root vs research/analytics files`

### 2.3 Consolidate indicators into single source of truth

**Canonical location:** `src/domain/indicators/`

**Current state:**
- `src/domain/indicators/{atr,macd,rsi,vwap}.py` — domain definitions
- `analytics/indicators/{halftrend,market_structure}.py` — analytics-specific
- `analytics/pipeline/features.py` — pandas Feature classes (ATR, VWAP, RSI, SMA, EMA, MACD, etc.)
- `plugins/indicators/{atr,macd,rsi,vwap}.py` — DELETED in Phase 1

**Plan:**
1. Move `analytics/indicators/halftrend.py` → `src/domain/indicators/halftrend.py`
2. Move `analytics/indicators/market_structure.py` → `src/domain/indicators/market_structure.py`
3. Verify `analytics/pipeline/features.py` imports from `domain.indicators` (not its own copies)
4. Update all consumers

**Validation:**
```bash
PYTHONPATH="src:." pytest src/domain/tests/ analytics/tests/ -x -q -k "indicator"
```

**Commit:** `refactor(indicators): consolidate into src/domain/indicators/`

### 2.4 Consolidate scanner implementations

**Current state (3 scanners):**
- `analytics/scanner/` (8 files) — pandas-based, rule engine
- `datalake/scanner/` (3 files) — DuckDB-based, JSON rules
- `src/domain/scanners/scanner.py` (1 file) — domain VO

**Plan:**
1. Determine which scanner is the primary (likely `analytics/scanner/`)
2. Move `datalake/scanner/` rules and engine logic into `analytics/scanner/`
3. Update `datalake/research/` to import from `analytics.scanner`
4. Keep `src/domain/scanners/` as domain types only

**Validation:**
```bash
PYTHONPATH="src:." pytest analytics/scanner/tests/ datalake/tests/ -x -q
```

**Commit:** `refactor(scanner): consolidate 3 scanner impls into analytics/scanner/`

### PHASE 2 GATE
```bash
PYTHONPATH="src:." pytest tests/architecture/ -x -q
PYTHONPATH="src:." lint-imports --config pyproject.toml
PYTHONPATH="src:." pytest datalake/tests/ analytics/tests/ -x -q
```

---

## PHASE 3: Absorb `infrastructure/` into `tradex/runtime/core/`

> **Risk:** HIGH — Structural change affecting import paths across the codebase
> **Agents:** Agent-γ (primary), Agent-β (parallel duplicate cleanup), Agent-ζ (validate)
> **Duration:** 1–2 days
> **Depends on:** Phase 2 ✅
> **Can parallelize with:** Phase 3b (scanner consolidation, if deferred)

### 3.1 Create `tradex/runtime/core/` package

```
tradex/runtime/core/
├── __init__.py
├── cache/
│   ├── __init__.py          ← from infrastructure.cache
│   └── redis.py             ← from infrastructure.cache_redis
├── correlation.py           ← from infrastructure.correlation
├── di.py                    ← from infrastructure.di
├── di_scopes.py             ← from infrastructure.di_scopes
├── event_bus/
│   ├── __init__.py          ← from infrastructure.event_bus.*
│   ├── async_event_bus.py
│   ├── dead_letter_queue.py
│   ├── domain_bus_adapter.py
│   ├── event_bus.py
│   ├── factory.py
│   ├── persistent_dead_letter_queue.py
│   └── processed_trade_repository.py
├── event_log.py             ← from infrastructure.event_log
├── health.py                ← from infrastructure.health
├── io/
│   ├── __init__.py          ← from infrastructure.io.*
│   ├── async_compat.py
│   ├── environment_bootstrap.py
│   └── parquet.py
├── lifecycle/
│   ├── __init__.py          ← from infrastructure.lifecycle.*
│   └── lifecycle.py
├── logging_config.py        ← from infrastructure.logging_config
├── metrics/
│   ├── __init__.py          ← from infrastructure.metrics.*
│   ├── prometheus.py
│   ├── registry.py
│   └── types.py
├── persistence/
│   ├── __init__.py          ← from infrastructure.persistence.*
│   └── sqlite_order_store.py
├── time_service.py          ← from infrastructure.time_service
└── resource_manager.py      ← from infrastructure.resource_manager
```

### 3.2 Create backward-compat shims in `infrastructure/`

Every moved file gets a shim:
```python
# infrastructure/cache.py
"""Backward-compat shim — moved to tradex.runtime.core.cache."""
from tradex.runtime.core.cache import *  # noqa: F401,F403
```

**This allows incremental migration** — existing imports continue to work.

### 3.3 Migrate consumers in waves

**Wave 1 — Low-risk modules (Day 1 AM):**
```bash
# Files that import from infrastructure.*
grep -rn "from infrastructure\." --include="*.py" . | grep -v __pycache__ | grep -v "infrastructure/" | \
  sed 's/:.*from \([a-zA-Z_]*\)\..*/\1/' | sort -u
```

Update these modules to import from `tradex.runtime.core.*`:
- `brokers/dhan/` files
- `brokers/upstox/` files
- `api/` files
- `cli/` files
- `config/` files

**Wave 2 — Medium-risk modules (Day 1 PM):**
- `tradex/runtime/` internal files (already partially migrated)
- `application/` files

**Wave 3 — High-risk modules (Day 2 AM):**
- `tests/` files
- `scripts/` files

### 3.4 Merge duplicate observability

**Before:**
```
infrastructure/observability/http_server.py  (479 lines)
tradex/runtime/observability/http_server.py  (462 lines)  ← KEEP this one
```

**Plan:**
1. Verify `tradex/runtime/observability/http_server.py` is the canonical version
2. Update all consumers to import from `tradex.runtime.observability.http_server`
3. Delete `infrastructure/observability/http_server.py` (or leave as shim)

Same for:
- `infrastructure/observability/alerting.py` → merge into `tradex/runtime/observability/audit.py`
- `infrastructure/retry.py` → merge into `tradex/runtime/resilience/retry.py`

### 3.5 Merge duplicate circuit breaker

**Before:**
```
brokers/dhan/resilience/circuit_breaker.py
tradex/runtime/resilience/circuit_breaker.py   ← KEEP this one
```

**Plan:**
1. Verify `tradex/runtime/resilience/circuit_breaker.py` is the canonical version
2. Update `brokers/dhan/` to import from `tradex.runtime.resilience.circuit_breaker`
3. Delete `brokers/dhan/resilience/circuit_breaker.py`

### 3.6 Update `pyproject.toml` import linter contracts

```toml
# BEFORE:
[tool.importlinter]
root_packages = ["domain", "brokers", "analytics", "datalake", "cli", "api", 
                 "application", "infrastructure", "tradex", "shared"]

# AFTER:
[tool.importlinter]
root_packages = ["domain", "brokers", "analytics", "datalake", "cli", "api", 
                 "application", "tradex"]
# infrastructure removed — absorbed into tradex.runtime.core
# shared removed — deleted in Phase 1
```

Update all `[[tool.importlinter.contracts]]` that reference `infrastructure`.

### 3.7 Delete `infrastructure/` package

After all shims are verified working and all tests pass:
```bash
# Final verification
PYTHONPATH="src:." pytest tests/architecture/ -x -q
PYTHONPATH="src:." lint-imports --config pyproject.toml

# Remove the package
rm -rf infrastructure/
```

**Commit:** `refactor(infra): absorb infrastructure/ into tradex/runtime/core/`

### PHASE 3 GATE
```bash
PYTHONPATH="src:." pytest tests/architecture/ -x -q
PYTHONPATH="src:." lint-imports --config pyproject.toml
PYTHONPATH="src:." pytest tests/unit/ src/domain/tests/ -x -q
PYTHONPATH="src:." pytest brokers/dhan/tests/unit/ brokers/upstox/tests/unit/ -x -q
```

---

## PHASE 4: Break God Classes

> **Risk:** HIGH — Behavioral changes, requires careful test coverage
> **Agents:** Agent-δ (primary), Agent-ε (test repair), Agent-ζ (validate)
> **Duration:** 2–3 days
> **Depends on:** Phase 3 ✅
> **Can parallelize:** Phases 4a, 4b, 4c can run in parallel on separate agents

### 4a. Decompose `Instrument` (1,161 lines → 4 classes)

**Current class responsibilities:**
```
Instrument (1,161 lines, 65+ methods)
├── Entity: identity, state, properties (lines 55–316)
├── Streaming: subscribe, callbacks (lines 332–417)
├── Market Data: quote, depth, history, options, futures (lines 419–568)
└── Trading: buy, sell, market, limit, stop_loss, cancel, modify (lines 569–655)
```

**Target structure:**
```
src/domain/instruments/
├── instrument.py         ← Entity only (~300 lines)
│   class Instrument:
│       id, symbol, exchange, lot_size, tick_size
│       quote, ltp, bid, ask, volume, depth
│       statistics, snapshot, serialize, clone
│
├── instrument_streaming.py  ← Streaming mixin (~150 lines)
│   class InstrumentStreaming:
│       subscribe, unsubscribe
│       on_tick, on_quote, on_depth, on_disconnect, on_reconnect
│
├── instrument_market_data.py  ← Market data queries (~200 lines)
│   class InstrumentMarketData:
│       history, option_chain, future_chain
│       refresh, depth, spread, mid_price
│
└── instrument_trading.py   ← Trading actions (~200 lines)
    class InstrumentTrading:
        buy, sell, market, limit, stop_loss
        cancel, modify
```

**Migration strategy:**
```python
# instrument.py — composition via mixins
class Instrument(InstrumentStreaming, InstrumentMarketData, InstrumentTrading):
    """Unified instrument facade."""
    pass
```

**Validation:**
```bash
PYTHONPATH="src:." pytest src/domain/tests/test_instrument.py -x -v
PYTHONPATH="src:." pytest tests/unit/domain/instruments/ -x -v
```

**Commit:** `refactor(domain): decompose Instrument god class into 4 focused classes`

### 4b. Decompose `StreamOrchestrator` (1,040 lines → 5 classes)

**Current responsibilities:**
```
StreamOrchestrator (1,040 lines, 30+ methods)
├── Session Management: start, stop, open, disconnect (lines 278–650)
├── Subscription Routing: subscribe, unsubscribe, merge (lines 301–548)
├── Message Delivery: tick, order update, dedup (lines 392–510)
├── Reconnection: reconnect loop, failover, heartbeat (lines 775–980)
└── Broker Selection: select_broker (lines 980–1007)
```

**Target structure:**
```
tradex/runtime/
├── stream_orchestrator.py   ← Orchestrator only (~250 lines)
├── session_manager.py       ← Session lifecycle (~200 lines)
├── tick_router.py           ← Message delivery + dedup (~200 lines)
├── reconnect_controller.py  ← Reconnect + failover + heartbeat (~250 lines)
└── broker_selector.py       ← Broker selection logic (~100 lines)
```

**Commit:** `refactor(runtime): decompose StreamOrchestrator into 5 focused classes`

### 4c. Decompose `BrokerService` (1,010 lines → 4 classes)

**Current responsibilities:**
```
BrokerService (1,010 lines, 32 methods)
├── Lifecycle: start, stop, close (lines 130–404)
├── OMS Setup: _build_oms_risk_manager, _build_and_register_oms (lines 465–678)
├── Order Routing: place_order, cancel_order, get_orders (lines 779–915)
└── Broker Management: set_active_broker, use_paper, get_broker_statuses (lines 915–973)
```

**Target structure:**
```
cli/services/
├── broker_service.py        ← Thin orchestrator (~200 lines)
├── oms_bootstrap.py         ← OMS setup and DI (~200 lines)
├── cli_broker_facade.py     ← Order routing for CLI (~200 lines)
└── broker_manager.py        ← Active broker switching (~150 lines)
```

**Commit:** `refactor(cli): decompose BrokerService god class`

### PHASE 4 GATE
```bash
PYTHONPATH="src:." pytest src/domain/tests/test_instrument.py -x -v
PYTHONPATH="src:." pytest tests/unit/ -x -q
PYTHONPATH="src:." pytest cli/tests/ -x -q
PYTHONPATH="src:." pytest tests/api/ -x -q
```

---

## PHASE 5: Fix Dependency Direction & SOLID Violations

> **Risk:** MEDIUM-HIGH — Architectural fixes
> **Agents:** Agent-γ (dependency direction), Agent-δ (SOLID), Agent-ζ (validate)
> **Duration:** 1–2 days
> **Depends on:** Phase 4 ✅
> **Can parallelize:** Phases 5a and 5b can run on separate agents

### 5a. Fix cyclic dependency: `tradex.runtime` ↔ `infrastructure`

**Current cycles:**
```
tradex/runtime/bootstrap.py → infrastructure.event_bus (EventBus, ProcessedTradeRepository)
tradex/runtime/auth/environment_bootstrap.py → infrastructure.io
tradex/runtime/auth/metrics.py → infrastructure.metrics
tradex/runtime/observability/__init__.py → infrastructure.observability
```

**After Phase 3:** These should already be resolved (infrastructure absorbed into tradex.runtime.core).
**Verify:**
```bash
grep -rn "from infrastructure\." --include="*.py" . | grep -v __pycache__ | grep -v "infrastructure/"
# Should return 0 results (all moved to tradex.runtime.core)
```

### 5b. Move error types to domain layer

**Current:** `tradex/runtime/resilience/errors.py` contains `TradeXV2Error` hierarchy
**Problem:** Error types used by `brokers.common`, `application`, `api` all depend on `tradex.runtime`

**Plan:**
1. Move error hierarchy to `src/domain/errors.py` (already exists — verify it has the types)
2. Create re-export in `tradex/runtime/resilience/errors.py` for backward compat
3. Update `brokers/common/api/__init__.py` to import from `domain.errors`

**Validation:**
```bash
PYTHONPATH="src:." pytest tests/architecture/test_no_duplicate_error_hierarchies.py -x -q
PYTHONPATH="src:." lint-imports --config pyproject.toml
```

**Commit:** `refactor(domain): move error hierarchy to domain layer`

### 5c. Fix ISP violations in broker ports

**Current:** `tradex/runtime/broker_port.py` `CommonBrokerGateway` has 14 methods

**Plan:** Split into focused protocols:
```python
# tradex/runtime/ports/market_data_gateway.py
class MarketDataGateway(Protocol):
    def ltp(...) -> Decimal: ...
    def quote(...) -> Quote: ...
    def depth(...) -> MarketDepth: ...
    def history(...) -> pd.DataFrame: ...

# tradex/runtime/ports/order_gateway.py
class OrderGateway(Protocol):
    def place_order(...) -> OrderResponse: ...
    def cancel_order(...) -> OrderResponse: ...
    def modify_order(...) -> OrderResponse: ...
    def get_orderbook(...) -> list[Order]: ...

# tradex/runtime/ports/stream_gateway.py
class StreamGateway(Protocol):
    def stream(...) -> StreamHandle: ...
    def unstream(...) -> None: ...
```

**Backward compat:** `CommonBrokerGateway` becomes a composite:
```python
class CommonBrokerGateway(MarketDataGateway, OrderGateway, StreamGateway, Protocol):
    ...
```

**Commit:** `refactor(ports): split CommonBrokerGateway into focused protocols`

### 5d. Fix `TradingContext` service locator pattern

**Current:** `TradingContext` (759 lines, 38 methods/properties) is a god bag

**Plan:**
1. Extract `DlqMonitorService` → `application/oms/dlq_monitor.py`
2. Extract `ProcessedTradeCleanupService` → `application/oms/trade_cleanup.py`
3. Replace `TradingContext` property-heavy design with constructor injection
4. Keep `TradingContext` as a thin data holder (< 100 lines)

**Commit:** `refactor(oms): extract services from TradingContext god bag`

### 5e. Fix `OrderManager` shotgun surgery

**Current:** `OrderManager` (838 lines) handles idempotency, validation, submission, trade recording, risk, events

**Plan:**
1. Extract `IdempotencyGuard` → `application/oms/idempotency_guard.py`
2. Extract `OrderValidator` → `application/oms/order_validator.py`
3. Extract `TradeRecorder` → `application/oms/trade_recorder.py`
4. `OrderManager` becomes a thin orchestrator (~300 lines)

**Commit:** `refactor(oms): decompose OrderManager into focused collaborators`

### PHASE 5 GATE
```bash
PYTHONPATH="src:." pytest tests/architecture/ -x -q
PYTHONPATH="src:." lint-imports --config pyproject.toml
PYTHONPATH="src:." pytest application/oms/tests/ -x -q
PYTHONPATH="src:." pytest brokers/common/tests/ -x -q
```

---

## PHASE 6: Runtime State Cleanup

> **Risk:** LOW — File system hygiene
> **Agents:** Agent-α (primary), Agent-ζ (validate)
> **Duration:** 1–2 hours
> **Depends on:** Phase 5 ✅

### 6.1 Add runtime artifacts to `.gitignore`

```gitignore
# Runtime state (NEVER commit)
runtime/*.sqlite
runtime/*.lock
runtime/*.json
runtime/*.log
runtime/event-log/
market_data/*.sqlite
market_data/*.sqlite-*
market_data/*.lock
```

### 6.2 Remove tracked runtime files

```bash
git rm --cached runtime/dead_letter.sqlite
git rm --cached runtime/dhan-market-feed-*.lock
git rm --cached runtime/dhan-token-state.json
git rm --cached runtime/dhan-totp-cooldown.json
git rm --cached runtime/upstox-token-state.json
git rm --cached runtime/server.log
git rm --cached market_data/backtest_results.sqlite
git rm --cached market_data/journal.sqlite*
git rm --cached market_data/oms_orders.sqlite*
```

### 6.3 Clean 226 `__pycache__` directories

```bash
find . -type d -name "__pycache__" -not -path "./venv/*" -exec rm -rf {} + 2>/dev/null
echo "__pycache__/" >> .gitignore
```

**Commit:** `refactor(hygiene): remove runtime artifacts from source tree, clean pycache`

---

## PHASE 7: Over-Engineering Cleanup

> **Risk:** LOW-MEDIUM
> **Agents:** Agent-α (deletions), Agent-δ (simplifications), Agent-ζ (validate)
> **Duration:** 2–4 hours
> **Depends on:** Phase 6 ✅

### 7.1 Delete `poc/` or move to `docs/poc/`

21 prototype files with no tests. Either archive or delete.

### 7.2 Simplify `config/profiles/`

**Current:** 3-class hierarchy (`BaseProfile` → `DevProfile`, `StagingProfile`, `ProdProfile`)

**Plan:** Replace with a single `EnvironmentProfile` dataclass loaded from env vars:
```python
@dataclass
class EnvironmentProfile:
    env: str = "dev"
    strict_validation: bool = False
    allow_mock_brokers: bool = True
    debug_endpoints: bool = True
```

### 7.3 Simplify `config/__init__.py`

**Current:** 79-line facade with extensive docstrings for 3 functions.

**Plan:** Trim to essential imports only (~15 lines).

### 7.4 Reduce `analytics/__init__.py` mega re-export

**Current:** 598 lines, 22 re-exports.

**Plan:** Reduce to essential public API only (~30 lines). Consumers should import directly from sub-modules.

### 7.5 Move design docs from `reports/` to `docs/`

```bash
mv reports/ARCHITECTURE_REVIEW_2026-07-08.md docs/
mv reports/ARCHITECTURE_REVIEW_BOARD_2026-07-09.md docs/
mv reports/BROKERS_EVOLUTION_PLAN.md docs/
# ... etc
```

**Commit:** `refactor(cleanup): simplify configs, archive POC, move docs`

---

## PHASE 8: Documentation & Governance

> **Risk:** NONE
> **Agents:** Agent-ζ (primary)
> **Duration:** 2–4 hours
> **Depends on:** Phase 7 ✅

### 8.1 Update `pyproject.toml` for new structure

```toml
[tool.setuptools.packages.find]
where = ["src", "."]
include = ["brokers*", "cli*", "analytics*", "datalake*", "config*", 
           "domain*", "runtime*", "application*", "tradex*"]

[tool.pytest.ini_options]
testpaths = ["tests", "brokers", "analytics", "cli", "datalake", 
             "application", "src", "tradex"]
# infrastructure removed

[tool.coverage.run]
source = ["brokers", "analytics", "cli", "datalake", "application", 
          "domain", "tradex"]
# infrastructure removed
```

### 8.2 Update architecture tests

Update `tests/architecture/test_imports.py`:
```python
MODULES = [
    "tradex.runtime.core.logging_config",  # was infrastructure.logging_config
    "tradex.runtime.core.metrics",
    "tradex.runtime.core.cache",
    "tradex.runtime.core.health",
    "tradex.runtime.observability.tracing",  # was infrastructure.observability.tracing
    "tradex.runtime.core.correlation",
    "tradex.runtime.resilience.errors",  # was infrastructure.global_exception_handler
    "api.main",
]
```

Update `tests/architecture/test_domain_isolation.py`:
```python
FORBIDDEN_LAYERS = (
    "application", "brokers", "analytics", "api", "cli",
    "config",  # was infrastructure — now part of tradex
    "datalake", "tradex",
)
```

### 8.3 Update `docs/ARCHITECTURE.md`

Document the final module structure:
```
src/domain/          → Core domain (entities, value objects, ports, events)
tradex/              → Public SDK + runtime engine
  session.py         → Entry point
  runtime/           → Platform kernel
    core/            ← absorbed from infrastructure/
    resilience/      → retry, circuit breaker, rate limiter
    observability/   → audit, metrics, alerting
    auth/            → token management
    broker/          → router, registry, policy
    adapters/        → broker↔domain translation
    services/        → instrument registry, data validation
    models/          → DTOs, routing models
application/         → Use cases (OMS, execution, trading, composer)
brokers/             → Broker implementations
  common/            → Shared abstractions
  dhan/              → Dhan broker
  upstox/            → Upstox broker
  paper/             → Paper trading
analytics/           → Quantitative analytics
datalake/            → Data storage and ingestion
api/                 → REST/WebSocket API
cli/                 → CLI interface
config/              → Configuration
tests/               → Integration/system tests
```

### 8.4 Final regression run

```bash
# Full test suite
PYTHONPATH="src:." pytest tests/ -x -q --timeout=120

# Architecture fitness
PYTHONPATH="src:." pytest tests/architecture/ -v

# Import linter
PYTHONPATH="src:." lint-imports --config pyproject.toml

# Coverage
PYTHONPATH="src:." pytest tests/ --cov=brokers --cov=analytics --cov=datalake \
  --cov=application --cov=domain --cov=tradex --cov-report=term-missing
```

### 8.5 Push final branch

```bash
git push origin refactor/structural-cleanup
```

**Commit:** `docs: update architecture for final module structure`

---

## Risk Mitigation

### Per-Phase Rollback Plan

Every phase is a single commit (or small set). Rollback:
```bash
git revert HEAD  # Undo last phase
```

### Test-First Safety Net

| Phase | Minimum Test Gate | Test Count |
|---|---|---|
| Phase 1 | `tests/architecture/` | 17 tests |
| Phase 2 | `tests/architecture/` + `datalake/tests/` | 17 + 37 tests |
| Phase 3 | `tests/architecture/` + `lint-imports` | 17 + linter |
| Phase 4 | `tests/unit/` + `cli/tests/` + `tests/api/` | 8 + 32 + 46 tests |
| Phase 5 | `tests/architecture/` + `application/oms/tests/` | 17 + 26 tests |
| Phase 6 | `tests/architecture/` | 17 tests |
| Phase 7 | Full suite | ~400 tests |
| Phase 8 | Full suite + coverage | ~400 tests + report |

### Agent Parallelism Matrix

```
Phase 1:  [α Delete] ────────────────────────────────────────
Phase 2:  [α Shims]  [β Indicators] ─────────────────────────
Phase 3:  [γ Absorb] [β Scanner]    ─────────────────────────
Phase 4:  [δ Instr]  [δ Stream]     [δ BrokerSvc] (parallel)
Phase 5:  [γ Deps]   [δ SOLID]      (parallel)
Phase 6:  [α Cleanup] ───────────────────────────────────────
Phase 7:  [α POC]    [δ Config]     (parallel)
Phase 8:  [ζ Docs]   [ζ CI]         (parallel)
```

---

## File Impact Summary

| Phase | Files Deleted | Files Modified | Files Created | Net Change |
|---|---|---|---|---|
| Phase 1 | ~30 | 0 | 0 | -30 |
| Phase 2 | ~20 | ~15 | 0 | -20 |
| Phase 3 | ~82 | ~60 | ~30 | -52 |
| Phase 4 | 0 | ~12 | ~10 | +10 |
| Phase 5 | 0 | ~20 | ~5 | +5 |
| Phase 6 | ~230 (pycache) | 2 | 0 | -228 |
| Phase 7 | ~25 | ~5 | 0 | -25 |
| Phase 8 | 0 | ~8 | 0 | 0 |
| **TOTAL** | **~387** | **~122** | **~45** | **-340** |

**Net result:** ~340 fewer files, cleaner structure, enforced boundaries, single source of truth for every concept.
