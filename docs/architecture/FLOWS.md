# FLOWS.md — End-to-End Flow Contracts

> Condensed, test-enforced summary of the numbered flows specified in
> `docs/architecture/e2e-spec/`. `tests/architecture/test_flow_contracts.py` requires this
> file to exist and to contain each `§N — Name` section marker below verbatim. Full detail
> and Nautilus references live in the linked e2e-spec docs — this file is the stable
> section-numbered index those tests check against, not a duplicate of the prose.

---

## §1 — Startup

Source: `docs/architecture/e2e-spec/02-kernel-and-components.md`, `01-system-intent-and-invariants.md`.

1. `runtime/` resolves the active broker **once** via the `tradex.brokers` entry-point group
   (`broker_id` enum — never string branching) and, where registered, the active exchange via
   `tradex.exchanges`.
2. Composition root wires: `EventBus` (single instance), `TradingCache`, `RiskEngine`,
   `ExecutionEngine`, `IdempotencyGuard`, injected `Clock` (`SystemClock` live/sandbox,
   `FakeClock` backtest).
3. Structural boot checks run before accepting traffic: single `ExecutionEngine` wiring, Clock
   injection present, `RiskGate` port bound (no `getattr` reach-through).
4. `Environment` (BACKTEST / SANDBOX / LIVE) is frozen at boot — see §11.

## §6 — Quote

Source: `docs/architecture/e2e-spec/05-data-flow.md` §1, §6.

```
Broker DataClient / DataProvider → DataEngine → TradingCache.set_quote(instrument_id, quote)
  → EventBus.publish(QUOTE|TICK) → Strategy/Orchestrator handler
```

**Invariant:** cache-then-publish — the quote is written to `TradingCache` *before* the event
publishes, so any handler reading `Cache.get_quote()` during the callback sees the same value.

Expected Behavior Contract:

| | |
|---|---|
| Inputs | Venue WS/REST payload mapped to `QuoteSnapshot` |
| Outputs | Cache updated; `QUOTE`/`TICK` published once per accepted update |
| Timing | Timestamp = venue time if present, else `Clock.now()` — never a bare `datetime.now()` in a mapper |
| Failure modes | Parse failure → log + drop (no corrupt Cache); duplicate seq → ignore; disconnect → `BROKER_DISCONNECTED` + reconnect policy |

## §7 — Order

Source: `docs/architecture/e2e-spec/06-execution-flow.md` §1–§4, §6.

```
Orchestrator → OrderServicePort.place(intent, correlation_id) → IdempotencyGuard.check_and_reserve
  → RiskEngine.check_order
      denied  → EventBus(RISK_REJECTED) — no venue call
      approved → ExecutionEngine → BrokerAdapter.submit → Venue
                 Venue ack/reject → Cache upsert (Order FSM) → EventBus(ORDER_PLACED|ORDER_REJECTED)
                 Venue fill → ExecutionEngine.record_trade (idempotent on trade_id)
                   → Cache order status FSM transition → EventBus(TRADE_APPLIED)
                   → PositionManager.apply_trade (Position FSM) → EventBus(POSITION_*)
```

**Denial vs rejection:** a local `RISK_REJECTED` never reaches the venue; a venue
`ORDER_REJECTED` means the broker proved non-acceptance; an ambiguous network failure records
`UNKNOWN` in the ledger and is resolved by reconciliation (§9), never invented as REJECTED.

**Zero-Parity (I1):** replay/paper use the same `ExecutionEngine`/`RiskEngine`/FSM/position-
projection code as live — only the `FillSource` (`SimulatedFillSource`/`PaperFillSource` vs.
`BrokerAdapter`) and `Clock` differ. A second, bypassing order-placement path
(`SimulatedOMSAdapter.place_order`-style) is forbidden.

Expected Behavior Contract:

| | |
|---|---|
| Inputs | `OrderIntent` with mandatory `correlation_id`, symbol, side, qty, type, product |
| Outputs | `OrderResult`; events per spine; ledger rows |
| Timing | Intent recorded before venue I/O; `Clock` stamps all local events |
| Failure modes | Duplicate correlation → prior result returned; risk deny → no I/O; venue ambiguous → `UNKNOWN` + reconcile; illegal status transition → fail-fast |

## §9 — Reconciliation

Source: `docs/architecture/e2e-spec/09-reconciliation-and-cache.md`.

```
BrokerAdapter.mass_status/positions/funds → ExecutionEngine
  → ReconciliationEngine.compare(local Cache, broker snapshot) → list[DriftItem]
  → for each HIGH/MEDIUM drift: Cache upsert (FSM-validated) + RiskEngine capital refresh
  → EventBus(RECONCILIATION_DRIFT) if any, then EventBus(RECONCILIATION_COMPLETED)
```

