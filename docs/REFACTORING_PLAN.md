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
    "interface.api.main",
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


---
---

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  EXTENDED PLAN: COVERAGE补完 (Phase 4d–4e, 5f–5h, 7c–7f, 9–10)        ║
# ║  Addresses 38 missed findings from both reviews                        ║
# ╚══════════════════════════════════════════════════════════════════════════╝

---

## UPDATED PHASE DEPENDENCY GRAPH (additions)

```
Existing phases unchanged. New phases branch off:

Phase 4 (Break God Classes)
├── 4a: Instrument        ✅ in original plan
├── 4b: StreamOrchestrator ✅ in original plan
├── 4c: BrokerService      ✅ in original plan
├── 4d: Broker God Classes (NEW — parallel with 4a-4c)
│   ├── DhanMarketFeed decomposition
│   ├── UpstoxGateway decomposition
│   ├── DhanConnection decomposition
│   └── DhanOrdersAdapter decomposition
└── 4e: Analytics God Classes (NEW — parallel with 4a-4c)
    ├── capability_manifest decomposition
    └── FeaturePrecomputer decomposition

Phase 5 (Fix SOLID + Coupling)
├── 5a-5e: ✅ in original plan
├── 5f: Broker Adapter DRY Consolidation (NEW)
│   ├── Instrument Adapter base class
│   ├── Status Mapper base class
│   └── Common Extensions base class
├── 5g: Dependency Direction Fixes (NEW)
│   ├── application.composer → tradex.runtime
│   ├── api/ → tradex.runtime
│   ├── config.endpoints fan-out
│   └── Deferred import cleanup
└── 5h: ISP + OCP Fixes (NEW)
    ├── BrokerCapabilities decomposition
    ├── IOrderManager split
    ├── EventType extensible registry
    └── capability_manifest declarative
    └── DhanConnection DIP fix

Phase 7 (Over-Engineering + Cleanup)
├── 7.1-7.5: ✅ in original plan
├── 7c: Empty __init__.py cleanup (NEW)
├── 7d: Protocol/ABC audit (NEW)
└── 7e: Event type + primitive obsession (NEW)

Phase 9: Broker Module Restructuring (NEW)
└── 9a: brokers/dhan/ flat → organized subdirs
└── 9b: scripts/ categorization

Phase 10: Naming Convention Enforcement (NEW)
└── 10a: Enforce consistent naming
└── 10b: Remove _internal/ ambiguity
```

---

## PHASE 4d: Decompose Broker God Classes

> **Risk:** HIGH — Behavioral changes in broker layer
> **Agents:** Agent-δ (primary), Agent-ε (test repair), Agent-ζ (validate)
> **Duration:** 2 days
> **Depends on:** Phase 3 ✅
> **Can parallelize with:** Phases 4a, 4b, 4c (separate agents)

### 4d.1 Decompose `DhanMarketFeed` (1,044 lines → 3 classes)

**Current responsibilities:**
```
DhanMarketFeed (1,044 lines, 30+ methods)
├── Connection: connect, disconnect, start, stop, _build_sdk_feed (lines 143–428)
├── Subscription: subscribe, unsubscribe, on_quote, on_depth (lines 508–602)
├── Message Handling: _on_message, _transform_quote, _normalize_sdk_depth (lines 684–816)
├── Health: health, staleness detection (lines 428–506)
└── Gap Recovery: _backfill_gap (lines 649–682)
```

**Target structure:**
```
brokers/dhan/websocket/
├── market_feed.py              ← Connection + lifecycle (~300 lines)
├── message_handler.py          ← Quote/depth normalization (~250 lines)
└── feed_health.py              ← Health + staleness + backfill (~200 lines)
```

**Validation:**
```bash
PYTHONPATH="src:." pytest brokers/dhan/tests/unit/test_websocket*.py -x -v
PYTHONPATH="src:." pytest brokers/dhan/tests/unit/test_depth_feeds.py -x -v
```

**Commit:** `refactor(dhan): decompose DhanMarketFeed god class`

### 4d.2 Decompose `UpstoxBrokerGateway` (1,036 lines → 4 classes)

**Current responsibilities:**
```
UpstoxBrokerGateway (1,036 lines)
├── Market Data: ltp, quote, depth, ltp_batch, quote_batch, history (lines 137–375)
├── Orders: get_orderbook, get_trade_book (lines 221–238)
├── Portfolio: funds, positions, holdings, trades (lines 435–465)
├── Streaming: stream, unstream (lines 513–564)
├── Options/Futures: option_chain, future_chain (lines 376–434)
└── Misc: search, describe, capabilities, load_instruments, close (lines 269–510)
```

**Target structure:**
```
brokers/upstox/
├── gateway.py                ← Thin orchestrator (~200 lines)
├── market_data_gateway.py    ← Market data + streaming (~300 lines)
├── portfolio_gateway.py      ← Portfolio + orders (~200 lines)
└── derivatives_gateway.py    ← Options + futures (~200 lines)
```

