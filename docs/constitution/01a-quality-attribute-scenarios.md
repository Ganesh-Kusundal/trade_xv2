# 01a — Quality Attribute Scenarios

**Status:** Canonical  
**Principles:** See `01-architecture-constitution.md` §5 (intent)  
**Rule:** Every Phase H acceptance review cites at least one scenario ID below.

Scenario ID format: `QA-<attribute>-<n>`

---

## Latency

### QA-latency-1 — Indicator batch on universe

**Stimulus:** Receive 500 symbols × 1m bar close simultaneously at session open.  
**Response:** Feature pipeline + indicator warm completes for all symbols.  
**Acceptance:** p99 completion ≤ 30s on reference hardware (8-core, 16GB RAM, local DuckDB). p50 ≤ 10s.

### QA-latency-2 — Signal to risk decision

**Stimulus:** Strategy emits Signal for single instrument.  
**Response:** Risk gate evaluates and returns allow/deny.  
**Acceptance:** p99 ≤ 50ms (in-process, no network). Deny path same latency as allow.

### QA-latency-3 — Order place round-trip (Paper)

**Stimulus:** Approved Order submitted via OMS to Paper execution target.  
**Response:** Order reaches terminal state (FILLED or REJECTED) and Fill recorded.  
**Acceptance:** p99 ≤ 200ms in-process (no broker network).

### QA-latency-4 — Order place round-trip (Live)

**Stimulus:** Approved Order submitted to Live broker (Dhan sandbox).  
**Response:** Broker ack + fill or reject received and reconciled.  
**Acceptance:** p99 ≤ 2s including broker RTT (network-dependent; measured, not guessed).

---

## Scalability

### QA-scalability-1 — Historical backtest depth

**Stimulus:** Backtest 1 strategy × 200 symbols × 2 years daily bars.  
**Response:** Completes without OOM; equity curve produced.  
**Acceptance:** Peak RSS ≤ 4GB; completes ≤ 10 min on reference hardware.

### QA-scalability-2 — Datalake query fan-out

**Stimulus:** 50 concurrent read queries against DuckDB read pool.  
**Response:** All queries return without deadlock.  
**Acceptance:** p99 query latency ≤ 5s per query; zero connection leaks.

### QA-scalability-3 — Event bus throughput

**Stimulus:** 10,000 domain events published in 60s (market data replay).  
**Response:** All subscribers process without unbounded queue growth.  
**Acceptance:** Max queue depth ≤ 1,000; no subscriber loss; DLQ count = 0 for valid events.

---

## Extensibility

### QA-extensibility-1 — New broker plugin

**Stimulus:** Add new broker plugin implementing `BrokerAdapter` + register entry-point.  
**Response:** Composition root selects by `BrokerId`; market data flows without core edit.  
**Acceptance:** Zero changes to `application/oms/` or `domain/`; one integration test green.

### QA-extensibility-2 — New execution target

**Stimulus:** Add new `ExecutionTarget` impl (e.g. custom simulator).  
**Response:** Same strategy code runs unchanged; OMS + Risk unchanged.  
**Acceptance:** Parity test: same Signal stream ⇒ same Order intents (modulo target-specific fills).

### QA-extensibility-3 — New exchange calendar

**Stimulus:** Register `tradex.exchanges` plugin for new exchange.  
**Response:** Datalake quality checks and session hours use plugin calendar.  
**Acceptance:** Zero hardcoded exchange strings in `datalake/core/`.

---

## Observability

### QA-observability-1 — Order lifecycle trace

**Stimulus:** Place → partial fill → complete fill → position update.  
**Response:** Structured log + EventBus events for each transition.  
**Acceptance:** Given `correlation_id`, operator can reconstruct full timeline from events alone.

### QA-observability-2 — Risk deny audit

**Stimulus:** Risk denies Signal (daily loss exceeded).  
**Response:** Deny event with reason code published; no Order created.  
**Acceptance:** 100% of denies have non-empty `reason_code` in event payload.

