# 10 — Ports & Expected Behavior Contracts

Freeze these Protocols before implementing the redesign. New methods require an ADR.

---

## 1. OrderServicePort

```python
class OrderServicePort(Protocol):
    def place(self, intent: OrderIntent) -> OrderResult: ...
    def cancel(self, order_id: str) -> OrderResult: ...
    def modify(self, request: ModifyOrderRequest) -> OrderResult: ...
```

| | place | cancel | modify |
|---|---|---|---|
| **Inputs** | OrderIntent + correlation_id | order_id | ModifyOrderRequest |
| **Outputs** | OrderResult + events | OrderResult + events | OrderResult + events |
| **Timing** | Ledger intent before I/O | — | — |
| **Failure** | Risk deny / idempotent replay / venue reject / UNKNOWN | Not found / kill-switch / venue reject | Illegal state / venue reject |

---

## 2. RiskManagerPort / RiskEngine

```python
class RiskManagerPort(Protocol):
    def check_order(self, order) -> RiskResult: ...
    def is_kill_switch_active(self) -> bool: ...
    def get_status(self) -> dict: ...
```

Target extensions (ADR): `trading_state()`, `set_trading_state()`, throttler stats — keep behind port.

**EBC:** see `07-risk-and-safety.md` §5. Fail-closed on dependency fault.

---

## 3. DataProvider

```python
class DataProvider(Protocol):
    def get_quote(self, instrument_id: InstrumentId) -> QuoteSnapshot | None: ...
    def get_history(...) -> HistoricalSeries: ...
    def subscribe(...) -> SubscriptionHandle: ...
```

**EBC:** returns domain types only; never raw broker JSON. Timestamps Clock/venue normalized.

---

## 4. BrokerAdapter / ExecutionProvider

Transport only: submit / cancel / modify / fetch mass status / stream events.  
**Must not** call RiskManager concretes; may receive RiskManagerPort for paper paths that mirror OMS, but live adapters should not re-implement risk.

---

## 5. ExecutionLedgerPort

```python
class ExecutionLedgerPort(Protocol):
    def record_intent(self, intent: OrderIntent) -> None: ...
    def record_outcome(self, outcome: SubmissionOutcome) -> None: ...
    def record_fill(self, fill: LedgerFillRecord) -> None: ...
    def outcome_for(self, intent_id: str) -> SubmissionOutcome | None: ...
```

**EBC:** durable before acknowledging success to UI for live. Crash recovery replays UNKNOWN intents via reconcile.

---

## 6. EventBusPort

```python
class EventBusPort(Protocol):
    def publish(self, event: DomainEvent) -> None: ...
    def subscribe(self, event_type: str, handler) -> str: ...
    def unsubscribe(self, token: str) -> None: ...
```

**EBC:** see `04-messaging-and-events.md` §7.

---

## 7. TimeServicePort

```python
class TimeServicePort(Protocol):
    def now(self) -> datetime: ...
```

**EBC:** UTC-aware; FakeClock deterministic; no hidden wall clock.

---

## 8. Reconciliation apply port (target)

```python
class ReconciliationApplicatorPort(Protocol):
    def apply_mass_status(self, orders, positions, funds) -> list[DriftItem]: ...
```

Implemented by ExecutionEngine; uses pure `ReconciliationEngine` compare.

---

## 9. Contract change process

1. Propose ADR under `docs/architecture/adr/`.  
2. Update this file + affected flow docs.  
3. Add/adjust architecture tests.  
4. Then implement.
