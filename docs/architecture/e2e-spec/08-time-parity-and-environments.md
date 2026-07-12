# 08 — Time, Parity & Environments

Reference: Nautilus overview (same semantics + time model), architecture environment contexts, TestClock/LiveClock in `common/component.pyx`, kernel clock registration.

---

## 1. Environments

| Environment | Data source | FillSource | Clock |
|---|---|---|---|
| **BACKTEST** | Catalog / Parquet / DuckDB | SimulatedFillSource | FakeClock advanced by engine |
| **SANDBOX** | Live DataProvider | PaperFillSource | SystemClock (or FakeClock for drills) |
| **LIVE** | Live DataProvider | BrokerAdapter (Dhan/Upstox) | SystemClock |

**Invariant I1:** Strategy, RiskEngine, ExecutionEngine (minus FillSource), Position projection, Event types — **identical** across environments.

---

## 2. Clock contract (I2)

```
TimeServicePort.now() → datetime (UTC-aware)
```

| Allowed | Forbidden |
|---|---|
| Injected Clock into Order/Trade/Event builders | `datetime.now()` / `time.time()` in fill/order/event paths |
| Venue timestamp when present (normalized) | Mixing naive local IST stamps into domain without conversion |
| FakeClock.advance(delta) in replay | Relying on wall clock for bar ordering in backtest |

**As-built violations (must close):**  
`paper_orders.py`, `derivatives_mapper.py`, `order_command_adapter.py`, `dhan/websocket/_helpers.py` call `datetime.now(timezone.utc)`.

---

## 3. Zero-Parity definition (testable)

Given:
- fixed catalog dataset D  
- fixed strategy S  
- FakeClock sequence T  

Then BACKTEST run produces order intent stream O and fill stream F such that:

1. Re-running BACKTEST twice → identical O, F (byte-stable timestamps from FakeClock).  
2. LIVE path with SimulatedFillSource stubbed to same prices/qty → identical risk decisions and position projections for the same intents.  
3. `pure_sim` research mode (if retained) is a **distinct type** that cannot be promoted to LIVE config without explicit conversion.

Parity gate:
- Live Environment: **must not** honor `SKIP_PARITY_GATE`.  
- Boot runs structural checks (single ExecutionEngine wiring, Clock injection) + regression tests.  
- Pytest may skip slow suites; live node must not.

---

## 4. Replay engine responsibilities

1. Load bars/ticks for symbol/range.  
2. Advance FakeClock to event time **before** publishing BAR/TICK.  
3. Invoke same strategy → OrderService path as live.  
4. SimulatedFillSource fills at model price using Clock.now().  
5. Persist optional session recording for audit.

---

## 5. Expected Behavior Contract — environments

| | |
|---|---|
| **Inputs** | Environment enum + adapters |
| **Outputs** | Kernel whose strategy code path is env-agnostic |
| **Timing** | All domain times from Clock |
| **State** | Env frozen at boot |
| **Failure modes** | Attempt to use BrokerAdapter FillSource with FakeClock in LIVE without operator flag → config error. Wall-clock in fill builder → arch test fail |