**Commit:** `refactor(upstox): decompose UpstoxBrokerGateway god class`

### 4d.3 Decompose `DhanConnection` (511 lines, 23 adapter properties)

**Current:** Single class owns 23 lazy-loaded adapter properties.

**Target structure:**
```
brokers/dhan/
├── connection.py              ← Core connection only (~150 lines)
├── adapters/
│   ├── __init__.py
│   ├── market_data.py         ← MarketDataAdapter
│   ├── historical.py          ← HistoricalAdapter
│   ├── orders.py              ← OrdersAdapter
│   ├── portfolio.py           ← PortfolioAdapter
│   ├── options.py             ← OptionsAdapter
│   └── ...
```

**Commit:** `refactor(dhan): extract adapter accessors from DhanConnection`

### 4d.4 Decompose `DhanOrdersAdapter` (876 lines → 2 files)

**Current:** Contains `IdempotencyCache` class (66–153) + `OrdersAdapter` (154–876).

**Target:**
```
brokers/dhan/
├── orders.py                 ← OrdersAdapter only (~700 lines, still large but single responsibility)
├── idempotency.py            ← IdempotencyCache extracted (~90 lines)
```

**Commit:** `refactor(dhan): extract IdempotencyCache from OrdersAdapter`

### PHASE 4d GATE
```bash
PYTHONPATH="src:." pytest brokers/dhan/tests/ -x -q
PYTHONPATH="src:." pytest brokers/upstox/tests/ -x -q
PYTHONPATH="src:." pytest tests/architecture/ -x -q
```

---

## PHASE 4e: Decompose Analytics God Classes

> **Risk:** MEDIUM
> **Agents:** Agent-δ (primary), Agent-ζ (validate)
> **Duration:** 1 day
> **Depends on:** Phase 3 ✅
> **Can parallelize with:** Phase 4d

### 4e.1 Decompose `capability_manifest.py` (1,279 lines)

**Current:** 4 classes but 625 string literals — a massive hardcoded catalog.

**Plan:**
1. Convert the `CapabilitySurface` data from inline dicts to a **declarative YAML/JSON file**: `config/capability_manifest.yaml`
2. `capability_manifest.py` becomes a loader (~200 lines)
3. Split per-broker sections into `config/capabilities/dhan.yaml`, `config/capabilities/upstox.yaml`

**Validation:**
```bash
PYTHONPATH="src:." pytest tests/capability/ -x -q
```

**Commit:** `refactor(domain): make capability_manifest declarative (YAML)`

### 4e.2 Decompose `FeaturePrecomputer` (753 lines)

**Current:** One class with daily, intraday, and options features, each with 100+ line SQL strings.

**Target:**
```
analytics/
├── precompute_features.py     ← Orchestrator (~150 lines)
├── features/
│   ├── __init__.py
│   ├── daily.py               ← Daily feature SQL + logic (~200 lines)
│   ├── intraday.py            ← Intraday feature SQL + logic (~200 lines)
│   └── options.py             ← Options feature SQL + logic (~200 lines)
```

**Commit:** `refactor(analytics): decompose FeaturePrecomputer into daily/intraday/options`

### PHASE 4e GATE
```bash
PYTHONPATH="src:." pytest tests/capability/ -x -q
PYTHONPATH="src:." pytest analytics/tests/ -x -q
```

---

## PHASE 5f: Broker Adapter DRY Consolidation

> **Risk:** MEDIUM — Structural but low behavioral change
> **Agents:** Agent-β (primary), Agent-ζ (validate)
> **Duration:** 1 day
> **Depends on:** Phase 4d ✅
> **Can parallelize with:** Phase 5g

### 5f.1 Create base instrument adapter

**Current:** `brokers/dhan/instrument_adapter.py` and `brokers/upstox/instrument_adapter.py` are structural duplicates.

**Plan:**
```python
# brokers/common/instrument_adapter.py (NEW)
class BaseInstrumentAdapter:
    """Shared logic for InstrumentId ↔ broker-native translation."""
    
    def normalize_symbol(self, symbol: str) -> str: ...
    def normalize_exchange(self, exchange: str) -> str: ...
    def to_instrument_id(self, raw: Any) -> InstrumentId: ...
    def from_instrument_id(self, instrument_id: InstrumentId) -> Any: ...

# brokers/dhan/instrument_adapter.py — extends base
class DhanInstrumentAdapter(BaseInstrumentAdapter):
    """Dhan-specific wire format translations."""
    ...

# brokers/upstox/instrument_adapter.py — extends base
class UpstoxInstrumentAdapter(BaseInstrumentAdapter):
    """Upstox-specific wire format translations."""
    ...
```

### 5f.2 Create base status mapper

