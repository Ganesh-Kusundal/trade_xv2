# 04 — Component Contracts

**Status:** Canonical  
**Runtime:** Threading rules in `02a-runtime-execution-model.md`  
**Rule:** Protocols only — no implementations in this document.

Contracts define seams. Bounded contexts (`05-bounded-contexts.md`) implement them.

---

## Contract Hierarchy

```text
ExecutionTarget          ← primary seam (capability)
├── ReplayTarget
├── BacktestTarget
├── PaperTarget
└── LiveTarget ──uses──▶ BrokerSession

OMS ──depends──▶ ExecutionTarget, RiskManager, EventBus, Clock, IdempotencyGuard
RiskManager ──depends──▶ PortfolioService, InstrumentLookup
Strategy ──depends──▶ Indicator, EventBus, PortfolioService (read)
MarketDataProvider ──depends──▶ BrokerSession (optional), EventBus
```

---

## ExecutionTarget

**Owner:** Runtime wires one implementation per session.  
**Purpose:** Fulfill Orders — submit, cancel, modify; emit Fills.

### API (conceptual)

| Method | Input | Output | Errors |
|---|---|---|---|
| `submit(order: Order) -> SubmitResult` | validated Order | ack/reject + broker refs | `TargetUnavailable`, `RejectReason` |
| `cancel(order_id) -> CancelResult` | platform order_id | ack/reject | `OrderNotFound`, `CancelRejected` |
| `modify(order_id, changes) -> ModifyResult` | partial update | ack/reject | same as cancel |
| `capabilities() -> TargetCapabilities` | — | supported order types, TIF | — |

### Threading

- Called from **main asyncio loop** only (OMS single-writer).
- Implementations may offload blocking I/O; must return to loop before mutating shared state.

### Lifecycle

`init(config) → ready → submit/cancel/modify → shutdown()`

### Error contract

- Reject ≠ exception. Exception = infrastructure fault → OMS marks order REJECTED or retries per policy.
- Live: never swallow broker error without event + log.

### Implementations

| Impl | Venue | Fill source |
|---|---|---|
| `ReplayTarget` | In-process | Historical book / deterministic model |
| `BacktestTarget` | Batch | Same fill model as Replay |
| `PaperTarget` | In-process | Live quotes + slippage model |
| `LiveTarget` | Broker API | Broker venue |

**P1:** All four MUST produce fills that OMS processes identically.

---

## BrokerSession

**Owner:** Broker plugin.  
**Purpose:** Authenticated connection to broker API (market data + order wire when Live).

| Method | Input | Output | Errors |
|---|---|---|---|
| `connect(credentials) -> SessionInfo` | profile creds | session metadata | `AuthFailed` |
| `disconnect() -> None` | — | — | — |
| `is_connected() -> bool` | — | — | — |
| `place_order_wire(payload) -> WireAck` | broker JSON | broker order id | broker errors |
| `subscribe(symbols) -> None` | instrument list | — | `SubscriptionFailed` |

### Threading

- WS callbacks → enqueue to asyncio loop; no direct OMS calls.

### Lifecycle

`DISCONNECTED → CONNECTED → DISCONNECTED`

---

## MarketDataProvider

**Owner:** Market Data context.  
**Purpose:** Normalize ticks/bars; publish domain events.

| Method | Input | Output | Errors |
|---|---|---|---|
| `subscribe(instruments, timeframe)` | list | subscription handle | `InvalidInstrument` |
| `unsubscribe(handle)` | handle | — | — |
| `get_history(instrument, range, tf) -> BarSeries` | query | bars | `DataNotFound` |
| `latest_bar(instrument) -> Bar | None` | — | — | — |

### Events published

`TICK_RECEIVED`, `BAR_CLOSED`, `DATA_STALE`

---

## EventBus

**Owner:** Infrastructure (single impl).  
**Purpose:** Pub/sub domain events.

| Method | Input | Output | Errors |
|---|---|---|---|
| `publish(event: DomainEvent)` | event | — | DLQ on handler failure |
| `subscribe(event_type, handler)` | type, callable | subscription id | — |
| `unsubscribe(sub_id)` | id | — | — |

### Threading

- Handlers run on publisher's task (main loop) unless documented executor offload.
- Handler exceptions → DLQ; bus continues (P11 recoverable).

