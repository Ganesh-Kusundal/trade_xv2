# Object Model

**Version:** 1.0 (TRANS-P1-005)  
**Implementation:** `src/domain/`

---

## Aggregates

### Order

**Location:** `domain.entities.Order`, `application.oms._internal.order_lifecycle`

| Attribute | Type | Invariant |
|-----------|------|-----------|
| `order_id` | str | Unique per process |
| `correlation_id` | str | Idempotency key |
| `status` | `OrderStatus` | Legal transitions only |
| `side`, `quantity`, `price` | VOs | Decimal precision |
| `filled_qty` | Decimal | ≤ quantity |

**State machine (summary):**

```
PENDING → SUBMITTED → OPEN → PARTIALLY_FILLED → FILLED
                    ↘ CANCELLED / REJECTED
                    ↘ UNKNOWN (ambiguous broker) → recon required
```

**Rules:**

- `UNKNOWN` blocks automatic retry until reconciliation resolves.
- All transitions emit `ORDER_UPDATED`.

### Execution

**Location:** `domain.executions` (aggregate); wired in Phase 5 ledger.

| Responsibility | Method |
|----------------|--------|
| Own fills for one order | `apply_trade(trade)` |
| Idempotency | Reject duplicate `trade_id` |
| Emit fact | `TRADE_APPLIED` |

### Position

**Location:** `domain.entities.Position`, `application.oms.position_manager`

| Attribute | Source |
|-----------|--------|
| `quantity` | Sum of `TRADE_APPLIED` |
| `avg_price` | Weighted from fills |
| `realized_pnl` | On reducing trades |

**Invariant:** Positions updated only from `TRADE_APPLIED`, never from broker polls directly.

### Subscription

**Location:** `domain.instruments`, streaming layer

| State | Meaning |
|-------|---------|
| `inactive` | Created, not streaming |
| `active` | Receiving ticks |
| `degraded` | Partial data / reconnecting |
| `ended` | Clean shutdown |

**Invariant:** `degraded` must be observable (metrics/event), not silent.

### BrokerSession (facade)

**Location:** `brokers` public API (ADR-014)

| Concern | Owner |
|---------|-------|
| Auth state | Broker plugin |
| Capability flags | `domain.capabilities` |
| Instrument factory | `domain.instruments` |

Not a domain aggregate — session is a **facade** over plugin + runtime bundle.

---

## Value objects

| VO | Module | Notes |
|----|--------|-------|
| `InstrumentId` | `domain.instruments` | Canonical symbol identity |
| `ExchangeSegment` | `domain.types` | NSE, NSE_FNO, MCX, … |
| `OrderRequest` | `domain.orders.requests` | Placement intent |
| `HistoricalBar` | `domain.candles.historical` | Single OHLCV bar (Decimal, UTC, provenance) |
| `HistoricalSeries` | `domain.candles.historical` | Ordered bars + coverage + gaps |
| `MarketTick` | `domain.entities.market` | Live tick SSOT |
| `InstrumentRef` | `domain.candles.historical` | Symbol + exchange on bars |

See [MARKET_DATA_OBJECTS.md](./MARKET_DATA_OBJECTS.md) and ADR-020 for full market-data catalog.

---

## Market data (bars and ticks)

**Location:** `domain.candles.historical`, `domain.entities.market`, `domain.provenance`

### HistoricalBar

| Attribute | Type | Invariant |
|-----------|------|-----------|
| `instrument` | `InstrumentRef` | Required |
| `timeframe` | str | Normalized interval (`1m`, `1D`, …) |
| `event_time` | datetime | UTC-aware; canonical bar open time |
| `open/high/low/close` | Decimal | No NaN; reject at ingress |
| `volume` | int | ≥ 0 |
| `provenance` | `DataProvenance` | Required on every bar |
| `is_partial` | bool | True for incomplete live candle |
| `close_time`, `tick_count` | optional | Live aggregation metadata |

**Factories:** `from_replay`, `from_live_bucket`. Series ingress: `HistoricalSeries.from_broker_df`, `from_datalake_df`.

**Not domain:** API `Candle` (wire), datalake parquet DataFrame (storage), analytics OHLCV DataFrame (working set).

### HistoricalSeries

| Attribute | Role |
|-----------|------|
| `bars` | Ascending by `event_time` |
| `coverage` | Requested date window |
| `gaps` | Missing intervals |
| `merge_manifest` | Multi-broker federation audit |

**Export:** `to_dataframe()` for analytics only. **Forbidden:** returning raw DataFrame as domain history type.

### MarketTick

Cross-reference ADR-016. Single live tick type; streaming normalizes to domain before fan-out.

### Forbidden duplicates

- `HistoricalCandle` (removed; use `HistoricalBar`)
- Parallel `class Bar` / `class Candle` outside `interface.api.schemas.Candle`
- Router-local OHLC construction bypassing `candle_mapper`

---

## Ports (hexagonal)

| Port | Module | Implemented by |
|------|--------|----------------|
| `BrokerAdapter` | `domain.ports` | `brokers.*.wire` |
| `DomainEventBus` | `domain.events` | `infrastructure.event_bus` |
| `SegmentMapper` | `domain.market` | Broker plugins via registry |
| `TimeService` | `domain.ports.time_service` | `infrastructure.time.clock` |
| `TracerPort` | `domain.ports.observability` | Composition root (optional) |

---

## Registry patterns

### SegmentMapperRegistry

```python
# Broker plugin (at import):
register_segment_mapper("dhan", DhanSegmentMapper)

# Domain lookup (after plugin import):
segment_mapper_for("dhan")
```

Fail-closed `LookupError` if plugin not imported.

---

## Projections (read models)

| Projection | Source events | Consumer |
|------------|---------------|----------|
| Order book | ORDER_* | UI, API |
| Positions | TRADE_APPLIED | Risk, portfolio |
| Portfolio PnL | TRADE_APPLIED + marks | Dashboard |

Target (ADR-015): all projections rebuildable from execution ledger.