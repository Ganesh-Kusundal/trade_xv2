# Expected Execution Contract

## Scope

This contract governs the money-moving path currently split between `src/application/oms`, `src/application/execution`, `src/analytics/replay`, `src/analytics/paper`, and `src/brokers/paper`. The existing live spine is `TradingContext → OrderManager → TradeRecorder → PositionManager`; all other modes must become consumers of the same state reducer.

## Contract objects

### MarketEvent

Required fields:

- `event_id`: stable source identity, never regenerated during persistence or replay.
- `instrument_id`: canonical instrument identity; symbol text alone is insufficient.
- `exchange`: canonical exchange/segment.
- `event_time`: exchange/source timestamp with timezone semantics.
- `received_time`: local ingestion timestamp.
- `source`: broker/feed/replay identifier.
- `sequence`: source sequence or explicit `sequence_unavailable`.
- `payload`: typed quote/bar/depth data.
- `quality`: `VALID`, `STALE`, `GAP`, `MALFORMED`, or `QUARANTINED`.

Invalid, stale, or gap-affected events cannot enter an actionable strategy decision without an explicit recovery policy.

### SignalDecision

Required fields:

- `decision_id`: hash of account, strategy version, instrument, market event ID, and decision version.
- `strategy_id` and immutable strategy version.
- `instrument_id`, `market_event_id`, and feature snapshot ID.
- `decision_time`, `side`, `entry policy`, `requested quantity/size policy`.
- `decision_status`: `ACTIONABLE`, `HOLD`, `REJECTED`, or `STALE_INPUT`.
- reason codes and feature provenance.

Signals do not mutate orders, positions, or broker state.

### RiskReservation

Required fields:

- `reservation_id` linked to `decision_id` and `order_intent_id`;
- account/strategy partition;
- reserved cash, gross exposure, net exposure, margin, and quantity;
- reservation version and expiry policy;
- status: `RESERVED`, `RELEASED`, `CONSUMED`, or `REJECTED`.

Reservation creation and order-intent acceptance are one atomic operation from the execution partition's perspective.

### OrderIntent

An immutable command to submit an order:

- `order_intent_id`;
- account, strategy, instrument, side, quantity, order type, product, validity;
- client idempotency key;
- originating decision and reservation IDs;
- creation time and schema version.

An intent is never silently retried. A second submission requires either broker-confirmed idempotency or a reconciled `UNKNOWN` outcome.

### SubmissionOutcome

Exactly one of:

- `ACCEPTED`: broker confirms an order identity;
- `REJECTED`: broker confirms rejection and supplies normalized reason;
- `UNKNOWN`: transport/auth/timeout ambiguity; broker acceptance is unresolved.

`UNKNOWN` is not a failure equivalent to rejection and must not release risk or permit an untracked second order.

### FillEvent

Required fields:

- stable `fill_id` or broker execution ID;
- order intent/order ID;
- cumulative and incremental quantity;
- execution price, fees, taxes, multiplier, currency;
- event/receipt timestamps and broker sequence;
- fill status and source.

The reducer rejects duplicate fill IDs, impossible cumulative decreases, overfills, incompatible prices, and fills for unknown orders unless a controlled late-order reconciliation path accepts them.

### PositionTransition and PortfolioProjection

Every accepted fill produces a deterministic transition. The projection owns:

- quantity and average price;
- realized and unrealized PnL;
- cash, fees, margin, exposure, and LTP provenance;
- position version and last applied fill ID.

Paper, replay, and backtest session objects are read models only. They do not mutate independent position or PnL truth.

### ReconciliationDiscrepancy

Required fields:

- account, broker, partition, and observation times;
- local and broker values for order status, filled quantity, average price, fees, multiplier, cash, positions, and PnL;
- discrepancy class and severity;
- state: `OPEN`, `ACKNOWLEDGED`, `RESOLVED`, or `ESCALATED`;
- resolution evidence and operator identity.

Open material discrepancies block new entries.

## Timing and durability guarantees

1. An actionable decision uses only fresh, valid, point-in-time data.
2. Intent and risk reservation are durable before broker submission.
3. A broker outcome is durable before the caller reports completion.
4. Fill application is idempotent and ordered by stable identity.
5. Projection checkpoints are durable before readiness reports recovered.
6. Replay preserves event identity and schema version.

## Failure semantics

- Missing data: `STALE` or `QUARANTINED`, never zero/empty success.
- Feature failure: `STALE_INPUT`, no order.
- Risk failure: `REJECTED`, reservation not created.
- Broker rejection: `REJECTED`, explicit reason.
- Transport ambiguity: `UNKNOWN`, reconciliation required.
- Persistence failure: no success acknowledgement; readiness degrades/fails.
- Reconciliation drift: new entries blocked until policy resolves it.
- Kill switch: blocks new entries; emergency exits require separately authorized control.