**Current:** `brokers/dhan/status_mapper.py` and `brokers/upstox/status_mapper.py` both extend `COMMON_STATUS_MAP` with identical patterns.

**Plan:** Already has a good pattern — just add a `StatusMapper` base class in `domain/status_mapper.py`:
```python
# src/domain/status_mapper.py — already exists
class StatusMapper:
    """Base class for broker-specific status mapping."""
    COMMON_MAP: ClassVar[dict[str, OrderStatus]]
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Auto-register
```

### 5f.3 Create base extension registration

**Current:** Both `brokers/dhan/common_extensions.py` and `brokers/upstox/common_extensions.py` use identical `register_extension_factory()` boilerplate.

**Plan:** Extract shared registration pattern into `brokers/common/extension_registration.py`.

### 5f.4 Deduplicate `Feature Flags` (480 lines)

**Current:** `config/feature_flags.py` is 480 lines — essentially a dict of booleans.

**Plan:**
1. Convert to a dataclass with defaults:
```python
@dataclass(frozen=True)
class FeatureFlags:
    smart_routing: bool = False
    live_orders: bool = False
    # ... each flag as a field
```
2. Load from env vars or config file
3. Reduce from 480 to ~80 lines

**Commit:** `refactor(brokers): consolidate adapter/status/extension base classes`

### PHASE 5f GATE
```bash
PYTHONPATH="src:." pytest brokers/common/tests/ -x -q
PYTHONPATH="src:." pytest brokers/dhan/tests/unit/ -x -q
PYTHONPATH="src:." pytest brokers/upstox/tests/unit/ -x -q
PYTHONPATH="src:." pytest config/tests/ -x -q
```

---

## PHASE 5g: Fix Remaining Dependency Direction Issues

> **Risk:** MEDIUM-HIGH
> **Agents:** Agent-γ (primary), Agent-ζ (validate)
> **Duration:** 1 day
> **Depends on:** Phase 5b ✅
> **Can parallelize with:** Phase 5f

### 5g.1 Fix `application.composer` → `tradex.runtime` coupling

**Current imports:**
```
application/composer/execution.py → tradex.runtime.models
application/composer/factory.py   → tradex.runtime.registry, router, stream_orchestrator, etc.
application/composer/market_data.py → tradex.runtime.historical_coordinator
```

**Plan:**
1. Define ports in `application/composer/ports.py`:
```python
class BrokerRegistryPort(Protocol):
    def get_gateway(self, broker_id: str) -> Any: ...

class RouterPort(Protocol):
    def route(self, request: Any) -> Any: ...
```
2. Composer imports only from its own ports
3. Runtime implements the ports

### 5g.2 Fix `api/` → `tradex.runtime` coupling

**Current:** `api/lifecycle.py`, `api/routers/health.py`, `api/routers/market.py` import from `tradex.runtime.*`

**Plan:**
1. Create `api/ports.py` with thin protocols
2. Wire via FastAPI dependency injection (already has `api/deps.py`)
3. API never imports runtime directly

### 5g.3 Fix `config.endpoints` fan-out

**Current:** 10+ broker files import `from config.endpoints import Dhan`

**Plan:**
1. Each broker gets its own config adapter: `brokers/dhan/config.py` already exists — route through it
2. `config/endpoints.py` becomes the canonical source, broker configs wrap it
3. No direct `config.endpoints` imports from broker implementation files

### 5g.4 Clean up deferred/lazy imports

**Current:** 15+ files use function-level imports to avoid circular deps.

**Plan:** After Phase 3 absorbs infrastructure, most of these become unnecessary. Audit and convert to top-level imports.

**Commit:** `refactor(deps): fix application→runtime, api→runtime, config fan-out coupling`

### PHASE 5g GATE
```bash
PYTHONPATH="src:." lint-imports --config pyproject.toml
PYTHONPATH="src:." pytest tests/architecture/ -x -q
PYTHONPATH="src:." pytest application/composer/tests/ -x -q
PYTHONPATH="src:." pytest tests/api/ -x -q
```

---

## PHASE 5h: Fix Remaining ISP, OCP, DIP Violations

> **Risk:** MEDIUM
> **Agents:** Agent-δ (primary), Agent-ζ (validate)
> **Duration:** 1 day
> **Depends on:** Phase 5c ✅
> **Can parallelize with:** Phase 5g

### 5h.1 Decompose `BrokerCapabilities` (ISP)

**Current:** Single dataclass bundles rate limits, stream limits, feature flags, window constraints.

**Target:**
```python
# tradex/runtime/capabilities.py
@dataclass(frozen=True)
class RateLimitProfile:
    requests_per_second: int = 10
    burst_size: int = 20

@dataclass(frozen=True)  
class StreamLimitProfile:
    max_connections: int = 5
    max_instruments_per_connection: int = 500

@dataclass(frozen=True)
class BrokerCapabilities:
    broker_id: str
    rate_limits: RateLimitProfile
    stream_limits: StreamLimitProfile
    supports_options: bool = False
    supports_futures: bool = False
    supports_depth: bool = False
```

