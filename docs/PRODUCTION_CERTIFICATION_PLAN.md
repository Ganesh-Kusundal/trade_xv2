# Trade_XV2 — Production Certification Plan
## The Three-Architect Roadmap

> Authored from the combined perspectives of Dr. Venkat Subramaniam
> (composability, simplicity, deletion), Martin Fowler (deduplication,
> explicit ownership), and Robert C. Martin (single responsibility,
> dependencies inward, no accidental complexity).

---

## Guiding Principles

1. **One owner per concept.** Every business idea has exactly one
   source of truth; the others are deleted.
2. **No shared mutable state.** Everything that mutates is owned by
   one thread, behind a LifecycleManager.
3. **Silent failure is a production incident.** Every `except` must
   log, count, and (where appropriate) alert.
4. **Delete first, refactor second, add abstractions last.**
5. **Code is only as good as its tests.** No untested code ships.

---

## Audit Findings (Wave 1 — research complete)

### Domain Duplication
- `Order`: **3 copies** (domain.py dataclass, models.py Pydantic, schemas.py)
- `Position`: **2 copies** (domain.py, models.py, plus analytics/replay)
- `MarketDepth`: **7 variants** (MarketDepth5/30/D5/D30/Level/Level5/Level30) in models.py
- `Quote`: **2 copies** (domain.py, dhan/domain.py)
- `Enums`: `OrderStatus/OrderType/ProductType/Side/Validity` in **2 places** (domain.py, enums.py)
- **Status:** Pydantic models.py is marked DEPRECATED but still 534 LOC

### Gateway / Factory Duplication
- 2 abstract gateway bases: `MarketDataGateway` (canonical, frozen v1.0) and `BrokerConnection` (DEPRECATED, 48-value `Capability` enum)
- 3 concrete gateways: `BrokerGateway` (Dhan), `UpstoxBrokerGateway`, `IntelligentGateway` (router), `DataLakeGateway` (read-only)
- 2 Upstox factories: `UpstoxBrokerFactory.create()` and `UpstoxBroker.__new__()` (in `__init__.py`)

### Kill Switch Triplication
- `RiskConfig.kill_switch` (in-process boolean, oms/risk_manager.py)
- `UpstoxKillSwitchClient/Adapter` (Upstox broker API, upstox/kill_switch/)
- `Connection.Capability.KILL_SWITCH` (enum, DEPRECATED)
- `KillSwitchPort` (ABC, api/ports.py)

### Background Thread Hazards
- `TokenRefreshScheduler` (daemon, started in factory, never stopped)
- `TradingContext._reconciliation_loop` (daemon, started in __init__, only stop_reconciliation() stops it)
- `DhanWebSocket._thread` (daemon, never stopped on close)
- `DhanOrderStream._thread` (daemon, never stopped)
- `UpstoxMarketDataV3` — implicit thread pool

### Module-Level Globals
- `_token_refresh_lock` in `brokers/dhan/factory.py` — module global, imported across module boundaries (token_scheduler imports it)
- `_DOMAIN_TYPES` in `brokers/common/event_log.py` — populated only at runtime, breaks across processes

### Silent Failures
- 30+ bare `except Exception:` blocks across Upstox WebSocket, reconciliation, and order paths
- Most in `brokers/upstox/websocket/market_data_v3.py`, `brokers/upstox/reconciliation/service.py`
- `except: pass` patterns in `EventBus` (FIXED in Phase 1) and `EventLog` (FIXED in Phase 1)

### Critical Untested Files
- `brokers/common/oms/context.py` (TradingContext — central wiring, no test)
- `brokers/dhan/token_scheduler.py` (background refresh)
- `brokers/common/intelligent_gateway.py` (multi-broker router)
- `datalake/gateway.py` (read-only gateway)
- `brokers/upstox/broker.py` (20+ sub-adapters)
- `brokers/dhan/websocket.py` (718 LOC, reconnect + order stream)

### Risk Manager Defects
- `set_kill_switch` mutates `_config` without lock
- `check_order` reads `_config` and `_daily_pnl` without lock
- `update_daily_pnl` writes without lock
- Daily loss check is REACTIVE (fires after breach) not PREVENTIVE
- `_daily_pnl` is never reset at day rollover

### CLI Routing
- 50+ `elif` blocks in `cli/main.py` (428 LOC)
- No command registry, no plugin system
- `TradexTuiApp` imported but never launched

---

## Execution Waves

### Wave 1: Research (DONE)
- Domain model audit ✓
- Gateway abstraction audit ✓
- Concurrency & lifecycle audit ✓
- Observability gap audit ✓