Triggers: on broker connect/reconnect, on periodic mass-status **applied inside**
`ExecutionEngine` (a timer may fetch, but apply happens in-engine — not a detached service),
and on any `UNKNOWN` submission outcome.

Drift severity: **HIGH** (missing local/broker order, qty mismatch) · **MEDIUM** (price/avg
drift beyond tolerance) · **LOW** (cosmetic/status lag within grace).

`domain/reconciliation_engine.py` stays pure (no I/O, no bus, no broker imports) —
`compare_orders`/`compare_positions`/`compare_funds` only. The application layer applies
results.

Expected Behavior Contract:

| | |
|---|---|
| Inputs | Broker-normalized Order/Position/funds lists + Cache snapshot |
| Outputs | Cache healed; `DriftItem`s published; risk capital aligned |
| Timing | Completes before accepting new risk after reconnect (or TradingState DEGRADED until done) |
| Failure modes | Compare exception → fail-fast/HALTED; partial apply → DEGRADED + alarm; HIGH drift is never left silent |

## §11 — Mode

Source: `docs/architecture/e2e-spec/08-time-parity-and-environments.md`.

| Environment | Data source | FillSource | Clock |
|---|---|---|---|
| **BACKTEST** | Catalog / Parquet / DuckDB | `SimulatedFillSource` | `FakeClock`, advanced by the replay engine |
| **SANDBOX** | Live `DataProvider` | `PaperFillSource` | `SystemClock` (or `FakeClock` for drills) |
| **LIVE** | Live `DataProvider` | `BrokerAdapter` (Dhan/Upstox) | `SystemClock` |

**Invariant I1:** Strategy, RiskEngine, ExecutionEngine (minus FillSource), position
projection, and event types are identical across all three modes — only FillSource, Clock,
and DataSource change at composition time. `Environment` is frozen at boot (§1) and cannot be
changed mid-process.

**Parity gate:** `SKIP_PARITY_GATE` is **never honored** when `Environment.LIVE` — see
`docs/architecture/e2e-spec/08-time-parity-and-environments.md` §3 and the C3 acceptance test
(`tests/unit/.../test_live_parity_gate*`, landed via commit `7bb0a4ec`).

## §12 — Historical Multi-Asset

Source: `docs/architecture/adr/0023-contract-centric-historical-data.md`.

```
API /historical/{equities|options|futures}
  → ContractResolver (InstrumentId identity)
  → BrokerRouter (lane: asset, exchange, contract_state, timeframe, lookback, entitlement)
  → QuotaScheduler → DhanAdapter | UpstoxAdapter
  → Normalizer → Validator → Merger → ProvenanceLedger
  → ContractLake (contracts/{options|futures}/candles/…) | derived rolling DuckDB views
```

**Invariant:** Rolling ATM±N is never canonical storage; exact `InstrumentId` is. Dhan
rolling expired options is NFO index only; Upstox exact expired contracts require Plus
entitlement. Fail-closed unless `allow_partial=true`; watermarks do not advance on degraded
fetch.

Expected Behavior Contract:

| | |
|---|---|
| Inputs | Separate equity / option / future requests with `exchange`, `underlying`, `expiry`, `timeframe`, `contract_state` |
| Outputs | Sorted unique bars + coverage, gaps, broker provenance, route decision, contract metadata |
| Timing | Chunk sizes and concurrency from authoritative `RateLimitProfile` only |
| Failure modes | Invalid selector (422), entitlement absent (403), capability mismatch (422), all sources unavailable (503); empty broker response is not success |

---

## Broker API scheduling & cache ownership

**Rate-limit call path (as-built):**

1. Application `QuotaScheduler` (`application/scheduling/quota_scheduler.py`) — global priority
   classes with max-wait deadlines for cross-broker coordination.
2. Per-broker HTTP clients acquire `MultiBucketRateLimiter` tokens from
   `infrastructure/resilience/rate_limiter.py` using `RateLimitProfile` entries in
   `BrokerCapabilities`.

Both layers may apply; callers should not bypass either at the transport boundary.

**Cache ownership:**

| Cache | Owner |
|---|---|
| Instrument master (file + resolver) | Broker plugin + `domain/ports/data_catalog.py` |
| Token persistence | Per-broker auth modules |
| Idempotency (orders) | `brokers/common/idempotency.py` |
| Historical bars (canonical) | Datalake / `HistoricalDataCoordinator` — not broker-local |
| Quote snapshots | Instrument refresh path — no shared broker quote cache |

---

## As-built gap tracking

See `docs/architecture/backlog.md` (2026-07-13 re-verification) for current status of the
gaps each flow's e2e-spec doc lists (`05-data-flow.md` §7, `06-execution-flow.md` §7,
`09-reconciliation-and-cache.md` §6). Do not duplicate gap status here — it drifts. Link to
the source of truth instead.