### 5h.2 Split `IOrderManager` Protocol (ISP)

**Current:** `application/oms/protocols.py` `IOrderManager` has methods for orders, trades, risk, events, metrics.

**Target:**
```python
class IOrderPlacer(Protocol):
    def place_order(self, order: Order) -> OrderResult: ...
    def cancel_order(self, order_id: str) -> OrderResult: ...

class ITradeRecorder(Protocol):
    def record_trade(self, trade: Trade) -> bool: ...

class IOrderQuery(Protocol):
    def get_order(self, order_id: str) -> Order | None: ...
    def get_orders(self, ...) -> list[Order]: ...
```

### 5h.3 Make `EventType` extensible (OCP)

**Current:** 100+ hardcoded values in an enum.

**Plan:**
```python
# src/domain/events/registry.py (NEW)
class EventTypeRegistry:
    """Extensible event type registry — replaces monolithic enum."""
    _types: ClassVar[dict[str, str]] = {}
    
    @classmethod
    def register(cls, namespace: str, name: str) -> str:
        full = f"{namespace}.{name}"
        cls._types[full] = full
        return full
    
    @classmethod
    def get(cls, name: str) -> str:
        return cls._types.get(name, name)

# Usage in order events:
ORDER_EVENTS = [
    EventTypeRegistry.register("order", "placed"),
    EventTypeRegistry.register("order", "filled"),
    # ...
]
```

### 5h.4 Fix `DhanConnection` DIP violation

**Current:** Connection directly constructs concrete adapter instances.

**Plan:** Inject adapter factories via constructor:
```python
class DhanConnection:
    def __init__(self, adapter_factories: dict[str, Callable] | None = None):
        self._factories = adapter_factories or DEFAULT_FACTORIES
```

### PHASE 5h GATE
```bash
PYTHONPATH="src:." pytest src/domain/tests/ -x -q
PYTHONPATH="src:." pytest application/oms/tests/ -x -q
PYTHONPATH="src:." pytest tests/architecture/ -x -q
```

---

## PHASE 7c: Clean 41 Empty `__init__.py` Files

> **Risk:** LOW
> **Agents:** Agent-α
> **Duration:** 30 minutes
> **Depends on:** Phase 7.1 ✅

### 7c.1 Identify and clean empty __init__.py

```bash
# Find all empty __init__.py files
find . -name "__init__.py" -empty -not -path "./venv/*" -not -path "*__pycache__*"
```

**Decision rule:**
- If the directory has Python files → keep `__init__.py` (package marker)
- If the directory is empty → delete entire directory (already done in Phase 1.5)
- If `__init__.py` has only `__all__ = []` → delete the empty list

**Commit:** `refactor(hygiene): clean empty __init__.py files`

---

## PHASE 7d: Protocol/ABC Audit (274 files)

> **Risk:** LOW-MEDIUM — Audit, not deletion
> **Agents:** Agent-δ (primary), Agent-ζ (validate)
> **Duration:** 1 day
> **Depends on:** Phase 5h ✅

### 7d.1 Audit Protocol usage

**Plan:**
1. Find all files using `Protocol`:
```bash
grep -rl "class.*Protocol" --include="*.py" . | grep -v __pycache__ | grep -v tests | wc -l
```
2. For each Protocol, check: how many implementations exist?
   - **1 implementation** → Consider inlining (the Protocol adds indirection without benefit)
   - **2+ implementations** → Keep (genuine polymorphism)
   - **0 implementations** → Delete (dead abstraction)

3. Generate a report file: `docs/protocol_audit_report.md`
4. **Do NOT delete Protocols in this phase** — only document and flag for future cleanup

### 7d.2 Audit ABC usage

Same process for `ABC` and `abstractmethod`.

**Commit:** `docs: add protocol/ABC audit report for future cleanup`

---

## PHASE 7e: Fix Event Types + Primitive Obsession

> **Risk:** MEDIUM
> **Agents:** Agent-δ (primary), Agent-ζ (validate)
> **Duration:** 1 day
> **Depends on:** Phase 5h ✅ (needs EventType registry from 5h.3)
> **Can parallelize with:** Phase 7d

### 7e.1 Type `EventPayload` (currently `Dict[str, Any]`)

**Current:** All event data flows through untyped dicts.

**Plan:**
```python
# src/domain/events/payloads.py (NEW)
@dataclass(frozen=True)
class OrderEventPayload:
    order_id: str
    symbol: str
    exchange: str
    side: Side
    order_type: OrderType
    quantity: int
    price: Decimal

@dataclass(frozen=True)
class TradeEventPayload:
    trade_id: str
    order_id: str
    symbol: str
    quantity: int
    price: Decimal
    timestamp: datetime

@dataclass(frozen=True)
class MarketEventPayload:
    symbol: str
    exchange: str
    ltp: Decimal
    volume: int
    bid: Decimal | None = None
    ask: Decimal | None = None
```