### Wave 2: Concurrency & Lifecycle (THIS WAVE)
**Goal:** Every background service has a LifecycleManager with start/stop/health.

**Files to create:**
- `brokers/common/lifecycle/__init__.py`
- `brokers/common/lifecycle/manager.py` (LifecycleManager)
- `brokers/common/lifecycle/managed_service.py` (ManagedService Protocol)
- `brokers/common/lifecycle/health.py` (HealthStatus, HealthCheck)

**Files to refactor:**
- `brokers/dhan/token_scheduler.py` — implement ManagedService
- `brokers/common/oms/context.py` — replace ad-hoc _recon_thread with ManagedService
- `brokers/dhan/websocket.py` — implement ManagedService for both feed and order stream
- `brokers/dhan/factory.py` — remove `_token_refresh_lock` global, inject lock via context

**New tests:**
- `tests/unit/test_lifecycle_manager.py` — start/stop/health, idempotency, multi-service
- `tests/unit/test_managed_service_protocol.py` — protocol conformance

**Acceptance:**
- Every `daemon=True` thread is now owned by a LifecycleManager
- A misbehaving service's failure is observable via `health()` snapshot
- Process shutdown drains all services in <5s

### Wave 3: Domain Consolidation (next)
**Goal:** One owner per concept. Delete everything else.

**Decisions:**
- **KEEP** `brokers/common/core/domain.py` (489 LOC, dataclass, canonical)
- **DELETE** `brokers/common/core/models.py` (534 LOC, Pydantic, DEPRECATED)
- **DELETE** `brokers/common/core/enums.py` (135 LOC, DEPRECATED)
- **DELETE** `brokers/common/data_contracts.py` (pure re-exports)
- **CONSOLIDATE** `brokers/dhan/domain.py` into domain.py
- **CONSOLIDATE** `analytics/replay/models.py` to use common domain
- **MIGRATE** every consumer of models.py / enums.py / data_contracts.py to domain.py
- **DELETE** `MarketDepth5/30/D5/D30/Level/Level5/Level30` variants — use `MarketDepth` with `depth_levels=5/30` config

**Acceptance:**
- Zero references to Pydantic `Order`/`Position`/`Quote`
- Zero `MarketDepth5/D5/Level5` classes
- All consumers import from `brokers.common.core.domain`

### Wave 4: OMS Hardening
**Goal:** Explicit state machine, immutable risk snapshots, position reconciliation.

**Files to create:**
- `brokers/common/oms/state_machine.py` (OrderStateMachine)
- `brokers/common/oms/risk_snapshot.py` (immutable RiskSnapshot replacing mutable config)
- `brokers/common/oms/reconciliation.py` (PositionReconciliationService with drift detection)

**Files to refactor:**
- `brokers/common/oms/order_manager.py` — wire OrderStateMachine
- `brokers/common/oms/risk_manager.py` — immutable snapshots, no shared mutable state
- `brokers/common/oms/position_manager.py` — reconciliation hooks

**New tests:**
- `tests/unit/test_order_state_machine.py` — all transitions
- `tests/unit/test_risk_snapshot.py` — immutability under concurrent check

**Acceptance:**
- An order in CANCELLED state cannot transition to FILLED
- `RiskManager.check_order` is safe under 1000 concurrent threads
- Daily PnL is reset at configured rollover time

### Wave 5: Gateway Consolidation
**Goal:** One gateway abstraction. Capability discovery via `gateway.supports("options")`.

**Decisions:**
- **KEEP** `MarketDataGateway` (frozen v1.0)
- **DELETE** `BrokerConnection` ABC
- **DELETE** `IntelligentGateway` (router is a strategy-layer concern, not a gateway)
- **SPLIT** `DataLakeGateway` — extract `MarketDataReader` interface
- **MERGE** Upstox `UpstoxBroker.__new__` factory and `UpstoxBrokerFactory.create` into one

**Unify kill switch:**
- Single `KillSwitch` Port + per-broker adapter
- `RiskManager` reads from `KillSwitch.is_active()`
- `Connection.Capability.KILL_SWITCH` removed

**Acceptance:**
- 1 gateway abstract base, 1 reader abstract base
- 1 kill switch port, 1 in-process implementation, 1 broker API adapter per broker
- `gateway.supports("options")` works for every broker

### Wave 6: Observability Program
**Goal:** Every critical event emits a metric. Every silent failure logs+couts+alerts.

