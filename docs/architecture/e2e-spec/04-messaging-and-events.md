# 04 — Messaging & Events

Reference: Nautilus `docs/concepts/message_bus.md`, architecture.md messaging section.  
TradeXV2: `src/domain/events/types.py`, `bus.py`, infrastructure event_bus (to be collapsed).

---

## 1. Message kinds (Nautilus triad)

| Kind | Direction | Examples |
|---|---|---|
| **Data** | Adapter → DataEngine → subscribers | TICK, QUOTE, DEPTH, BAR_CLOSED, OPTION_CHAIN |
| **Commands** | Strategy/UI → Risk/Execution | place / cancel / modify (point-to-point) |
| **Events** | Engines → everyone | ORDER_*, TRADE_*, RISK_*, POSITION_*, RECONCILIATION_* |

**Immutability rule (Nautilus):** once created, message fields must not be mutated. Derive a new message instead of rewriting.

---

## 2. Topic / type hierarchy (TradeXV2)

TradeXV2 currently uses `EventType` enum strings rather than dotted topics. Target keeps enum for type-safety; optional topic aliases for bus routing:

```
data.tick.{exchange}.{symbol}
data.quote.{exchange}.{symbol}
data.bar.{timeframe}.{exchange}.{symbol}
data.option_chain.{underlying}
events.order.{order_id}
events.trade.{trade_id}
events.risk.*
events.reconciliation.*
commands.execution.place|cancel|modify
```

Handlers may subscribe by `EventType` or by topic pattern; one bus implements both.

---

## 3. Canonical EventType catalog

### Market
`TICK`, `DEPTH`, `QUOTE`, `QUOTE_UPDATED`, `DEPTH_UPDATED`, `INDEX_QUOTE`, `OPTION_CHAIN`, `BAR_CLOSED`, `SUBSCRIPTION_STARTED`, `SUBSCRIPTION_ENDED`

### Orders & trades (spine)
```
ORDER_REQUESTED → ORDER_PLACED → ORDER_SUBMITTED
  → ORDER_UPDATED | ORDER_CANCELLED | ORDER_REJECTED
TRADE → TRADE_FILLED → TRADE_APPLIED
  → POSITION_UPDATED | POSITION_OPENED | POSITION_CLOSED
```

### Risk & safety
`RISK_APPROVED`, `RISK_REJECTED`, `RISK_LIMIT_BREACHED`, `KILL_SWITCH_TOGGLED`, `DAILY_PNL_RESET`, `DRAWDOWN_LIMIT_HIT`, `CIRCUIT_BREAKER_OPENED`, `CIRCUIT_BREAKER_CLOSED`

### Reconciliation
`RECONCILIATION_DRIFT`, `RECONCILIATION_COMPLETED`

### Strategy / scan
`SCAN_STARTED`, `CANDIDATE_GENERATED`, `SCAN_COMPLETED`, `SIGNAL_GENERATED`, `SIGNAL_EXECUTED`, `EXECUTION_PLAN_BUILT`, `STRATEGY_ACTIVATED|PAUSED|DISABLED`

### System
`SERVICE_*`, `SYSTEM_STARTED|SHUTDOWN`, `HEALTH_CHECK_*`, `BROKER_CONNECTED|DISCONNECTED`, `TOKEN_REFRESHED|EXPIRED`, `PORTFOLIO_UPDATED`, `METRICS_UPDATED`

---

## 4. DomainEvent shape

```text
DomainEvent
  type: EventType | str
  payload: mapping (prefer typed wrappers: TradeFilledEvent, TradeAppliedEvent, …)
  symbol: str | None
  correlation_id: str | None
  source: str          # component id
  timestamp: datetime  # FROM CLOCK — never datetime.now()
```

Typed wrappers (`events/typed_events.py`) are preferred at handler boundaries.

---

## 5. Messaging styles (when to use which)

| Style | Use for |
|---|---|
| Pub/Sub EventType | Fan-out: fills, positions, market data, health |
| Point-to-point command | Place/cancel/modify into Risk/Execution (no silent fan-out) |
| Req/Rep | Rare: instrument resolve, margin quote with timeout |

Nautilus Actor publish_data / publish_signal → TradeXV2: publish DomainEvent; avoid ad-hoc dict channels.

---

## 6. Single-bus rule (I10)

**As-built violation:** multiple buses under `domain/events`, `infrastructure/event_bus`, `brokers/runtime`, `interface/ui/services`.

**Target:**
- Port: `domain/events/bus.py` / `EventBusPort`
- One infra core + optional async façade
- DeadLetterQueue mandatory
- Arch test fails if a second concrete bus is constructed in runtime wiring

---

## 7. Expected Behavior Contract — publish

| | |
|---|---|
| **Inputs** | Immutable DomainEvent with Clock timestamp |
| **Outputs** | All current subscribers invoked; failures → DLQ |
| **Timing** | Sync dispatch on kernel thread; order = subscription order (document if changed) |
| **State** | Bus itself is stateless except subscriber registry |
| **Failure modes** | Handler exception must not stop other handlers; never drop without DLQ |