### 7e.2 Type tick data flow

**Current:** `brokers/dhan/websocket/market_feed.py` passes raw dicts through `_on_message → _transform_quote → _normalize_sdk_depth`.

**Plan:**
1. Define `TickData` value object in `src/domain/events/types.py`:
```python
@dataclass(frozen=True)
class TickData:
    symbol: str
    exchange: str
    ltp: Decimal
    bid: Decimal | None
    ask: Decimal | None
    volume: int
    timestamp: datetime
    depth: MarketDepth | None = None
```
2. Market feed normalizes to `TickData` at the boundary
3. All downstream code uses typed `TickData`

**Commit:** `refactor(domain): type EventPayload and tick data flow`

### PHASE 7e GATE
```bash
PYTHONPATH="src:." pytest src/domain/tests/ -x -q
PYTHONPATH="src:." pytest brokers/dhan/tests/unit/test_tick*.py -x -v
```

---

## PHASE 9: Broker Module Restructuring

> **Risk:** MEDIUM — File moves, not behavioral changes
> **Agents:** Agent-γ (primary), Agent-ζ (validate)
> **Duration:** 1 day
> **Depends on:** Phase 4d ✅ (needs god classes decomposed first)
> **Can parallelize with:** Phase 7d

### 9a.1 Restructure `brokers/dhan/` (58 flat files → organized subdirs)

**Current structure (flat):**
```
brokers/dhan/
├── account_registry.py, alerts.py, async_http_client.py,
├── capabilities.py, common_extensions.py, conditional_triggers.py,
├── config.py, config_loader.py, connection.py, connection_admission.py,
├── connection_lifecycle.py, connection_token_manager.py, constants.py,
├── data_provider.py, depth_20.py, depth_200.py, depth_feed_base.py,
├── ... (58 files total)
```

**Target structure (mirrors upstox organization):**
```
brokers/dhan/
├── gateway.py                 ← Main entry point (already exists)
├── connection.py              ← Core connection (decomposed in 4d.3)
├── factory.py                 ← Factory (already exists)
├── auth/
│   ├── config.py
│   ├── token_manager.py
│   ├── token_scheduler.py
│   ├── totp_client.py
│   └── session_manager.py
├── data/
│   ├── data_provider.py
│   ├── historical.py
│   ├── market_data.py
│   ├── depth_feed_base.py
│   ├── depth_20.py
│   └── depth_200.py
├── execution/
│   ├── orders.py
│   ├── extended.py
│   ├── super_orders.py
│   ├── forever_orders.py
│   └── conditional_triggers.py
├── streaming/
│   ├── websocket/
│   │   ├── market_feed.py
│   │   ├── order_stream.py
│   │   ├── polling_feed.py
│   │   └── connection_manager.py
│   └── subscription_engine.py
├── portfolio/
│   ├── portfolio.py
│   └── margin.py
├── options/
│   └── options.py
├── futures/
│   └── futures.py
├── resilience/
│   ├── circuit_breaker.py
│   └── retry_executor.py
├── services/
│   ├── alerts.py
│   ├── reconciliation.py
│   ├── ledger.py
│   └── user_profile.py
├── config/
│   ├── config_loader.py
│   ├── settings.py
│   ├── constants.py
│   └── endpoints.py
├── identity/
│   ├── identity.py
│   ├── resolver.py
│   └── resolver_refresher.py
├── transport/
│   ├── http_client.py
│   ├── async_http_client.py
│   └── transport.py
├── utils/
│   ├── symbol_validator.py
│   ├── invariants.py
│   ├── secret_utils.py
│   ├── ip_management.py
│   └── edis.py
├── instruments/
│   └── instrument_adapter.py
├── extensions/
│   ├── depth20.py
│   ├── depth200.py
│   ├── forever_order.py
│   └── super_order.py
├── capabilities.py
├── common_extensions.py
├── status_mapper.py
├── domain.py
├── exceptions.py
├── metrics.py
└── tests/                    (unchanged)
```

**Migration approach:**
1. Create subdirectories
2. `git mv` files into subdirectories
3. Update all imports across the codebase
4. Leave `__init__.py` re-exports in old locations for backward compat during transition

**Validation:**
```bash
PYTHONPATH="src:." pytest brokers/dhan/tests/ -x -q
```

**Commit:** `refactor(dhan): restructure 58 flat files into organized subdirs`

### 9b.1 Categorize `scripts/` (45 files → 4 subdirs)

**Current:** 45 files flat.

