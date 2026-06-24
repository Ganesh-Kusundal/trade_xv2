# 5-Why Architecture Review — TradeXV2

**Date**: 2026-06-24
**Scope**: Full platform audit — market data, events, strategies, scanners, brokers, risk, storage, observability, testing
**Method**: Principal Engineer 5-Why root cause analysis

---

## Platform Overview

- **Size**: 1,055 Python source files across 30 top-level directories
- **Test suite**: 386 test files (unit, contract, integration, chaos, e2e, property, stress)
- **Brokers**: Dhan (full), Upstox (full), Paper (simulator)
- **Architecture**: Hexagonal — domain layer, infrastructure layer, application layer, broker adapters

---

## FINDING 1 — Broker Layer EventBus Is Empty

**Severity**: 🟠 High
**File**: `brokers/common/event_bus/` (directory contains only `__pycache__/` and `tests/`)
**Production EventBus**: `infrastructure/event_bus/event_bus.py`

### 5-Why Chain

1. **Why** can't broker-layer code publish events? — The `brokers/common/event_bus/` directory has no Python source files.
2. **Why** is the directory empty? — The EventBus was migrated to `infrastructure/event_bus/` during the P4 (Phase 4) event-sourcing work, but the broker-layer package was never cleaned up.
3. **Why** wasn't it cleaned up? — The `brokers/common/` package still re-exports from `infrastructure.event_bus` via shim modules (`brokers/common/event_log.py`, `brokers/common/observability/event_metrics.py`), so imports still resolve. But the empty `event_bus/` directory creates confusion.
4. **Why** does the shim pattern persist? — Historical migration from monolithic `brokers/common/core/` to separated `infrastructure/` + `domain/` packages. The shim modules were left as backward-compat bridges.
5. **Root cause**: Incomplete package migration left a phantom directory that misleads developers and tooling (IDE auto-imports from the wrong path).

### Mitigation

- Delete `brokers/common/event_bus/` entirely (it has no source files).
- Verify all imports resolve through `infrastructure.event_bus` or the existing shims.
- Update `pyproject.toml` package discovery to remove phantom entry.

---

## FINDING 2 — agent.md References Deprecated Paths

**Severity**: 🟡 Medium
**File**: `agent.md` (534 lines)

### 5-Why Chain

1. **Why** does `agent.md` reference `brokers/common/core/domain.py`? — The onboarding guide was written before the domain-model migration to `domain/` package.
2. **Why** wasn't it updated? — The 2026-06-15 production certification remediation deleted deprecated modules and moved types to `domain/`, but the guide was only partially updated (new Status Update section appended at bottom).
3. **Why** is partial update insufficient? — The main body still references `models.py`, `enums.py`, `connection.py`, `facade.py` — all deleted. New contributors following the guide will look in wrong directories.
4. **Why** no automated check? — No test validates that `agent.md` paths correspond to actual files. The import-linter catches import violations but not documentation staleness.
5. **Root cause**: Documentation maintenance not coupled to code migration — no gate process ensures docs stay current when modules move.

### Mitigation

- Rewrite `agent.md` body to reflect current `domain/`, `application/oms/`, `infrastructure/event_bus/` layout.
- Add a CI check: grep `agent.md` for known-deleted paths and fail if found.

---

## FINDING 3 — Dual EventBus Without Clear Migration Path

**Severity**: 🟡 Medium
**Files**: `infrastructure/event_bus/event_bus.py` (sync), `infrastructure/event_bus/async_event_bus.py` (async), `infrastructure/event_bus/factory.py`

### 5-Why Chain

1. **Why** are there two EventBus implementations? — Sync `EventBus` was the original; `AsyncEventBus` was added for high-throughput scenarios with backpressure (BLOCK/DROP/ERROR policies).
2. **Why** hasn't one replaced the other? — The `AsyncPublishAdapter` wrapper provides a uniform `async publish()` API, but migration is gated by the `USE_ASYNC_EVENT_BUS` env var. No deadline or ownership assigned.
3. **Why** is migration stalled? — `TradingContext` creates both buses (`self._event_bus` and `self._async_bus`) but most handlers are synchronous. Converting handlers to async requires touching every subscriber.
4. **Why** is handler conversion expensive? — Each handler must be audited for blocking I/O, then wrapped with `asyncio.to_thread` or rewritten. The bus supports both sync and async handlers, but the overhead of thread-pool dispatch defeats the purpose.
5. **Root cause**: No phased migration plan with deadlines — the async bus shipped as opt-in without a decommission path for the sync bus.