---

## Strategy

**Owner:** Strategy context / analytics.  
**Purpose:** Evaluate on bar/tick; emit Signals.

| Method | Input | Output | Errors |
|---|---|---|---|
| `on_bar(bar, ctx: StrategyContext) -> None` | bar, read-only ctx | emits via bus | strategy-local |
| `on_tick(tick, ctx) -> None` | tick | emits via bus | — |
| `id() -> StrategyId` | — | — | — |

### StrategyContext (read-only port)

- positions, indicators, clock, instrument metadata
- **Must NOT** expose OMS place directly

---

## Indicator

**Owner:** Analytics / feature pipeline.  
**Purpose:** Pure computation of series.

| Method | Input | Output | Errors |
|---|---|---|---|
| `compute(inputs) -> Series` | bars/ticks | values aligned to index | `InsufficientData` |
| `warmup_period() -> int` | — | bars required | — |

---

## RiskManager

**Owner:** Risk context.  
**Purpose:** Pre-trade gate; authoritative deny.

| Method | Input | Output | Errors |
|---|---|---|---|
| `evaluate(signal: Signal) -> RiskResult` | signal + portfolio | Allow(draft Order) / Deny(reason) | **Deny on any fault** |
| `check_order(order: Order) -> RiskResult` | pending order | allow/deny | fail-closed |
| `trading_state() -> TradingState` | — | ACTIVE/REDUCING/HALTED | — |
| `activate_kill_switch() -> None` | — | HALTED | — |

### Error contract

- Provider exception → `Deny(reason=PROVIDER_FAULT)` — never Allow (P4, QA-resiliency).

---

## OMS (OrderManagerPort)

**Owner:** OMS context.  
**Purpose:** Order lifecycle authority.

| Method | Input | Output | Errors |
|---|---|---|---|
| `place_order(intent) -> Order` | order draft + correlation_id | Order in FSM | `DuplicateCorrelation`, `RiskDenied`, `IllegalTransition` |
| `cancel_order(order_id) -> Order` | id | updated Order | `OrderNotFound` |
| `apply_fill(fill) -> Order` | fill from target | updated Order | FSM violations |
| `get_order(correlation_id) -> Order | None` | — | — | — |
| `request_reconciliation()` | — | — | — |

### Idempotency

- Same `correlation_id` → return existing Order; no second submit (P7).

### Events published

All Order aggregate events + `RECONCILE_*`

---

## PortfolioService

**Owner:** Portfolio context.  
**Purpose:** Positions and PnL read/write from fills.

| Method | Input | Output | Errors |
|---|---|---|---|
| `apply_fill(fill) -> Position` | fill | updated position | — |
| `get_position(instrument_id) -> Position` | — | — | — |
| `snapshot() -> Portfolio` | — | full snapshot | — |
| `daily_pnl() -> Money` | — | session realized | — |

---

## HistoricalProvider

**Owner:** Datalake / market data.  
**Purpose:** Batch history for backtest/replay catalog.

| Method | Input | Output | Errors |
|---|---|---|---|
| `load_catalog(spec) -> Catalog` | symbols, range, tf | iterable bars | `QualityCheckFailed` |
| `validate(spec) -> QualityReport` | — | pass/fail + gaps | — |

---

## Clock (port)

| Method | Purpose |
|---|---|
| `now() -> Timestamp` | Injected time (P8) |
| `advance(delta)` | FakeClock only |

---

## IdempotencyGuard (port)

| Method | Purpose |
|---|---|
| `claim(key) -> bool` | True if first claim |
| `release(key)` | On explicit rollback only |

---

## Expected Behavior Contract Summary

| Contract | Timing | Failure |
|---|---|---|
| ExecutionTarget | submit p99 see QA-latency-3/4 | reject or exception → event |
| RiskManager | p99 ≤ 50ms | always deny on fault |
| OMS | synchronous FSM | illegal transition raises |
| EventBus | FIFO per instrument publisher | DLQ, continue |
| MarketDataProvider | stale detection < 5s | DATA_STALE event |

---

## Versioning

Breaking contract changes require:

1. ADR
2. Gap analysis update
3. Parity test update
4. Major version bump on affected port Protocol