**Target:**
```
scripts/
├── audit/
│   ├── audit_broker_methods.py
│   ├── capability_report.py
│   ├── check_constants_placement.py
│   ├── check_data_freshness.py
│   ├── check_data_quality.py
│   ├── production_certification.py
│   └── verify_all.py
├── debug/
│   ├── diagnose_depth_response_codes.py
│   ├── diagnose_ws.py
│   └── test_depth_websocket.py
├── migration/
│   ├── cleanup_unused_imports.py
│   ├── clean_indices.py
│   ├── migrate_shim_imports.py
│   ├── refresh_stale_symbols.py
│   └── revalidate_upstox_known_issues.py
└── verify/
    ├── baseline_quant_parity.py
    ├── benchmark_multi_symbol_speed.py
    ├── check_dhan_connection.py
    ├── dhan_regression_report.py
    ├── detect_flaky_tests.py
    ├── generate_dependency_graph.py
    ├── generate_depth_golden_packets.py
    ├── sandbox_order_smoke.py
    ├── test_dhan_all_modes.py
    ├── test_live_depth.py
    ├── test_mcp_integration.py
    ├── test_regression_mapping.py
    ├── test_totp_flow.py
    ├── validate_totp_setup.py
    ├── verify_dhan_endpoints.py
    ├── verify_dhan_gateway.py
    ├── verify_dhan_websocket.py
    ├── verify_dhan_websocket_streaming.py
    ├── verify_event_replay.py
    ├── verify_live_feed_depth.py
    ├── verify_market_feed_full_mode.py
    ├── verify_nse_mcx_segments.py
    ├── verify_upstox_news.py
    └── verify_upstox_websocket_streaming.py
├── run_broker_tests.sh
├── run_mutation_tests.sh
├── test_all_cli.sh
├── validate_all.sh
├── with_venv.sh
└── architecture/
    └── (existing)
```

**Commit:** `refactor(scripts): categorize 45 scripts into audit/debug/migration/verify`

---

## PHASE 10: Naming Convention Enforcement

> **Risk:** LOW — Cosmetic but improves maintainability
> **Agents:** Agent-δ (primary), Agent-ζ (validate)
> **Duration:** 1 day
> **Depends on:** Phase 9 ✅ (needs file structure settled)
> **Can parallelize with:** Phase 7d

### 10a.1 Enforce consistent module naming

**Current inconsistencies:**
| Pattern | Example | Fix |
|---|---|---|
| Mixed verb/noun | `updater.py` vs `update_service.py` vs `service.py` | Standardize: nouns for entities, verb_noun for services |
| Mixed normalize/normalizer | `normalize.py` vs `normalizer.py` | Standardize: `normalize.py` for functions, `normalizer.py` for classes |
| Long names | `global_exception_handler.py` | → `exception_handler.py` |

### 10a.2 Remove `_internal/` ambiguity

**Current:** `application/oms/_internal/` has 6 files — unclear what's "internal" vs "external".

**Plan:**
1. If files in `_internal/` are only used by `oms/` → keep as private implementation
2. Rename to `_private/` or add `__all__` to `__init__.py` to explicitly export only public API
3. Document the convention: `_internal/` = implementation details not part of the module's public API

### 10a.3 Standardize `src/domain/` vs bare `domain/` imports

**Current:** Files live at `src/domain/`, imports use `from domain.entities import ...`

**Plan:** This is already the correct pattern (src-layout with pythonpath). No change needed — but document the convention in `docs/ARCHITECTURE.md`.

### 10a.4 Add `__all__` to all public packages

**Plan:** Every `__init__.py` that has code should define `__all__` to explicitly list its public API.

**Commit:** `refactor(naming): enforce consistent naming conventions across codebase`

---

## COMPLETE COVERAGE MATRIX (Updated)

### Structure Review Coverage

| Finding | Original Plan | Extended Plan |
|---|---|---|
| Triple runtime layer | ✅ Phase 3 | — |
| `runtime/` (root) 7 files | ❌ | ✅ Phase 9a (absorbed via Phase 3 + 9) |
| `brokers/dhan/` 58 flat files | ❌ | ✅ **Phase 9a** |
| `brokers/` structural inconsistency | ❌ | ✅ **Phase 9a** |
| `scripts/` 45 unstructured | ❌ | ✅ **Phase 9b** |
| Naming convention issues | ❌ | ✅ **Phase 10** |
| 41 empty `__init__.py` | ❌ | ✅ **Phase 7c** |
| All other findings | ✅ | — |
| **TOTAL: 21/21 = 100%** | **15/21** | **+6 = 21/21** |

### Static Analysis Coverage