### Mitigation

- Define Phase 5 goal: async bus becomes default for OMS event path (order/trade/risk events).
- Keep sync bus for CLI/diagnostic paths (low throughput, no backpressure needed).
- Add `DEPRECATED` warning to sync EventBus.publish() when `USE_ASYNC_EVENT_BUS=1`.

---

## FINDING 4 — ProcessedTradeRepository Lifecycle Complexity

**Severity**: 🟡 Medium
**File**: `infrastructure/event_bus/processed_trade_repository.py`

### 5-Why Chain

1. **Why** does `ProcessedTradeRepository` have a daemon cleanup thread? — Stale idempotency entries (trade IDs processed >24h ago) would accumulate indefinitely without cleanup.
2. **Why** is cleanup a daemon thread? — The repository must be available immediately on startup (singleton-per-path pattern), so background cleanup runs independently.
3. **Why** is this risky? — Daemon threads die silently on process exit. If the process crashes between `mark_processed()` and JSONL flush, the idempotency ledger loses entries. On restart, duplicate trades could be re-processed.
4. **Why** isn't crash recovery handled? — The JSONL file is append-only with fsync, but there's no checkpoint/compaction. On restart, the entire file is reloaded into the in-memory set — O(n) startup cost.
5. **Root cause**: Idempotency persistence was designed for correctness (no double-processing) but not for operational resilience (crash recovery, startup performance).

### Mitigation

- Add periodic compaction: rewrite JSONL with only entries from last 24h (bounded file size).
- Add startup metric: time to load idempotency ledger. Alert if >1s.
- Consider SQLite-backed idempotency (like PersistentDeadLetterQueue) for atomic writes.

---

## FINDING 5 — Scanner DataFrame Copy Under ThreadPoolExecutor

**Severity**: 💡 Recommendation
**File**: `analytics/scanner/runner.py:303`

### 5-Why Chain

1. **Why** does each scanner receive `universe.copy()`? — Scanners mutate the DataFrame in-place during feature computation (`result["score_rsi"] = ...`). Without copying, concurrent scanners would corrupt shared state.
2. **Why** is copy expensive? — A universe of 500 symbols × 1D candles with 6+ feature columns can be 50-100MB. Copying 4 scanners = 200-400MB peak.
3. **Why not use immutable views?** — Pandas doesn't support true immutable DataFrames. `.copy()` is the standard thread-safety pattern.
4. **Why not reduce copy cost?** — Could use `copy(deep=False)` for column-selection scenarios, but feature computation adds new columns requiring deep copy.
5. **Root cause**: DataFrame is the wrong abstraction for concurrent feature computation — columnar storage (Polars) or pre-computed feature stores would eliminate copies.

### Mitigation

- Short-term: Log peak memory per ScannerRunner invocation for monitoring.
- Medium-term: Evaluate Polars lazy evaluation for zero-copy feature pipelines.
- Long-term: Pre-materialize feature columns in data lake (already partially done with `m_daily_*` tables).

---

## FINDING 6 — OMS Backward-Compat Shim at brokers/common/oms

**Severity**: 💡 Recommendation
**File**: `brokers/common/oms/_internal/__init__.py`

### 5-Why Chain

1. **Why** does `brokers/common/oms/_internal/__init__.py` exist? — It's a 3-line shim: `from application.oms._internal import *`.
2. **Why** was this created? — During OMS migration from `brokers/common/oms/` to `application/oms/`, existing imports needed to keep working.
3. **Why is it still needed?** — Check if any production code imports from `brokers.common.oms._internal`. If not, it's dead code.
4. **Why might it confuse developers?** — Two paths to the same code (`application.oms._internal` and `brokers.common.oms._internal`) creates ambiguity about canonical location.
5. **Root cause**: Migration shim outlived its purpose — no cleanup gate after migration completed.

### Mitigation

