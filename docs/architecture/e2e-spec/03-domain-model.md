# 03 — Domain Model

Reference: Nautilus `model` crate / `docs/concepts/value_types.md`, `orders/`, `positions.md`.  
TradeXV2 home: `src/domain/` (pure; stdlib only).

---

## 1. Bounded contexts

| Context | Home | Owns |
|---|---|---|
| Market Data | `entities/market.py`, `quotes/`, ports `DataProvider` | QuoteSnapshot, MarketDepth, subscriptions |
| Instruments | `instruments/` | InstrumentId, metadata, tick/lot, resolver |
| Orders / OMS domain | `entities/order.py`, `orders/`, `executions/` | Order, OrderIntent, Execution aggregate |
| Positions / Portfolio | `entities/position.py`, `portfolio/`, `portfolio_projection.py` | Position, project_trade, RiskProfile |
| Risk policy | `risk/`, `ports/risk_manager.py` | notional math, KillSwitch policy object |
| Events | `events/` | EventType, DomainEvent, typed wrappers |
| Reconciliation | `reconciliation.py`, `reconciliation_engine.py` | DriftItem, pure compare |
| Options / Futures | `options/`, `futures/` | chains, greeks, strike selection |
| Analytics / Indicators | `indicators/`, `analytics/`, `candles/` | pure math |
| Session / Universe | `session.py`, `universe.py` | session view over ports |
| Capabilities | `capabilities/`, `capability_manifest/` | broker surface catalogs |

---

## 2. Value objects (Nautilus-aligned)

| Type | Rules | Location |
|---|---|---|
| `Money` | Currency-tagged; same-currency arithmetic only; finite Decimal | `primitives/value_objects.py` |
| `Quantity` | Non-negative (or signed where domain allows); Decimal | same |
| `Price` helpers | Tick alignment via `value_objects/price.py` | `is_tick_aligned` |
| `Clock` | Protocol; **never** call wall clock inside domain modules | injected |

**Fail-fast (Nautilus policy):** NaN / non-finite / empty currency → raise at construction. Corrupt money is worse than no money.

---

## 3. Entities & aggregates

### 3.1 Order
- Fields: `order_id`, `correlation_id`, `symbol`, `exchange`, `side`, `quantity`, `filled_quantity`, `price`, `status`, `reject_reason`, timestamps.
- **FSM:** `ORDER_STATUS_TRANSITIONS` in `entities/order_lifecycle.py`:

```
OPEN → {PARTIALLY_FILLED, FILLED, CANCELLED, PARTIALLY_CANCELLED, REJECTED, EXPIRED}
PARTIALLY_FILLED → {FILLED, CANCELLED, PARTIALLY_CANCELLED, REJECTED}
FILLED | CANCELLED | PARTIALLY_CANCELLED | REJECTED | EXPIRED → ∅ (terminal)
UNKNOWN → {OPEN, REJECTED, CANCELLED}
```

**Contract:** every status change MUST go through `StateMachine[OrderStatus]` (today `Order.with_status` is a plain `replace` — **gap**, see migration).

### 3.2 Trade
- Immutable fill record: `trade_id`, `order_id`, `qty`, `price`, `side`, `timestamp` (Clock-sourced).
- Idempotency key: `trade_id`.

### 3.3 Execution (aggregate)
- Owns fills for one order (`executions/execution.py`).
- Methods: `apply_trade`, `avg_price`, `filled_quantity`, `remaining_quantity`, `is_complete`.
- Emits `TRADE_APPLIED` for downstream position projection.

### 3.4 Position
- Updated only via `project_trade` / `with_fill`.
- **FSM:** `POSITION_STATE_TRANSITIONS` (FLAT → OPEN → REDUCING / REVERSED → CLOSED …).
- Already enforced in `PositionManager` (keep).

### 3.5 Instrument
- Identity: `InstrumentId`.
- Metadata: tick size, lot, multiplier, segment, trading hours.
- Resolution via `InstrumentProvider` / resolver ports.

---

## 4. Domain services (pure)

| Service | Responsibility |
|---|---|
| `project_trade` | Position math from Trade |
| `effective_notional` | Never treat bare qty as rupee notional |
| `ReconciliationEngine.compare_*` | DriftItem list; no I/O |
| Indicator / candle helpers | Research math without broker imports |

---

## 5. Ports (hexagonal boundary)

Critical Protocols (freeze without ADR):

- `DataProvider` / `ExecutionProvider` / `BrokerAdapter` — `ports/protocols.py`, `broker_adapter.py`
- `OrderServicePort` — place / cancel / modify via OMS only
- `RiskManagerPort` — `check_order`, kill-switch
- `ExecutionLedgerPort` — durable intent / outcome / fill
- `EventBusPort` / `EventPublisher`
- `TimeServicePort`
- `MarginProviderPort`, `RiskViewPort`
- `ExchangeAdapter` / `TradingCalendar` (target; ADR-005)

Brokers and interfaces depend on these Protocols — never on `OrderManager` / `RiskManager` concretes.

---

## 6. Expected Behavior Contract — domain mutation

| | |
|---|---|
| **Inputs** | Validated intents / trades / broker-normalized DTOs |
| **Outputs** | New immutable entity versions + domain events |
| **Timing** | Timestamps from Clock argument / TimeServicePort |
| **State** | Only legal FSM transitions |
| **Failure modes** | IllegalTransitionError, DomainValueError — never silent coerce of NaN/status |
