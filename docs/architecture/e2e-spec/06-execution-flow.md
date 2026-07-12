# 06 — Execution Flow (End-to-End)

Reference: Nautilus `docs/concepts/execution.md`, architecture.md “Execution flow: life of an order”, `docs/concepts/live.md` (denial vs rejection).

---

## 1. Component chain (target)

```mermaid
flowchart LR
    orch[TradingOrchestrator / Strategy]
    osvc[OrderServicePort]
    risk[RiskEngine]
    eng[ExecutionEngine]
    fill[FillSource]
    broker[BrokerAdapter]
    cache[TradingCache]
    pos[PositionManager]
    bus[EventBus]

    orch --> osvc --> risk
    risk -->|approved| eng
    risk -->|denied| bus
    eng --> fill
    fill -->|live| broker
    fill -->|paper/sim| eng
    broker -->|WS events| eng
    eng --> cache
    eng --> pos
    eng --> bus
```

**Nautilus rule mirrored:** Strategy never talks to venue clients directly.  
**TradeXV2 rule:** Orchestrator never imports brokers; only `OrderServicePort`.

---

## 2. Life of a place-order (live)

```mermaid
sequenceDiagram
    participant Orch as Orchestrator
    participant OS as OrderService / ExecutionEngine
    participant Idem as IdempotencyGuard
    participant Risk as RiskEngine
    participant Ledger as ExecutionLedger
    participant BA as BrokerAdapter
    participant Venue as Broker venue
    participant Cache as TradingCache
    participant Pos as PositionManager
    participant Bus as EventBus

    Orch->>OS: place(OrderIntent + correlation_id)
    OS->>Idem: check_and_reserve(correlation_id)
    alt duplicate correlation_id
        Idem-->>Orch: prior OrderResult
    end
    OS->>Bus: ORDER_REQUESTED
    OS->>Risk: check_order(order)
    alt denied
        Risk-->>OS: RiskResult(false)
        OS->>Bus: RISK_REJECTED / OrderDenied
        Note over OS,Venue: NO venue call
    else approved
        Risk->>Risk: reserve_pending(notional)
        OS->>Bus: RISK_APPROVED
        OS->>Ledger: record_intent
        OS->>BA: submit(order)
        BA->>Venue: REST/WS place
        Venue-->>BA: ack / reject
        BA-->>OS: Order (SUBMITTED / REJECTED)
        OS->>Ledger: record_outcome
        OS->>Cache: upsert order
        OS->>Bus: ORDER_PLACED / ORDER_SUBMITTED / ORDER_REJECTED
        Venue-->>BA: fill
        BA-->>OS: Trade / TRADE_FILLED
        OS->>OS: record_trade (idempotent trade_id)
        OS->>Ledger: record_fill
        OS->>Cache: update order filled qty / status (FSM)
        OS->>Bus: TRADE_APPLIED
        Bus->>Pos: apply_trade (Position FSM)
        OS->>Risk: release_pending if terminal
    end
```

### Denial vs rejection (Nautilus live.md)

| Outcome | When | Event |
|---|---|---|
| **Denied locally** | Risk / validation / kill-switch before venue | `RISK_REJECTED` / OrderDenied — **no** ORDER_SUBMITTED |
| **Rejected by venue** | Venue proves non-acceptance | `ORDER_REJECTED` |
| **Unresolved** | Ambiguous network failure | Ledger outcome UNKNOWN; reconcile later — do **not** invent REJECTED |

---

## 3. Life of a fill (apply path)

1. Broker WS → adapter maps to `Trade` (timestamp via **Clock**, venue time preferred).
2. `ExecutionEngine.record_trade` — idempotent on `trade_id`.
3. Order status transition via FSM (`OPEN`→`PARTIALLY_FILLED`→`FILLED`).
4. Publish `TRADE_APPLIED`.
5. `PositionManager` projects position; publish `POSITION_*`.
6. Portfolio updates unrealized/realized; RiskEngine `update_daily_pnl`.

---

## 4. Cancel / modify

```
OrderService.cancel/modify
  → RiskEngine (kill-switch freeze_all blocks; REDUCING may allow reduce-only)
  → ExecutionEngine
  → BrokerAdapter.cancel/modify
  → events back → Cache FSM update
```

Local validation failures: warn / OrderModifyRejected-equivalent — do not invent venue rejects.

---

## 5. Replay / paper (same engine)

```mermaid
sequenceDiagram
    participant Replay as ReplayEngine / Paper
    participant OS as ExecutionEngine
    participant Risk as RiskEngine
    participant Sim as SimulatedFillSource
    participant Cache as TradingCache
    participant Pos as PositionManager

    Replay->>OS: place(intent)  %% same API as live
    OS->>Risk: check_order
    Risk-->>OS: approve
    OS->>Sim: submit
    Note over Sim: Fill synchronously at Clock.now() + slippage model
    Sim-->>OS: Order FILLED + Trade
    OS->>Cache: upsert
    OS->>Pos: TRADE_APPLIED path identical to live
```

**Zero-Parity (I1):** `SimulatedFillSource` and live `BrokerAdapter` are the **only** swapped pieces. Risk, idempotency, FSM, position projection, ledger (optional in pure research) share code.

**Forbidden:** separate `SimulatedOMSAdapter.place_order` that bypasses RiskEngine or uses a second order book.

---

## 6. Expected Behavior Contract — place_order

| | |
|---|---|
| **Inputs** | `OrderIntent` with mandatory `correlation_id`, symbol, side, qty, type, product |
| **Outputs** | `OrderResult`; events per spine; ledger rows |
| **Timing** | Intent recorded **before** venue I/O; Clock stamps all local events |
| **State** | correlation_id reserved until terminal or release; pending notional reserved on approve |
| **Failure modes** | Duplicate correlation → return prior result. Risk deny → no I/O. Venue ambiguous → UNKNOWN + reconcile. Illegal status → IllegalTransitionError (fail-fast) |

---

## 7. As-built gaps (execution)

| Gap | Spec impact |
|---|---|
| Live inlined in ExecutionService; replay via SimulatedOMSAdapter | Breaks I1 |
| `datetime.now()` in paper/mapper fills | Breaks I2 |
| Order.with_status bypasses FSM | Breaks I7 |
| Detached reconciliation | Breaks I6 (phantom positions) |
