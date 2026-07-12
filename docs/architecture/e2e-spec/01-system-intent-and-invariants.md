# 01 — System Intent & Invariants

## 1. System intent

TradeXV2 is a **real-money, multi-broker Indian (NSE/IST) trading OS** that:

1. Ingests market data (quotes, depth, bars, option chains).
2. Evaluates strategies / scanners under risk constraints.
3. Places, modifies, cancels orders via Dhan / Upstox / Paper plugins.
4. Maintains local order + position state reconciled to broker truth.
5. Supports **backtest**, **sandbox (paper)**, and **live** with **identical** execution semantics (Zero-Parity).
6. Exposes the same capabilities to humans (Web/API/TUI/CLI) and agents (MCP).

Reference: Nautilus “research-to-live parity with no code changes”  
(`/Users/apple/Downloads/nautilus_trader-develop/docs/concepts/overview.md`).

---

## 2. Trust boundaries

```
┌─────────────────────────────────────────────────────────────┐
│  Interface (Web/API/TUI/CLI/MCP)                            │
│  — untrusted input; must go through application use-cases   │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  Runtime (TradeXKernel composition root)                    │
│  — ONLY place that selects concrete BrokerAdapter           │
└───────────────────────────┬─────────────────────────────────┘
                            │ injects ports
┌───────────────────────────▼─────────────────────────────────┐
│  Application engines (Data / Risk / Execution / Portfolio)  │
│  — real-money boundary: Risk + Idempotency + Ledger         │
└───────────────────────────┬─────────────────────────────────┘
                            │ ports only
┌───────────────────────────▼─────────────────────────────────┐
│  Domain (pure) — entities, FSMs, events, value objects      │
└─────────────────────────────────────────────────────────────┘
                            ▲
┌───────────────────────────┴─────────────────────────────────┐
│  Brokers (plugins) — transport + mapping; no risk authority │
└─────────────────────────────────────────────────────────────┘
```

Hard rules (from `docs/architecture/target-layering.md`):
- `domain` imports nothing inward.
- `application` never imports `infrastructure` / `runtime` / `brokers`.
- `runtime` alone imports concrete brokers (by `BrokerId` enum).
- Brokers depend on **ports** (`RiskManagerPort`, `OrderServicePort`), never OMS concretes.

---

## 3. Enforceable invariants

| ID | Invariant | Nautilus analogue | Enforcement |
|---|---|---|---|
| **I1** | Zero-Parity: one ExecutionEngine; env swaps FillSource only | Shared `ExecutionEngine` in kernel | Architecture test + type: no parallel place_order impls |
| **I2** | Deterministic time: all order/trade/event timestamps from injected Clock | `TestClock` / `LiveClock` | Grep-gate: no `datetime.now` in fill/order/event builders |
| **I3** | Domain purity | Rust `model` crate isolation | import-linter |
| **I4** | Single composition root | `NautilusKernel` | import-linter + BrokerId enum |
| **I5** | Risk is a port on the hot path | `RiskEngine` before venue | Every place/cancel/modify goes through RiskEngine |
| **I6** | Reconciliation on hot path | `ExecutionEngine.reconcile_*` | No detached timer as sole healer |
| **I7** | Order + Position FSMs enforced | `fsm.pyx` + order events | `with_status` / transitions raise `IllegalTransitionError` |
| **I8** | Single idempotency authority | Client-side dedupe + cache | One `IdempotencyGuard` for `correlation_id` / `trade_id` |
| **I9** | Fail-closed risk | Fail-fast policy | Provider fault → `RiskResult(allowed=False)` |
| **I10** | Single MessageBus / EventBus | One `MessageBus` | One port + one impl; arch test bans additional buses |

---

## 4. Expected Behavior Contract — system level

| Dimension | Contract |
|---|---|
| **Inputs** | Operator session config; market data streams; strategy signals; broker WS/REST |
| **Outputs** | Durable ledger intents/outcomes/fills; EventBus publications; portfolio views |
| **Timing** | Live: wall clock via SystemClock. Replay: FakeClock advanced by bar/event. Same ordering guarantees relative to Clock |
| **State transitions** | Component FSM + Order FSM + Position FSM + TradingState |
| **Failure modes** | Recoverable (network) → retry/circuit breaker. Unrecoverable (invariant/corrupt) → fail-fast halt. Risk deny → no venue call |

---

## 5. What “done” means for this OS

From `context/project-overview.md`, restated as E2E acceptance:

1. Operator can start a session; runtime selects broker once by `BrokerId`.
2. A signal that passes risk places exactly one broker order per `correlation_id`.
3. A dropped WS fill is healed by the next broker mass-status **inside** the engine (no phantom position for risk).
4. The same strategy module produces byte-identical order streams in replay given the same Clock + catalog data (Zero-Parity).
5. Kill-switch `freeze_all` rejects place/modify/cancel/`exit_all` until cleared.
6. Architecture tests + import-linter + coverage gates pass on every deployable build.