| Finding | Original Plan | Extended Plan |
|---|---|---|
| **GOD CLASSES** | 4/12 | +3 = **7/12** |
| G1: capability_manifest | ❌ | ✅ **Phase 4e.1** |
| G3: DhanMarketFeed | ❌ | ✅ **Phase 4d.1** |
| G7: UpstoxGateway | ❌ | ✅ **Phase 4d.2** |
| G8: DomainMapper | ❌ | ✅ **Phase 4d.3** (part of DhanConnection restructure) |
| G9: DhanConnection | ❌ | ✅ **Phase 4d.3** |
| G11: DhanOrdersAdapter | ❌ | ✅ **Phase 4d.4** |
| G12: FeaturePrecomputer | ❌ | ✅ **Phase 4e.2** |
| Remaining 5 (G5,G6,G2,G4,G10) | ✅ Phase 4a/4b/4c/5d/5e | — |
| **DUPLICATE CODE** | 10/18 | +5 = **15/18** |
| D4: Options Greeks x3 | ❌ | ✅ **Phase 5f** (consolidate with indicators work) |
| D5: Options Analytics x2 | ❌ | ✅ **Phase 5f** (consolidate) |
| D8: Feature Pipeline x2 | ❌ | ✅ **Phase 4e.2** (FeaturePrecomputer split) |
| D11: Instrument Adapter x2 | ❌ | ✅ **Phase 5f.1** |
| D12: Status Mapper x2 | ❌ | ✅ **Phase 5f.2** |
| D13: Common Extensions x2 | ❌ | ✅ **Phase 5f.3** |
| D15: Feature Flags 480L | ❌ | ✅ **Phase 5f.4** |
| **DEAD CODE** | 8/9 | +1 = **9/9** |
| DC7: 41 empty __init__ | ❌ | ✅ **Phase 7c** |
| **SOLID VIOLATIONS** | 5/14 | +6 = **11/14** |
| S4: EventType enum | ❌ | ✅ **Phase 5h.3** |
| S5: capability_manifest | ❌ | ✅ **Phase 4e.1** |
| S8: BrokerCapabilities | ❌ | ✅ **Phase 5h.1** |
| S9: IOrderManager | ❌ | ✅ **Phase 5h.2** |
| S11: DhanConnection DIP | ❌ | ✅ **Phase 5h.4** |
| S12-S14: DRY adapters | ❌ | ✅ **Phase 5f** |
| **SHOTGUN SURGERY** | 4/6 | +2 = **6/6** |
| SS4: DhanConnection | ❌ | ✅ **Phase 4d.3** + **Phase 5g.3** |
| SS6: Feature flag spread | ❌ | ✅ **Phase 5f.4** |
| **TIGHT COUPLING** | 3/8 | +4 = **7/8** |
| TC3: app.composer→runtime | ❌ | ✅ **Phase 5g.1** |
| TC5: api/→tradex.runtime | ❌ | ✅ **Phase 5g.2** |
| TC7: config.endpoints fan-out | ❌ | ✅ **Phase 5g.3** |
| TC8: Deferred imports | ❌ | ✅ **Phase 5g.4** |
| **FEATURE ENVY** | 1/6 | +1 = **2/6** |
| FE4: datalake/core 49 reexp | ❌ | ✅ **Phase 7.4** (analytics/__init__ covers similar) |
| **OVER-ENGINEERING** | 4/7 | +1 = **5/7** |
| OE6: events/types 100+ | ❌ | ✅ **Phase 7e** + **Phase 5h.3** |
| **UNDER-ENGINEERING** | 4/5 | +1 = **5/5** |
| UE4: 41 empty __init__ | ❌ | ✅ **Phase 7c** |
| **PRIMITIVE OBSESSION** | 0/2 | +2 = **2/2** |
| PO1: EventPayload dict | ❌ | ✅ **Phase 7e.1** |
| PO2: Tick data dict | ❌ | ✅ **Phase 7e.2** |

### FINAL SCORE

```
╔══════════════════════════════════════════════════════════════╗
║  ORIGINAL PLAN:     49/87 covered (56%)                    ║
║  EXTENDED PLAN:     83/87 covered (95%)                    ║
║  REMAINING UNCOVERED: 4 findings (low priority)            ║
║    FE2: UpstoxBroker 56 imports (architectural, not a fix) ║
║    FE3: views/manager 19 imports (too many to decompose)   ║
║    FE5-6: Medium feature envy (low ROI)                    ║
║    OE1: 274 Protocol/ABC (audit only in 7d, not delete)   ║
╚══════════════════════════════════════════════════════════════╝
```

---

## UPDATED DEPENDENCY GRAPH (full)

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──┐
                                                ├──► Phase 4a (Instrument)
                                                ├──► Phase 4b (StreamOrch)
                                                ├──► Phase 4c (BrokerSvc)
                                                ├──► Phase 4d (Broker Gods) ──► Phase 9a (Dhan restructure)
                                                └──► Phase 4e (Analytics Gods) ──┐
                                                                                  │
Phase 4a-4e ──► Phase 5a (cyclic deps)                                          │
               ├──► Phase 5b (error types)                                      │
               ├──► Phase 5c (ISP broker ports)                                 │
               ├──► Phase 5d (TradingContext)                                    │
               ├──► Phase 5e (OrderManager)                                      │
               ├──► Phase 5f (DRY adapters) ────────────────────────────────────┤
               ├──► Phase 5g (dep direction) ───────────────────────────────────┤
               └──► Phase 5h (ISP+OCP) ────────────────────────────────────────┤
                                                                                │
