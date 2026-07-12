# D1.5 — Target Package Structure

> Prescriptive directory layout for Phase 1+ of the Trade_XV2 transformation.
> Identifies what stays, splits, moves, and deletes — with dependency rules.
> Source: `find src -type d | sort` analysis as of 2026-07-12

---

## Table of Contents

1. [Current Structure Summary](#1-current-structure-summary)
2. [Current → Target Changes](#2-current--target-changes)
3. [File Splits Detail](#3-file-splits-detail)
4. [Before / After Directory Trees](#4-before--after-directory-trees)
5. [Dependency Rules Per Directory](#5-dependency-rules-per-directory)

---

## 1. Current Structure Summary

**LOC counts for files targeted for splitting:**

| File | LOC | Classes | Phase |
|---|---|---|---|
| `domain/events/types.py` | 1008 | `DomainEvent`, `EventType`, `EventPayload`, `TypedDomainEvent`, + 8 typed events, `TradeIdKey` | Phase 1 |
| `domain/capability_manifest/catalog.py` | 905 | Module-level `CAPABILITY_SURFACES` tuple (data only) | Phase 1 |
| `domain/universe.py` | 808 | `Universe`, `Session`, `SessionDx` + 3 module-level helpers | Phase 1 |
| `application/oms/context.py` | 809 | `DlqMonitorService`, `ProcessedTradeCleanupService`, `CancellationResult`, `TradingContext` | Phase 1 |
| `application/trading/trading_orchestrator.py` | 807 | `OrchestratorConfig`, `TradingOrchestrator` | Phase 1 |
| `analytics/replay/engine.py` | 1125 | `ReplayEngine` (21 methods) | Phase 1 |

**Total:** 5,462 LOC across 6 monolithic files.

---

## 2. Current → Target Changes

### 2.1 Stays the Same

```
src/analytics/backtest/          # Backtest engine (stable)
src/analytics/core/              # Core analytics types
src/analytics/features/          # Feature engineering
src/analytics/futures/           # Futures analytics
src/analytics/indicators/        # Technical indicators
src/analytics/market_breadth/    # Market breadth
src/analytics/options/           # Options analytics
src/analytics/orderflow/         # Orderflow analysis
src/analytics/paper/             # Paper backtest
src/analytics/pipeline/          # Data pipeline
src/analytics/probability/       # Probability models
src/analytics/ranking/           # Stock ranking
src/analytics/reports/           # Report generation
src/analytics/scanner/           # Scanner engine
src/analytics/scoring/           # Scoring models
src/analytics/sector/            # Sector analysis
src/analytics/stocks/            # Stock analysis
src/analytics/strategy/          # Strategy engine
src/analytics/views/             # View models
src/analytics/visualizations/    # Chart generation
src/analytics/volatility/        # Volatility models
src/analytics/volume_profile/    # Volume profile
src/analytics/walk_forward/      # Walk-forward optimization

src/brokers/common/              # Shared broker utilities
src/brokers/dhan/                # Dhan broker adapter
src/brokers/upstox/              # Upstox broker adapter
src/brokers/paper/               # Paper broker adapter
src/brokers/certification/       # Certification suite
src/brokers/cli/                 # CLI commands
src/brokers/diagnostics/         # Broker diagnostics
src/brokers/events/              # Broker events
src/brokers/exceptions/          # Broker exceptions
src/brokers/extensions/          # Extension framework
src/brokers/mcp/                 # MCP tools
src/brokers/notebooks/           # Jupyter notebooks
src/brokers/runtime/             # Runtime helpers
src/brokers/services/            # Broker services
src/brokers/session/             # Session management

src/config/                      # Configuration
src/config/profiles/             # Profile configs

src/datalake/                    # Data lake (all sub-packages)

src/domain/aggregates/           # Aggregate roots
src/domain/analytics/            # Domain analytics types
src/domain/backtest/             # Backtest domain
src/domain/candles/              # Candle types
src/domain/capabilities/         # Capability enum + value objects
src/domain/constants/            # Domain constants
src/domain/entities/             # Entity types (Order, Trade, etc.)
src/domain/executions/           # Execution planning
src/domain/extensions/           # Extension framework
src/domain/futures/              # Futures domain
src/domain/indicators/           # Indicator domain
src/domain/instruments/          # Instrument types
src/domain/market/               # Market types + segment registry
src/domain/models/               # Domain models
src/domain/options/              # Options domain
src/domain/orders/               # Order types
src/domain/policies/             # Business policies
src/domain/portfolio/            # Portfolio domain
src/domain/ports/                # Port interfaces (ABC)
src/domain/primitives/           # Value objects
src/domain/providers/            # Provider protocols
src/domain/quotes/               # Quote types
src/domain/repositories/         # Repository interfaces
src/domain/risk/                 # Risk domain
src/domain/scanners/             # Scanner domain
src/domain/services/             # Domain services
src/domain/sessions/             # Session domain
src/domain/specifications/       # Specification pattern
src/domain/value_objects/        # Value objects

src/infrastructure/adapters/     # Adapter implementations
src/infrastructure/auth/         # Auth infrastructure
src/infrastructure/config/       # Config infrastructure
src/infrastructure/connection/   # Connection management
src/infrastructure/db/           # Database
src/infrastructure/event_bus/    # Event bus implementation
src/infrastructure/gateway/      # Gateway implementation
src/infrastructure/idempotency/  # Idempotency service
src/infrastructure/io/           # I/O utilities
src/infrastructure/lifecycle/    # Lifecycle management
src/infrastructure/mappers/      # Object mappers
src/infrastructure/metrics/      # Metrics collection
src/infrastructure/observability/# Observability
src/infrastructure/persistence/  # Persistence layer
src/infrastructure/pool/         # Connection pooling
src/infrastructure/providers/    # Data providers
src/infrastructure/resilience/   # Rate limiting, circuit breaker
src/infrastructure/security/     # Security
src/infrastructure/time/         # Time/clock services

src/interface/api/               # REST API
src/interface/api/routers/       # API routers
src/interface/api/v2/            # API v2
src/interface/api/ws/            # WebSocket API
src/interface/ui/                # Terminal UI
src/interface/agent/             # Agent interface

src/market_data/                 # Market data utilities
src/runtime/                     # Runtime entry points
src/runtime-dev/                 # Dev runtime
src/tradex/                      # Public API surface
```

### 2.2 Gets Split

| Source File | Target Files | Rationale |
|---|---|---|
| `domain/events/types.py` (1008 LOC) | See §3.1 | Per-context event files |
| `domain/capability_manifest/catalog.py` (905 LOC) | See §3.2 | Split by functional domain |
| `domain/universe.py` (808 LOC) | See §3.3 | Split 3 classes into own modules |
| `application/oms/context.py` (809 LOC) | See §3.4 | Split 4 classes into own modules |
| `application/trading/trading_orchestrator.py` (807 LOC) | See §3.5 | Split into focused modules |
| `analytics/replay/engine.py` (1125 LOC) | See §3.6 | Split into engine + statistics + simulation |

### 2.3 Moves

| Current Location | Target Location | Reason |
|---|---|---|
| `domain/capability_manifest/` | `domain/capabilities/manifest/` | Consolidate capability-related domain code |
| `domain/value_objects/capability.py` | `domain/capabilities/value_objects.py` | Co-locate with capability enum |
| `domain/capabilities/` | `domain/capabilities/enum.py` (rename) | Clarity: this is the capability enum |

### 2.4 Deletes (Phase 1 candidates)

| File/Directory | Reason |
|---|---|
| Dead event types (grep-confirmed zero publishers): `POSITION_CHANGED`, `RISK_BREACH`, `KILL_SWITCH_FLIPPED`, `RISK_VIOLATED`, `RECONCILIATION_OK` | Already removed from `EventType` enum 2026-07-10 |
| `Application/__pycache__/` directories | Generated artifacts |
| Duplicate `BrokerPlugin` metadata in `ensure_core_plugins()` | After Phase 2 static registry migration |

---

## 3. File Splits Detail

### 3.1 `domain/events/types.py` (1008 LOC) → Per-Context Event Files

```
domain/events/
├── __init__.py              # Re-exports all public symbols (backward compat)
├── bus.py                   # DomainEventBus ABC (unchanged)
├── types.py                 # Core: DomainEvent, EventType, EventPayload, EVENT_PAYLOADS
│                            # (kept as the canonical enum + payload catalog)
├── typed.py                 # TypedDomainEvent base + from_domain_event()
├── market_data.py           # QuoteUpdatedEvent, (future: TickEvent, DepthEvent)
├── orders.py                # OrderUpdatedEvent, TradeFilledEvent, TradeAppliedEvent,
│                            #   OrderRequestedEvent, OrderFilledEvent
├── execution.py             # ExecutionPlanBuiltEvent
├── position.py              # PositionClosedEvent
└── trade_id_key.py          # TradeIdKey value object
```

**Split logic:**
- `types.py` retains `DomainEvent`, `EventType`, `EventPayload`, `EVENT_PAYLOADS`, `make_payload`, `canonical_event_types` — the **enum + contract** layer
- `typed.py` retains `TypedDomainEvent` base class
- Each typed event goes to its context module: orders (OrderUpdated, TradeFilled, TradeApplied, OrderRequested, OrderFilled), market_data (QuoteUpdated), execution (ExecutionPlanBuilt), position (PositionClosed)
- `TradeIdKey` moves to its own file (identity utility, not an event)
- `__init__.py` re-exports everything for backward compatibility

**Estimated LOC per file:**
| File | LOC |
|---|---|
| `types.py` (reduced) | ~550 |
| `typed.py` | ~50 |
| `market_data.py` | ~80 |
| `orders.py` | ~130 |
| `execution.py` | ~40 |
| `position.py~60 |
| `trade_id_key.py` | ~70 |

### 3.2 `domain/capability_manifest/catalog.py` (905 LOC) → Split by Domain

```
domain/capabilities/
├── __init__.py
├── enum.py                  # Capability enum (from domain/capabilities/)
├── value_objects.py         # Capability, ExtensionInfo (from domain/value_objects/)
├── manifest/
│   ├── __init__.py          # Re-exports ALL_SURFACES
│   ├── market_data.py       # market_data.* surfaces (history, quote, ltp, depth)
│   ├── derivatives.py       # derivatives.* surfaces (option_chain, future_chain)
│   ├── orders.py            # orders.* surfaces (place, cancel, modify, status)
│   ├── portfolio.py         # portfolio.* surfaces (holdings, positions, funds)
│   ├── streaming.py         # streaming.* surfaces (subscribe, depth_stream)
│   ├── research.py          # research.* surfaces (screener, fundamentals, news)
│   └── system.py            # system.* surfaces (auth, health, capabilities)
├── query.py                 # Query helpers (from catalog.py module-level functions)
└── types.py                 # surface() factory + Surface dataclass
```

**Split logic:**
- The `CAPABILITY_SURFACES` tuple is split by functional domain into separate files
- Each file contains a tuple of `surface()` calls for its domain
- `manifest/__init__.py` imports and concatenates all: `ALL_SURFACES = market_data + derivatives + ...`
- Module-level query functions (`query_surface`, `find_surface`, etc.) move to `query.py`
- `surface()` factory + `Surface` dataclass moves to `types.py`

### 3.3 `domain/universe.py` (808 LOC) → 3 Classes

```
domain/
├── universe/
│   ├── __init__.py          # Re-exports Universe, Session, SessionDx
│   ├── universe.py          # Universe class (~170 LOC)
│   ├── session.py           # Session class (~520 LOC)
│   └── session_dx.py        # SessionDx class (~90 LOC)
├── _universe_helpers.py     # _as_side, _as_order_type, _as_product_type (~30 LOC)
```

**Split logic:**
- `Universe` (11 methods, instrument registry) → `universe/universe.py`
- `Session` (37 methods, session management + trading) → `universe/session.py`
- `SessionDx` (7 methods, derivatives helpers) → `universe/session_dx.py`
- Module-level helpers `_as_side`, `_as_order_type`, `_as_product_type` → `_universe_helpers.py`
- Backward-compat `__init__.py` re-exports all three classes

### 3.4 `application/oms/context.py` (809 LOC) → 4 Classes

```
application/oms/
├── __init__.py
├── context.py               # TradingContext class only (~550 LOC)
├── dlq_monitor.py           # DlqMonitorService (~60 LOC)
├── trade_cleanup.py         # ProcessedTradeCleanupService (~50 LOC)
├── cancellation.py          # CancellationResult (~30 LOC)
├── reconciliation/          # (existing, unchanged)
└── _internal/               # (existing, unchanged)
```

**Split logic:**
- `TradingContext` (30 methods, the main orchestrator) stays in `context.py`
- `DlqMonitorService` (5 methods, background DLQ watcher) → `dlq_monitor.py`
- `ProcessedTradeCleanupService` (4 methods, background cleanup) → `trade_cleanup.py`
- `CancellationResult` (1 method, simple data holder) → `cancellation.py`

### 3.5 `application/trading/trading_orchestrator.py` (807 LOC) → 5 Classes/Modules

```
application/trading/
├── __init__.py
├── trading_orchestrator.py  # TradingOrchestrator (core loop only, ~350 LOC)
├── orchestrator_config.py   # OrchestratorConfig dataclass (~30 LOC)
├── signal_evaluator.py      # Signal evaluation logic (_evaluate_candidate, _fetch_features, ~100 LOC)
├── order_placer.py          # Order placement logic (_place_order, _calculate_quantity, _resolve_equity, ~120 LOC)
└── event_publisher.py       # Event publishing (_publish_execution_events, _publish_plan_built, _publish_order_requested, ~80 LOC)
```

**Split logic:**
- `TradingOrchestrator` stays in `trading_orchestrator.py` but delegates to collaborators
- `OrchestratorConfig` → `orchestrator_config.py`
- Signal evaluation methods (`on_candidate`, `_fetch_features`, `_evaluate_candidate`) → `signal_evaluator.py`
- Order placement methods (`_place_order`, `_calculate_quantity`, `_resolve_equity`, `_signal_to_order_command`, `_intent_to_command`) → `order_placer.py`
- Event publishing methods (`_publish_execution_events`, `_publish_plan_built`, `_publish_order_requested`) → `event_publisher.py`

### 3.6 `analytics/replay/engine.py` (1125 LOC) → 3 Classes

```
analytics/replay/
├── __init__.py
├── engine.py                # ReplayEngine (orchestration only, ~450 LOC)
├── statistics.py            # ReplayStatistics computation (~200 LOC)
└── simulation.py            # Bar-level simulation (_process_signal_simulated, _close_position, etc., ~350 LOC)
```

**Split logic:**
- `ReplayEngine` core (`run`, `_run_single`, `_run_multi_symbol`, `_new_window_state`, `_append_bar_window`) → `engine.py`
- `compute_statistics` and helper methods → `statistics.py` (new `ReplayStatistics` class or pure functions)
- Simulation methods (`_process_signal`, `_process_signal_simulated`, `_process_signal_via_oms`, `_close_position`, `_close_position_at_price`) → `simulation.py` (mixin or helper class)
- `_record_session_fill`, `_compute_commission`, `_compute_slippage_pct` → `statistics.py`

---

## 4. Before / After Directory Trees

### Before (Current)

```
src/
├── analytics/
│   ├── replay/
│   │   ├── engine.py              # 1125 LOC ← monolith
│   │   └── ...
│   └── ...
├── application/
│   ├── oms/
│   │   ├── context.py             # 809 LOC ← monolith
│   │   ├── _internal/
│   │   └── reconciliation/
│   ├── trading/
│   │   └── trading_orchestrator.py # 807 LOC ← monolith
│   └── ...
├── domain/
│   ├── capabilities/
│   │   └── (enum + value objects)
│   ├── capability_manifest/
│   │   └── catalog.py             # 905 LOC ← monolith
│   ├── events/
│   │   ├── types.py               # 1008 LOC ← monolith
│   │   └── bus.py
│   ├── universe.py                # 808 LOC ← monolith (3 classes)
│   └── value_objects/
│       └── capability.py
└── infrastructure/
    ├── adapter_factory.py
    ├── broker_plugin.py
    └── event_bus/
```

### After (Target — Phase 1)

```
src/
├── analytics/
│   ├── replay/
│   │   ├── engine.py              # ~450 LOC (orchestration only)
│   │   ├── statistics.py          # NEW: ~200 LOC (statistics computation)
│   │   ├── simulation.py          # NEW: ~350 LOC (bar-level simulation)
│   │   └── ...
│   └── ...
├── application/
│   ├── oms/
│   │   ├── context.py             # ~550 LOC (TradingContext only)
│   │   ├── dlq_monitor.py         # NEW: ~60 LOC
│   │   ├── trade_cleanup.py       # NEW: ~50 LOC
│   │   ├── cancellation.py        # NEW: ~30 LOC
│   │   ├── _internal/
│   │   └── reconciliation/
│   ├── trading/
│   │   ├── trading_orchestrator.py # ~350 LOC (core loop)
│   │   ├── orchestrator_config.py  # NEW: ~30 LOC
│   │   ├── signal_evaluator.py     # NEW: ~100 LOC
│   │   ├── order_placer.py         # NEW: ~120 LOC
│   │   └── event_publisher.py      # NEW: ~80 LOC
│   └── ...
├── domain/
│   ├── capabilities/
│   │   ├── __init__.py
│   │   ├── enum.py                # MOVED from capabilities/
│   │   ├── value_objects.py       # MOVED from value_objects/capability.py
│   │   └── manifest/
│   │       ├── __init__.py        # ALL_SURFACES aggregation
│   │       ├── types.py           # surface() factory
│   │       ├── market_data.py     # NEW: market data surfaces
│   │       ├── derivatives.py     # NEW: derivatives surfaces
│   │       ├── orders.py          # NEW: order surfaces
│   │       ├── portfolio.py       # NEW: portfolio surfaces
│   │       ├── streaming.py       # NEW: streaming surfaces
│   │       ├── research.py        # NEW: research surfaces
│   │       ├── system.py          # NEW: system surfaces
│   │       └── query.py           # NEW: query helpers
│   ├── events/
│   │   ├── __init__.py            # Re-exports (backward compat)
│   │   ├── types.py               # ~550 LOC (enum + payloads only)
│   │   ├── bus.py                 # Unchanged
│   │   ├── typed.py               # NEW: ~50 LOC (TypedDomainEvent base)
│   │   ├── market_data.py         # NEW: ~80 LOC
│   │   ├── orders.py              # NEW: ~130 LOC
│   │   ├── execution.py           # NEW: ~40 LOC
│   │   ├── position.py            # NEW: ~60 LOC
│   │   └── trade_id_key.py        # NEW: ~70 LOC
│   ├── universe/
│   │   ├── __init__.py            # Re-exports
│   │   ├── universe.py            # ~170 LOC
│   │   ├── session.py             # ~520 LOC
│   │   └── session_dx.py          # ~90 LOC
│   └── _universe_helpers.py       # ~30 LOC
└── infrastructure/
    ├── adapter_factory.py          # Unchanged
    ├── broker_plugin.py            # Unchanged
    └── event_bus/                  # Unchanged
```

**Summary of changes:**

| Metric | Before | After |
|---|---|---|
| Files > 800 LOC | 6 | 0 |
| Largest file | 1125 LOC | ~550 LOC |
| New modules created | — | 18 |
| Modules deleted | 0 | 0 |
| Modules moved | 0 | 3 |

---

## 5. Dependency Rules Per Directory

### `domain/` — No outward dependencies

```
domain/ depends on: NOTHING (pure domain)
domain/ may depend on:
  - Python stdlib only
  - Other domain/ modules (same layer)
```

**Forbidden imports from domain:**
- `application.*`
- `infrastructure.*`
- `brokers.*`
- `analytics.*`
- `interface.*`

### `application/` — Depends on domain only

```
application/ depends on:
  - domain/ (ports, entities, value objects)
  - application/ (sibling modules within application)

application/ may NOT depend on:
  - infrastructure/ (use domain ports instead)
  - brokers/
  - analytics/
  - interface/
```

**Exception:** `application/oms/context.py` imports `infrastructure.event_bus` via
the `DomainEventBus` port — this is allowed because it receives the port via
dependency injection, not direct import.

### `analytics/` — Depends on domain only

```
analytics/ depends on:
  - domain/ (entities, value objects, ports)
  - analytics/ (sibling modules)

analytics/ may NOT depend on:
  - application/
  - infrastructure/
  - brokers/
  - interface/
```

### `infrastructure/` — Depends on domain (ports only)

```
infrastructure/ depends on:
  - domain/ports/ (interface implementations)
  - domain/ (entities, value objects)
  - infrastructure/ (sibling modules)

infrastructure/ may NOT depend on:
  - application/
  - brokers/
  - analytics/
  - interface/
```

**Exception:** `infrastructure/adapter_factory.py` and `infrastructure/broker_plugin.py`
are populated by broker packages at import time via self-registration — they do not
import brokers themselves.

### `brokers/` — Depends on domain + infrastructure

```
brokers/ depends on:
  - domain/ (entities, value objects, ports)
  - infrastructure/ (adapter_factory, broker_plugin — for self-registration)
  - brokers/common/ (shared utilities)

brokers/ may NOT depend on:
  - application/
  - analytics/
  - interface/
```

### `interface/` — Top of the dependency graph

```
interface/ depends on:
  - application/ (use cases)
  - domain/ (read models)
  - infrastructure/ (directly, for composition roots)

interface/ is the only layer that may import from all layers.
```

### Import Linter Rules

```python
# .importlinter (existing contracts)
[importlinter]
root_package = src

[importlinter:contract:1]
name = Domain Independence
type = independence
source_modules = domain
invalid_target_modules = application, infrastructure, brokers, analytics, interface

[importlinter:contract:2]
name = Application Depends on Domain Only
type = layers
source_modules = application
target_modules = domain

[importlinter:contract:3]
name = Infrastructure Depends on Domain Ports
type = layers
source_modules = infrastructure
target_modules = domain

[importlinter:contract:4]
name = Broker Isolation
type = independence
source_modules = brokers.dhan, brokers.upstox, brokers.paper
invalid_target_modules = application, analytics
```

### Dependency Direction Summary

```
┌─────────────┐
│  interface   │  ← imports everything
├─────────────┤
│ application  │  ← depends on domain
├─────────────┤
│  analytics   │  ← depends on domain
├─────────────┤
│   brokers    │  ← depends on domain + infrastructure (for registration)
├─────────────┤
│infrastructure│  ← implements domain ports
├─────────────┤
│    domain    │  ← depends on nothing (pure)
└─────────────┘
```