- Grep for `brokers.common.oms._internal` imports across codebase.
- If zero production imports remain, delete the shim.
- If imports exist, migrate them to `application.oms._internal` and then delete.

---

## FINDING 7 — Import Linter Contract Gaps

**Severity**: 🟠 High
**File**: `pyproject.toml` (lines 200-241) and `.import-linter.ini`

### 5-Why Chain

1. **Why** do test files bypass import restrictions? — The `application.oms` → `brokers` forbidden contract has 4 `ignore_imports` entries for test files.
2. **Why** do tests need broker imports? — E2E tests (`test_oms_e2e.py`, `test_execution_service.py`) wire real broker gateways to verify integration.
3. **Why** is this a problem? — Test exceptions can mask architectural violations. If a new test adds a forbidden import, the ignore list grows without review.
4. **Why** no automated audit? — `import-linter` runs as a CI step, but the ignore list is static in `pyproject.toml`. No diff-based check for new ignores.
5. **Root cause**: Import boundary enforcement lacks lifecycle management — ignores accumulate without expiry or review triggers.

### Mitigation

- Add `# REVIEW-DATE: 2026-06-24` comments to each ignore_imports entry.
- CI step: fail if any ignore_imports entry is >90 days old without review annotation.
- Consider test doubles (MockGateway) to eliminate real broker imports in OMS tests.

---

## FINDING 8 — Three Circuit Breakers in Dhan Without Unified Dashboard

**Severity**: 🟡 Medium
**File**: `brokers/dhan/http_client.py`

### 5-Why Chain

1. **Why** does Dhan have three separate circuit breakers? — Read (market data, threshold=10), Write (orders, threshold=3), Admin (account, threshold=5). Prevents read-side storms from blocking order placement.
2. **Why** is this good? — It's the correct separation-of-concerns pattern for trading systems. Read failures shouldn't halt trading.
3. **Why** is this a finding? — The three breakers have independent state but no unified observability. The `/metrics` endpoint exposes generic `circuit_breaker_open` counters without breaker-name labels.
4. **Why** is unified observability missing? — `EventMetrics` uses `(event_type, outcome)` keys. Circuit breaker name isn't part of the key.
5. **Root cause**: Metrics key structure doesn't support multi-instance circuit breaker monitoring.

### Mitigation

- Add breaker-name label to metrics: `(event_type, breaker=read, outcome=open)`.
- Include breaker state in `/metrics` Prometheus output as labeled gauges.
- Upstox adapter should adopt the same three-breaker pattern for consistency.

---

## FINDING 9 — Strategy Module Empty at Broker Layer

**Severity**: 💡 Recommendation
**File**: `brokers/common/strategy/` (contains only `__pycache__/`)

### 5-Why Chain

1. **Why** is `brokers/common/strategy/` empty? — Strategy evaluation lives in `analytics/strategy/` (Protocol-based with registry). No broker-layer strategy code was ever written.
2. **Why** does the empty directory exist? — It was created during initial project scaffolding as a placeholder. Never populated.
3. **Why** keep it? — The `pyproject.toml` `[tool.setuptools.packages.find]` includes `strategy*` in its `include` list. Empty directories with `__pycache__` don't cause import errors.
4. **Why** is this confusing? — `agent.md` lists `brokers/common/strategy/` as a module with status "🟡 Placeholder". The real strategy code is in `analytics/strategy/`.
5. **Root cause**: Scaffolding placeholders not cleaned up after real implementation landed elsewhere.

### Mitigation

- Delete `brokers/common/strategy/` directory.
- Remove `strategy*` from `pyproject.toml` include list (or change to `analytics.strategy*`).
- Update any documentation referencing the broker-layer strategy path.

---

## FINDING 10 — Replay Mode Mutates EventBus Internals

**Severity**: 🟠 High
**File**: `application/oms/context.py:541-562`

### 5-Why Chain

1. **Why** does `_replay_log_into_oms()` directly set `self._event_bus._replay_mode = True`? — Replay must suppress handler dispatch and auto-persistence to prevent double-counting.
2. **Why** use private attribute mutation? — The EventBus class exposes `replay_mode` as a read-only property but no setter. The context reaches into internals via `self._event_bus._replay_mode = True`.
3. **Why** is this fragile? — Any refactoring of EventBus internals (renaming `_replay_mode`, adding validation) breaks the context silently. No type checker catches this.
4. **Why** wasn't a public API added? — The EventBus was designed before the replay requirement. When replay was added (P4), the attribute was bolted on without a proper setter.
5. **Root cause**: Cross-module mutation of internal state instead of using the EventBus's own replay API.