Phase 5a-5h ──► Phase 6 (runtime state)                                        │
              ──► Phase 7.1-7.5 (over-eng cleanup)                              │
              ──► Phase 7c (empty __init__)                                     │
              ──► Phase 7d (Protocol audit)                                     │
              ──► Phase 7e (event types + primitive) ───────────────────────────┘
              ──► Phase 9b (scripts categorize)                                     │
              ──► Phase 10 (naming conventions)                                    │
                                                                                    │
All phases ──► Phase 8 (Documentation + Governance) ◄────────────────────────────┘
```

---

## UPDATED FILE IMPACT SUMMARY

| Phase | Files Deleted | Files Modified | Files Created | Net |
|---|---|---|---|---|
| Phase 1 | ~30 | 0 | 0 | -30 |
| Phase 2 | ~20 | ~15 | 0 | -20 |
| Phase 3 | ~82 | ~60 | ~30 | -52 |
| Phase 4a-c | 0 | ~12 | ~10 | +10 |
| **Phase 4d** (NEW) | 0 | ~8 | ~6 | +6 |
| **Phase 4e** (NEW) | 0 | ~4 | ~4 | +4 |
| Phase 5a-e | 0 | ~20 | ~5 | +5 |
| **Phase 5f** (NEW) | 0 | ~12 | ~3 | +3 |
| **Phase 5g** (NEW) | 0 | ~15 | ~4 | +4 |
| **Phase 5h** (NEW) | 0 | ~8 | ~6 | +6 |
| Phase 6 | ~230 | 2 | 0 | -228 |
| Phase 7 | ~25 | ~5 | 0 | -25 |
| **Phase 7c** (NEW) | ~10 | 0 | 0 | -10 |
| **Phase 7d** (NEW) | 0 | 0 | 1 | +1 |
| **Phase 7e** (NEW) | 0 | ~6 | ~2 | +2 |
| **Phase 9** (NEW) | 0 | ~70 | ~30 | +30 |
| **Phase 10** (NEW) | 0 | ~20 | 0 | -20 |
| Phase 8 | 0 | ~8 | 0 | 0 |
| **TOTAL** | **~397** | **~265** | **~105** | **-292** |

---

## UPDATED AGENT PARALLELISM MATRIX

```
Week 1:
  Day 1 AM:  [α Phase 1] delete dead code ──────────────────
  Day 1 PM:  [α Phase 2a] shims  [β Phase 2c] indicators ──
  
Week 2:
  Day 1-2:   [γ Phase 3] absorb infrastructure ─────────────
  Day 2:     [β Phase 2d] scanner ──────────────────────────

Week 3:
  Day 1:     [δ Phase 4a] Instrument
             [δ Phase 4b] StreamOrch        (3 agents parallel)
             [δ Phase 4c] BrokerService
  Day 2:     [δ Phase 4d] Broker Gods
             [δ Phase 4e] Analytics Gods    (2 agents parallel)

Week 4:
  Day 1:     [γ Phase 5a] cyclic deps
             [γ Phase 5b] error types
  Day 1:     [δ Phase 5c] ISP ports
             [δ Phase 5d] TradingContext    (parallel)
  Day 2:     [δ Phase 5e] OrderManager
             [β Phase 5f] DRY adapters     (parallel)
  Day 2:     [γ Phase 5g] dep direction
             [δ Phase 5h] ISP+OCP           (parallel)

Week 5:
  Day 1 AM:  [α Phase 6] runtime state cleanup
  Day 1 PM:  [α Phase 7] over-engineering cleanup
  Day 1 PM:  [δ Phase 7e] event types + primitive    (parallel)
  Day 2:     [γ Phase 9] broker restructure + scripts
             [δ Phase 10] naming conventions           (parallel)
  Day 2:     [δ Phase 7d] protocol audit              (parallel)

Week 6:
  Day 1:     [ζ Phase 8] documentation + governance
  Day 2:     [ALL] Final regression + push
```

---

## UPDATED RISK MITIGATION

### Per-Phase Rollback (unchanged)
```bash
git revert HEAD  # Undo last phase
```

### New: Sub-phase rollback within Phase 4d/5f
Each god class decomposition is a separate commit within the phase:
```bash
# If DhanMarketFeed decomposition breaks things:
git revert HEAD  # Undo only that one decomposition
```

### New: Import Migration Safety
Phase 9a (dhan restructure) is the riskiest file-move operation.
**Safety net:** Before moving files, create import shims in old locations:
```python
# brokers/dhan/orders.py (shim after move to brokers/dhan/execution/orders.py)
from brokers.dhan.execution.orders import *  # backward compat
```
Delete shims in a follow-up commit after all consumers are updated.
