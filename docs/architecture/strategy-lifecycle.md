# Strategy Lifecycle Management — Current State

## Summary

Strategy lifecycle management is **defined in domain but not implemented in production**.
Three lifecycle events (`STRATEGY_ACTIVATED`, `STRATEGY_PAUSED`, `STRATEGY_DISABLED`) exist
in the event catalog with payload schemas, and a `StrategyState` enum defines valid
transitions — but no production code publishes, subscribes to, or enforces these transitions.

The only runtime strategy control is the binary **kill switch** (`RiskManagerPort.is_kill_switch_active`),
which is all-or-nothing: it cannot target individual strategies.

---

## What Exists

### 1. Domain Events (defined, orphaned)

| Event | Defined In | Payload Schema | Published By | Subscribed By |
|-------|-----------|----------------|--------------|---------------|
| `STRATEGY_ACTIVATED` | `domain/events/types.py:177` | `required: strategy_name; optional: activated_by` | nobody | nobody |
| `STRATEGY_PAUSED` | `domain/events/types.py:178` | `required: strategy_name; optional: reason` | nobody | nobody |
| `STRATEGY_DISABLED` | `domain/events/types.py:179` | `required: strategy_name, reason` | nobody | nobody |

Payload schemas are registered in `domain/events/payloads.py:263-273`.

### 2. StrategyState Enum (defined, unused)

Location: `analytics/strategy/models.py:47-72`

```
Transitions:
  INACTIVE → ACTIVE    (activate strategy)
  ACTIVE → PAUSED      (temporarily disable)
  ACTIVE → DISABLED    (permanently disable)
  PAUSED → ACTIVE      (resume strategy)
  PAUSED → DISABLED    (disable from paused state)
  DISABLED → {}        (terminal state)
```

Properties: `is_active` (True if ACTIVE), `is_terminal` (True if DISABLED).

This enum is **never imported or used** outside its own module.

### 3. StrategyRegistry (class discovery only)

Location: `analytics/strategy/registry.py`

Provides class-level discovery and instantiation:
- `register(name, cls)` — manual registration
- `discover(package)` — importlib-based auto-discovery
- `create(name)` — factory instantiation
- `list()` — enumerate registered names
- `self_check(strategies)` — golden-bar validation at construction

This is a **static registry** — it knows nothing about runtime state. There is no
`activate(name)`, `pause(name)`, or `disable(name)` method.

### 4. TradingOrchestrator (service lifecycle only)

Location: `application/trading/trading_orchestrator.py`

Implements `ManagedServicePort` with `start()` / `stop()` / `health()`:
- `start()` subscribes to `CANDIDATE_GENERATED` events
- `stop()` unsubscribes and logs stats
- Lifecycle managed by `LifecycleManager` (system-level, not strategy-level)

The orchestrator is **strategy-agnostic** — it delegates to `StrategyEvaluator` (injected),
which wraps `StrategyPipeline` via `StrategyPipelineEvaluator` bridge. There is no mechanism
to pause or disable individual strategies within the pipeline.

### 5. Kill Switch (binary control)

Location: `application/trading/trading_orchestrator.py:478-486`

`_is_kill_switch_active()` delegates to `RiskManagerPort.is_kill_switch_active()`.
When active, **all** signal execution is blocked. This is the only runtime control,
and it cannot target individual strategies.

---

## What's Missing

| Capability | Status | Notes |
|-----------|--------|-------|
| Per-strategy activation/pause/disable | Not implemented | `StrategyState` defined but unused |
| Strategy lifecycle event publishing | Not implemented | Events defined, never published |
| Strategy lifecycle event handling | Not implemented | No subscribers exist |
| Runtime strategy enable/disable | Not implemented | Pipeline is stateless |
| Strategy health monitoring | Not implemented | Only orchestrator-level health exists |
| Strategy config persistence | Not implemented | Strategies are constructed at startup |
| Pause/resume without restart | Not implemented | Would require pipeline statefulness |

---

## Intended Flow (inferred from domain definitions)

Based on the event schemas and `StrategyState` transitions, the intended architecture is:

```
User/System trigger
    │
    ▼
StrategyManager (missing)
    │
    ├── transition STRATEGY_ACTIVATED  →  STRATEGY_PAUSED  →  STRATEGY_DISABLED
    │        publishes events on each transition
    │
    ▼
EventBus (STRATEGY_ACTIVATED / STRATEGY_PAUSED / STRATEGY_DISABLED)
    │
    ▼
TradingOrchestrator (would filter candidates by active strategies)
    │
    ▼
StrategyPipeline (would check strategy state before evaluating)
```

The `StrategyManager` (or equivalent) is the missing component that would:
1. Own the `StrategyState` for each registered strategy
2. Enforce valid transitions
3. Publish lifecycle events on state changes
4. Expose API commands (activate/pause/disable)

---

## Architecture Implications

### Current: Stateless Pipeline

```
StrategyPipeline
  └─ strategies: list[Strategy]  (set once at construction)
     └─ evaluate_single(candidate, features)  →  always runs ALL strategies
```

Every strategy in the pipeline is always evaluated. The only way to "disable" a
strategy is to not include it at construction time (requires restart).

### Needed: Stateful Strategy Control

```
StrategyManager
  └─ _states: dict[str, StrategyState]
  └─ activate(name) → publishes STRATEGY_ACTIVATED
  └─ pause(name)    → publishes STRATEGY_PAUSED
  └─ disable(name)  → publishes STRATEGY_DISABLED

StrategyPipeline (modified)
  └─ evaluate_single() checks StrategyManager state before running each strategy
```

---

## Related Files

| File | Role |
|------|------|
| `domain/events/types.py` | Event type definitions (lines 176-179) |
| `domain/events/payloads.py` | Payload schemas (lines 258-273) |
| `analytics/strategy/models.py` | `StrategyState` enum (lines 47-72) |
| `analytics/strategy/registry.py` | Class-level strategy registry |
| `analytics/strategy/pipeline.py` | Stateless strategy evaluation |
| `analytics/strategy/evaluator_bridge.py` | Adapts pipeline to domain port |
| `application/trading/trading_orchestrator.py` | Service lifecycle (start/stop) |
| `domain/ports/strategy_evaluator.py` | Domain port for strategy evaluation |
| `domain/ports/lifecycle.py` | `ManagedServicePort` / `LifecycleManagerPort` |
| `application/strategy_engine/__init__.py` | Confirms `LiveStrategyEngine` removed (G5) |