### QA-observability-3 — Health endpoint

**Stimulus:** GET `/health` during active session.  
**Response:** JSON with broker connectivity, bus status, OMS state summary.  
**Acceptance:** Returns 200 when Ready; 503 when kernel not booted or broker auth failed.

---

## Resiliency

### QA-resiliency-1 — Broker transient fault

**Stimulus:** Broker HTTP 503 on place_order; succeeds on retry.  
**Response:** Circuit breaker backs off; order eventually ack'd or explicitly rejected.  
**Acceptance:** Zero duplicate venue submissions for same `correlation_id`.

### QA-resiliency-2 — WebSocket disconnect (Live)

**Stimulus:** Broker WS drops mid-session.  
**Response:** Reconnect + reconcile before next place.  
**Acceptance:** No order placed while reconcile status = STALE; heal completes ≤ 30s.

### QA-resiliency-3 — Idempotency under retry

**Stimulus:** Client retries place_order with same `correlation_id` 3 times.  
**Response:** Single venue submission; subsequent calls return existing Order.  
**Acceptance:** Broker submit count = 1; OMS order count = 1.

---

## Recoverability

### QA-recoverability-1 — Process restart

**Stimulus:** Kill process mid-session with open orders (Paper/Live).  
**Response:** Restart reloads durable order state; reconcile runs.  
**Acceptance:** No phantom open orders after reconcile; no lost fills.

### QA-recoverability-2 — Reconcile heals drift

**Stimulus:** Inject local-only open Position not on broker.  
**Response:** Mass-status reconcile flattens phantom before next risk check.  
**Acceptance:** Position flat within one reconcile cycle (≤ 5s hot path).

### QA-recoverability-3 — Daily PnL reset

**Stimulus:** Session crosses calendar day boundary.  
**Response:** Daily PnL counters reset; risk limits re-evaluated on fresh baseline.  
**Acceptance:** `check_order` after reset uses zero daily loss, not stale cumulative.

---

## Determinism

### QA-determinism-1 — Replay reproducibility

**Stimulus:** Run Replay twice with same catalog + FakeClock seed.  
**Response:** Identical event stream (order, fill, position events).  
**Acceptance:** Byte-identical serialized event log OR structural diff = empty.

### QA-determinism-2 — Backtest reproducibility

**Stimulus:** Run Backtest twice on same data + strategy params.  
**Response:** Identical equity curve and trade journal.  
**Acceptance:** Sharpe, trade count, final equity match to 1e-9 relative tolerance.

### QA-determinism-3 — Clock purity

**Stimulus:** CI grep + architecture test scan `src/`.  
**Response:** No `datetime.now()` in fill/order/event builders.  
**Acceptance:** Zero violations in forbidden paths (see `01` P8).

---

## Testability

### QA-testability-1 — Architecture tests green

**Stimulus:** `venv/bin/pytest tests/architecture/`.  
**Response:** All architecture + import-linter contract tests pass.  
**Acceptance:** 100% pass; no skipped P0 contracts.

### QA-testability-2 — Coverage gates

**Stimulus:** `venv/bin/pytest --cov=src`.  
**Response:** Coverage thresholds met.  
**Acceptance:** ≥ 80 overall, ≥ 85 brokers, ≥ 90 OMS.

### QA-testability-3 — Parity gate

**Stimulus:** Live session boot (when enabled).  
**Response:** Parity gate runs before trading allowed.  
**Acceptance:** `SKIP_PARITY_GATE` ignored when `Environment.LIVE`; gate must pass or boot fails.

---

## Reference Hardware (for latency/scalability scenarios)

- CPU: 8 cores (Apple M-series or equivalent x86)
- RAM: 16 GB
- Storage: local SSD
- Network: Live scenarios use broker sandbox, not production

Re-baseline annually or when hardware target changes (ADR required).