### Mitigation

- Add `EventBus.set_replay_mode(enabled: bool)` public method with validation.
- Replace all `_event_bus._replay_mode = ...` with `self._event_bus.set_replay_mode(...)`.
- Add type annotation to prevent mypy from ignoring the private access.

---

## READINESS SCORES

| Category | Score | Evidence |
|---|---|---|
| Event Architecture | 7/10 | Dual bus (sync+async), DLQ, EventLog — but phantom directory and migration gap |
| Replay Capability | 8/10 | EventLog replay + determinism verifier — but private attribute mutation |
| Strategy Framework | 8/10 | Protocol-based with registry, built-in strategies, pipeline — but empty broker placeholder |
| Scanner Framework | 9/10 | 4 scanners, parallel runner, FeaturePipeline — but DataFrame copy overhead |
| State Machines | 9/10 | Generic StateMachine[T], ORDER_STATUS_TRANSITIONS, lifecycle enums |
| Broker Integration | 9/10 | Full Dhan + Upstox + Paper, capability-based discovery, contract tests |
| Risk Management | 9/10 | 7 sequential checks, LossCircuitBreaker, margin verification, kill switch |
| Testing | 9/10 | 386 tests, chaos/e2e/property/stress/contract, mutation testing config |
| Observability | 9/10 | EventMetrics, AlertingEngine, HttpObservabilityServer, correlation IDs |
| Reliability | 8/10 | Circuit breakers, retry, rate limiting, idempotency — but singleton lifecycle gaps |
| Maintainability | 7/10 | Clean separation — but stale docs, phantom directories, dual migration paths |
| Scalability | 7/10 | Thread-safe everywhere — but DataFrame copies, sync EventBus bottleneck |

**Overall Platform Readiness: 8.3/10**

---

## PRIORITIZED REMEDIATION ROADMAP

### Immediate (1-2 weeks)

| Priority | Finding | Action | Risk Reduction |
|---|---|---|---|
| 🔴 | F10 | Add EventBus.set_replay_mode() public method | Eliminates fragile internal mutation |
| 🟠 | F1 | Delete empty brokers/common/event_bus/ directory | Removes developer confusion |
| 🟠 | F7 | Add review-date annotations to import-linter ignores | Prevents ignore list creep |

### Short-term (2-4 weeks)

| Priority | Finding | Action | Risk Reduction |
|---|---|---|---|
| 🟡 | F2 | Rewrite agent.md to reflect current layout | New contributors follow correct paths |
| 🟡 | F3 | Define async EventBus migration timeline | Clear decommission path |
| 🟡 | F6 | Audit and remove OMS backward-compat shims | Single canonical import path |
| 🟡 | F8 | Add breaker-name labels to circuit breaker metrics | Unified observability dashboard |

### Medium-term (1-2 months)

| Priority | Finding | Action | Risk Reduction |
|---|---|---|---|
| 💡 | F4 | Add ProcessedTradeRepository compaction | Bounded startup time |
| 💡 | F5 | Evaluate Polars for zero-copy feature pipelines | 4x memory reduction |
| 💡 | F9 | Delete empty strategy/execution placeholders | Cleaner project structure |

---

## WHAT'S PRODUCTION-READY

- **Order placement with idempotency** — correlation_id dedup, pending-order set, SQLite persistence
- **Risk enforcement** — 7 sequential checks before every order, thread-safe kill switch, loss circuit breaker
- **Event sourcing and replay** — EventLog with sequence_number, determinism verifier in CI
- **Dual-broker failover** — IntelligentGateway routes between Dhan/Upstox based on health
- **Observability** — /healthz, /readyz, /metrics (Prometheus), AlertingEngine with 6 default rules
- **Chaos testing** — 10 deterministic failure-mode tests covering token expiry, concurrency, lifecycle drain
- **Graceful shutdown** — SIGTERM/SIGINT handlers, order cancellation, event log flush, lifecycle drain