**Files to expand:**
- `brokers/common/observability/event_metrics.py` — add OMS/broker/market-data/risk dimensions
- `brokers/common/observability/structured_logging.py` — new module for key=value logs
- All `except: pass` blocks get log + metric + (where critical) DLQ entry

**Mandatory metrics:**
- OMS: orders_submitted, orders_rejected, orders_failed, fills_received, duplicate_fills
- Broker: api_latency_p50/p95/p99, api_errors, rate_limit_hits
- Market data: tick_rate_per_symbol, message_gap, stale_feed_seconds
- Risk: daily_loss_pct, gross_exposure, kill_switch_state

**Critical alerts (must page):**
- Order rejected (broker side)
- Position mismatch > N
- Duplicate fill
- No ticks for 30s (per subscribed symbol)
- Token refresh failure
- Kill switch activated

**Acceptance:**
- Every critical event emits a counter or histogram
- Every silent failure now logs at ERROR with a metric
- Day-1 monitoring is wired into the lifecycle health() snapshot

### Wave 7: Test Certification
**Goal:** Critical paths have deterministic, isolated, repeatable tests.

**Test categories to add:**
- **Unit:** OrderManager, PositionManager, RiskManager, EventBus (all >90% line coverage)
- **Contract:** broker adapters produce identical domain types
- **Replay:** captured session → replayed → identical state
- **Concurrency:** 1000 simultaneous events, duplicate fills, reconnect storms
- **Chaos:** broker timeout, broker disconnect, partial fills, network partition
- **Failover:** token expiry mid-flight, scheduler failure, etc.

**Acceptance:**
- All critical paths tested
- 100% of CI runs include replay determinism check
- Chaos tests pass under fault injection

### Wave 8: Code Deletion Sprint
**Goal:** 20-30% code reduction.

**Delete:**
- All DEPRECATED modules
- `cli/views/tui_app.py` and `cli/widgets/*` (TUI never launched)
- `analytics/visualizations/charts.py` (no production import)
- `analytics/reports/reports.py` (no production import)
- `brokers/common/intelligent_gateway.py` (after Wave 5)
- `brokers/common/core/{models,enums,facade,broker,schemas,connection}.py`

**Merge:**
- Two Upstox factories into one
- Two view systems (analytics/views, datalake/views)
- Multiple DTOs in models.py into domain.py request/response dataclasses

**Acceptance:**
- 20-30% fewer LOC
- No "kept for backward compatibility" comments
- Zero grep hits for DEPRECATED / "no longer used" / "kept for compatibility"

### Wave 9: Deployment Gate Certification
**Final GO / NO-GO** based on:
- ✅ Architecture: single domain, single gateway, no dead code
- ✅ Reliability: no silent failures, idempotent trades, replay verified
- ✅ Observability: metrics, alerts, structured logs
- ✅ Testing: unit, integration, replay, concurrency, chaos

---

## Parallelization Plan

The waves above are mostly **sequential** because each depends on the
prior. But within each wave, the work is **massively parallel**:

| Wave | Parallel Tracks |
|------|----------------|
| 2 | (a) LifecycleManager core (b) Risk snapshot (c) Refactor TokenRefreshScheduler (d) Refactor reconciliation |
| 3 | (a) Migrate OMS (b) Migrate brokers.dhan (c) Migrate brokers.upstox (d) Migrate cli |
| 4 | (a) State machine (b) Risk snapshot (c) Reconciliation service (d) OMS hooks |
| 5 | (a) Delete BrokerConnection (b) Delete IntelligentGateway (c) Unify kill switch (d) Split DataLakeGateway |
| 6 | (a) Metrics expansion (b) Silent failure audit (c) Structured logging (d) Day-1 alerts |
| 7 | (a) Unit tests (b) Contract tests (c) Replay tests (d) Chaos tests |
| 8 | (a) Deprecation removal (b) TUI removal (c) Analytics removal (d) Factory merge |

---

## Status

- Wave 1 (Research): **DONE**
- Wave 2 (Concurrency): **IN PROGRESS** ← start here
- Wave 3 (Domain): pending
- Wave 4 (OMS): pending
- Wave 5 (Gateway): pending
- Wave 6 (Observability): pending
- Wave 7 (Tests): pending
- Wave 8 (Deletion): pending
- Wave 9 (Gate): pending

Per the Production Survival Program, **Event Integrity → OMS Correctness
→ Idempotency → Replay Determinism** were the four pre-conditions; they
are now green. The next step is **Lifecycle Management** because every
deployed process has background threads that today cannot be safely
stopped.
