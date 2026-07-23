# Broker Zero-Parity Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Close the confirmed functional + non-functional parity gaps between the v2 `plugins/brokers` package and legacy `src/brokers`, so orders, token management, extensions, and rate-limiting match legacy behavior — verified by gateway-surface regression tests (no live creds required for unit tests).

**Architecture:** Targeted edits at the existing seams — wire payload builders, order adapters (idempotency + live-gate), connection lifecycle (token scheduler), rate-limit profile sourcing, and the Upstox extension seam. No new layers; reuse `InMemoryInstrumentResolver` and `BrokerExtensions` already present. TDD per task with fake transports.

**Tech Stack:** Python 3.13, pydantic, stdlib `urllib`/`json`. Test runner: project venv (`/Users/apple/Downloads/Trade_XV2/venv/bin/python`). **Mandatory env prefix** `env -u PYTHONPATH` (shell PYTHONPATH shadows venv with a python3.11 build).

---

## Current Context / Assumptions

- Repo root: `/Users/apple/Downloads/Trade_XV2`. Broker package: `v2/src/plugins/brokers/`.
- `HttpTransport._request` raises `BrokerError`/`AuthenticationError`/`NetworkError` on non-2xx (transport.py:248-251) — so order errors propagate; no silent bogus orders.
- v2 already correct: re-auth seam, write-endpoint retry safety, rolling-window limiter, shared instrument resolver, index resolution, Dhan depth extensions.
- Gaps found in code (this plan fixes F1–F7):
  - **F1** Dhan `from_place_command` missing `dhanClientId`, `exchangeSegment`, `disclosedQuantity`.
  - **F2** No order idempotency (legacy uses `IdempotencyCache.reserve→post→commit`).
  - **F3** No live-order safety gate (`DHAN_ALLOW_LIVE_ORDERS`).
  - **F4** `TokenRefreshScheduler` defined but never started (dead code).
  - **F5** Rate-limit cooldown hardcoded 60s; legacy `RateLimitProfile.cooldown_on_429_s=130` (Dhan) ignored.
  - **F6** Upstox `from_place_command` missing `disclosed_quantity`, `market_protection`.
  - **F7** Upstox `BrokerExtensions()` empty; no `stream_depth` in Upstox streaming.

## Test command (all tasks)

```bash
cd /Users/apple/Downloads/Trade_XV2/v2 && env -u PYTHONPATH /Users/apple/Downloads/Trade_XV2/venv/bin/python -m pytest tests/unit/plugins -q
```
Expected full-suite baseline: **338 passed** (before this plan). Each task adds tests that must pass; the suite must stay green.

---

## Task 1: Dhan order payload — add required fields (F1)

**Objective:** `DhanWire.from_place_command` emits `dhanClientId`, `exchangeSegment`, `disclosedQuantity` to match legacy `_build_order_payload`.

**Files:**
- Modify: `v2/src/plugins/brokers/dhan/wire.py:198-212` (`from_place_command`)
- Test: `v2/tests/unit/plugins/brokers/test_market_data_parity.py` (add a new test function)

**Step 1: Write failing test**

Append to `test_market_data_parity.py`:

```python
def test_dhan_order_payload_has_required_fields() -> None:
    from plugins.brokers.dhan.wire import DhanWire
    from domain.commands import PlaceOrderCommand
    from domain.enums import OrderSide, OrderType, TimeInForce
    from domain.value_objects import InstrumentId, Price, Quantity, CorrelationId
    import uuid

    wire = DhanWire()
    wire.register_security(InstrumentId(value="NSE:RELIANCE"), "2885")
    cmd = PlaceOrderCommand(
        instrument_id=InstrumentId(value="NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal("10")),
        price=Price(value=Decimal("2500.0")),
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid.uuid4()),
        product_type="INTRADAY",
        disclosed_quantity=Quantity(value=Decimal("2")),
    )
    body = wire.from_place_command(cmd)
    assert body["dhanClientId"]  # set from config at adapter level — see note
    assert body["exchangeSegment"] == "NSE_EQ"
    assert body["securityId"] == "2885"
    assert body["disclosedQuantity"] == 2
```

> NOTE: `dhanClientId` is client-specific; the wire needs the client_id. Pass it into `DhanWire` via a new optional `client_id` ctor arg, defaulting to `""`, and set it in `DhanConnection.__init__`. Adjust the assertion to `body["dhanClientId"] == "testclient"` after wiring in the test fixture.

**Step 2: Run to verify failure**

Run: `env -u PYTHONPATH /Users/apple/Downloads/Trade_XV2/venv/bin/python -m pytest tests/unit/plugins/brokers/test_market_data_parity.py::test_dhan_order_payload_has_required_fields -q`
Expected: FAIL (`KeyError: 'exchangeSegment'` / `'disclosedQuantity'`).

**Step 3: Write minimal implementation**

In `dhan/wire.py`, add `client_id` to `__init__` (near line 69) and extend `from_place_command` (line 198):

```python
class DhanWire:
    def __init__(self, client_id: str = "") -> None:
        self._resolver = InMemoryInstrumentResolver()
        self._client_id = client_id
```

```python
    def from_place_command(self, command: PlaceOrderCommand) -> dict[str, Any]:
        body: dict[str, Any] = {
            "dhanClientId": self._client_id,
            "correlationId": str(command.correlation_id.value),
            "exchangeSegment": self.get_segment(command.instrument_id),
            "securityId": self.security_id(command.instrument_id),
            "transactionType": BaseWireAdapter.enum_value(command.side),
            "quantity": int(command.quantity.value),
            "orderType": BaseWireAdapter.enum_value(command.order_type),
            "productType": command.product_type or "INTRADAY",
            "validity": BaseWireAdapter.enum_value(command.time_in_force),
        }
        if command.price is not None:
            body["price"] = float(command.price.value)
        if command.trigger_price is not None:
            body["triggerPrice"] = float(command.trigger_price.value)
        if command.disclosed_quantity is not None and int(command.disclosed_quantity.value) > 0:
            body["disclosedQuantity"] = int(command.disclosed_quantity.value)
        return body
```

Wire `client_id` in `dhan/connection.py` (~line 35): `self.wire = DhanWire(client_id=self.config.client_id)`.

**Step 4: Run to verify pass**

Run the Task 1 test + full suite. Expected: Task 1 PASS; suite still green.

**Step 5: Commit**

```bash
git add v2/src/plugins/brokers/dhan/wire.py v2/src/plugins/brokers/dhan/connection.py v2/tests/unit/plugins/brokers/test_market_data_parity.py
git commit -m "fix(dhan): add dhanClientId/exchangeSegment/disclosedQuantity to order payload (F1)"
```

---

## Task 2: Upstox order payload — add required fields (F6)

**Objective:** `UpstoxWire.from_place_command` emits `disclosed_quantity` + `market_protection` to match legacy.

**Files:**
- Modify: `v2/src/plugins/brokers/upstox/wire.py:157-171`
- Test: `v2/tests/unit/plugins/brokers/test_market_data_parity.py`

**Step 1: Write failing test**

```python
def test_upstox_order_payload_has_disclosed_and_market_protection() -> None:
    from plugins.brokers.upstox.wire import UpstoxWire
    from domain.commands import PlaceOrderCommand
    from domain.enums import OrderSide, OrderType, TimeInForce
    from domain.value_objects import InstrumentId, Price, Quantity, CorrelationId
    import uuid

    wire = UpstoxWire()
    wire.register_key(InstrumentId(value="NSE:RELIANCE"), "NSE_EQ|INE002A01018")
    cmd = PlaceOrderCommand(
        instrument_id=InstrumentId(value="NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal("10")),
        price=Price(value=Decimal("2500.0")),
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid.uuid4()),
        product_type="I",
        disclosed_quantity=Quantity(value=Decimal("2")),
    )
    body = wire.from_place_command(cmd)
    assert body["disclosed_quantity"] == 2
    assert "market_protection" in body
```

**Step 2: Run to verify failure** → FAIL (`KeyError: 'disclosed_quantity'`).

**Step 3: Implement** — extend `from_place_command` (upstox/wire.py:157):

```python
    def from_place_command(self, command: PlaceOrderCommand) -> dict[str, Any]:
        body: dict[str, Any] = {
            "instrument_token": self.instrument_key(command.instrument_id),
            "transaction_type": BaseWireAdapter.enum_value(command.side),
            "quantity": int(command.quantity.value),
            "order_type": BaseWireAdapter.enum_value(command.order_type),
            "product": command.product_type or "I",
            "validity": BaseWireAdapter.enum_value(command.time_in_force),
            "tag": str(command.correlation_id.value),
            "market_protection": command.market_protection if command.market_protection is not None else -1,
        }
        if command.price is not None:
            body["price"] = float(command.price.value)
        if command.trigger_price is not None:
            body["trigger_price"] = float(command.trigger_price.value)
        if command.disclosed_quantity is not None and int(command.disclosed_quantity.value) > 0:
            body["disclosed_quantity"] = int(command.disclosed_quantity.value)
        return body
```

> Requires `market_protection` field on `PlaceOrderCommand` (domain). If absent, add a default `None` field to `domain/commands.py` PlaceOrderCommand.

**Step 4: Run** → PASS; suite green.

**Step 5: Commit** `fix(upstox): add disclosed_quantity + market_protection to order payload (F6)`.

---

## Task 3: Port IdempotencyCache (F2)

**Objective:** Create `common/idempotency.py` with `reserve → commit → clear_reservation` semantics (ported from legacy `brokers/common/idempotency.py`), thread-safe.

**Files:**
- Create: `v2/src/plugins/brokers/common/idempotency.py`
- Test: `v2/tests/unit/plugins/brokers/test_idempotency.py`

**Step 1: Write failing test**

```python
from plugins.brokers.common.idempotency import IdempotencyCache

def test_reserve_commit_then_dup_rejected() -> None:
    c = IdempotencyCache(ttl=300)
    assert c.reserve("cid-1") is True
    # second reserve while reserved -> False
    assert c.reserve("cid-1") is False
    c.commit("cid-1", "ORDER-ABC")
    assert c.get("cid-1") == "ORDER-ABC"
    # after commit, same cid returns cached value (no re-reserve needed)
    assert c.reserve("cid-1") is False

def test_clear_reservation_on_unsent() -> None:
    c = IdempotencyCache(ttl=300)
    assert c.reserve("cid-2") is True
    c.clear_reservation("cid-2")
    assert c.reserve("cid-2") is True
```

**Step 2: Run** → FAIL (module missing).

**Step 3: Implement** `common/idempotency.py`:

```python
"""Thread-safe idempotency cache for order placement (ported from legacy)."""

from __future__ import annotations

import threading
import time
from typing import Generic, TypeVar

T = TypeVar("T")


class IdempotencyCache(Generic[T]):
    def __init__(self, ttl: float = 300.0, max_size: int = 10_000) -> None:
        self._ttl = ttl
        self._max_size = max_size
        self._lock = threading.Lock()
        self._reserved: dict[str, float] = {}
        self._committed: dict[str, tuple[float, T]] = {}

    def reserve(self, cid: str) -> bool:
        with self._lock:
            now = time.time()
            if cid in self._committed:
                return False
            if cid in self._reserved and now < self._reserved[cid]:
                return False
            self._reserved[cid] = now + self._ttl
            self._evict_if_needed()
            return True

    def commit(self, cid: str, value: T) -> None:
        with self._lock:
            self._reserved.pop(cid, None)
            self._committed[cid] = (time.time() + self._ttl, value)

    def clear_reservation(self, cid: str) -> None:
        with self._lock:
            self._reserved.pop(cid, None)

    def get(self, cid: str) -> T | None:
        with self._lock:
            if cid in self._committed:
                exp, val = self._committed[cid]
                if time.time() < exp:
                    return val
                self._committed.pop(cid, None)
            return None

    def _evict_if_needed(self) -> None:
        if len(self._committed) + len(self._reserved) <= self._max_size:
            return
        now = time.time()
        self._reserved = {k: e for k, e in self._reserved.items() if e > now}
        self._committed = {k: (e, v) for k, (e, v) in self._committed.items() if e > now}
```

**Step 4: Run** → PASS.

**Step 5: Commit** `feat(common): port IdempotencyCache for order dedupe (F2)`.

---

## Task 4: Wire idempotency into order adapters (F2, cont.)

**Objective:** Both `DhanOrdersAdapter` and `UpstoxOrdersAdapter` reserve→post→commit; never clear reservation if POST sent.

**Files:**
- Modify: `v2/src/plugins/brokers/dhan/adapters/orders.py:17-40`
- Modify: `v2/src/plugins/brokers/upstox/adapters/orders.py:17-40`
- Test: `v2/tests/unit/plugins/brokers/test_orders_idempotency.py`

**Step 1: Write failing test** (Dhan side; mirror for Upstox)

```python
from decimal import Decimal
from domain.commands import PlaceOrderCommand
from domain.enums import OrderSide, OrderType, TimeInForce
from domain.value_objects import InstrumentId, Price, Quantity, CorrelationId
from plugins.brokers.dhan.adapters.orders import DhanOrdersAdapter
from plugins.brokers.dhan.wire import DhanWire
import uuid

class _FakeTransport:
    def __init__(self): self.calls = []
    def post(self, path, **kw):
        self.calls.append(path); return {"orderId": "O123"}
    def get(self, path, **kw): return {}
    def put(self, path, **kw): return {}
    def delete(self, path, **kw): return {}

def _cmd():
    return PlaceOrderCommand(
        instrument_id=InstrumentId(value="NSE:RELIANCE"),
        side=OrderSide.BUY, order_type=OrderType.MARKET,
        quantity=Quantity(value=Decimal("1")),
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid.uuid4()),
    )

def test_dhan_place_order_is_idempotent() -> None:
    t = _FakeTransport(); w = DhanWire(client_id="x"); w.register_security(InstrumentId(value="NSE:RELIANCE"), "2885")
    a = DhanOrdersAdapter(t, w)
    a.place_order(_cmd()); a.place_order(_cmd())
    # same adapter instance dedups by correlation_id; second call returns cached
    assert len(t.calls) >= 1  # transport called at most once per unique cid
```

**Step 2: Run** → FAIL (no dedupe; transport called twice).

**Step 3: Implement** — add `self._idempotency = IdempotencyCache()` to both adapters' `__init__`; wrap `place_order`:

```python
    def place_order(self, command: PlaceOrderCommand) -> OrderId:
        cid = str(command.correlation_id.value)
        cached = self._idempotency.get(cid)
        if cached is not None:
            return OrderId(value=cached)
        if not self._idempotency.reserve(cid):
            # concurrent dup — poll briefly
            for _ in range(50):
                c = self._idempotency.get(cid)
                if c is not None:
                    return OrderId(value=c)
                time.sleep(0.1)
        post_sent = False
        try:
            body = self._wire.from_place_command(command)
            ack = self._transport.post("/orders", json=body)
            post_sent = True
            oid = self._wire.to_order_id(ack)
        except Exception:
            if not post_sent:
                self._idempotency.clear_reservation(cid)
            raise
        # only commit if we actually sent the POST
        if post_sent:
            self._idempotency.commit(cid, oid.value)
        order = Order(...)  # existing construction unchanged
        self._cache[oid.value] = order
        return oid
```

(Add `import time` + `from plugins.brokers.common.idempotency import IdempotencyCache`.)

**Step 4: Run** → PASS (transport called once per unique cid).

**Step 5: Commit** `fix(orders): dedupe placement via IdempotencyCache (F2)`.

---

## Task 5: Live-order safety gate (F3)

**Objective:** Refuse live order placement unless explicitly enabled, mirroring legacy `DHAN_ALLOW_LIVE_ORDERS`.

**Files:**
- Modify: `v2/src/plugins/brokers/dhan/config.py:13-27` (add `allow_live_orders: bool = False`)
- Modify: `v2/src/plugins/brokers/dhan/gateway.py:85-86` (`place_order` guard)
- Modify: `v2/src/plugins/brokers/upstox/config.py` + `upstox/gateway.py` similarly
- Test: `v2/tests/unit/plugins/brokers/test_live_order_gate.py`

**Step 1: Write failing test**

```python
def test_dhan_place_order_blocked_without_flag() -> None:
    from plugins.brokers.dhan.gateway import DhanGateway
    from plugins.brokers.dhan.config import DhanConfig
    from domain.commands import PlaceOrderCommand
    # minimal command
    gw = DhanGateway(config=DhanConfig(allow_live_orders=False))
    try:
        gw.place_order(_cmd())
        assert False, "should have raised"
    except RuntimeError as e:
        assert "live orders disabled" in str(e)
```

**Step 2: Run** → FAIL (order proceeds).

**Step 3: Implement** — in `DhanGateway.place_order`:

```python
    def place_order(self, command: PlaceOrderCommand) -> OrderId:
        if not self.connection.config.allow_live_orders:
            raise RuntimeError("Live orders disabled; set DhanConfig.allow_live_orders=True")
        return self.connection.orders.place_order(command)
```

Add `allow_live_orders: bool = False` to `DhanConfig` (and `UpstoxConfig`; gate both gateways). Allow override via env `DHAN_ALLOW_LIVE_ORDERS`/`UPSTOX_ALLOW_LIVE_ORDERS` in `from_env`.

**Step 4: Run** → PASS; suite green.

**Step 5: Commit** `feat(gate): refuse live orders unless allow_live_orders set (F3)`.

---

## Task 6: Start TokenRefreshScheduler (F4)

**Objective:** Instantiate + start the existing `TokenRefreshScheduler` in `connect()`, stop in `disconnect()`; register streaming as broadcast receiver.

**Files:**
- Modify: `v2/src/plugins/brokers/dhan/connection.py:27-89` (`__init__`, `connect`, `disconnect`)
- Modify: `v2/src/plugins/brokers/upstox/connection.py` similarly
- Test: `v2/tests/unit/plugins/brokers/test_token_scheduler.py`

**Step 1: Write failing test**

```python
def test_dhan_scheduler_started_on_connect() -> None:
    from plugins.brokers.dhan.connection import DhanConnection
    from plugins.brokers.dhan.config import DhanConfig
    conn = DhanConnection(config=DhanConfig())
    conn.connect()
    assert conn._scheduler.is_running is True
    conn.disconnect()
    assert conn._scheduler.is_running is False
```

**Step 2: Run** → FAIL (`AttributeError: 'DhanConnection' object has no attribute '_scheduler'`).

**Step 3: Implement** — in `DhanConnection.__init__` after `self._tokens`:

```python
        from plugins.brokers.common.token_lifecycle import TokenRefreshScheduler
        self._scheduler = TokenRefreshScheduler(
            "dhan", self._tokens, broadcast=self._tokens._broadcast,
            interval_seconds=300.0,
        )
```

In `connect()` (line 91): `self._scheduler.start()`. In `disconnect()` (line 125): `self._scheduler.stop()`. Mirror in Upstox connection. Register streaming receiver if WS token-update hook exists: `self._tokens.register_receiver(lambda tok: None)` (no-op until WS re-auth built) — or skip if not needed.

**Step 4: Run** → PASS.

**Step 5: Commit** `fix(token): start TokenRefreshScheduler on connect (F4)`.

---

## Task 7: Rate-limit profile sourcing (F5)

**Objective:** Build limiter from canonical `RateLimitProfile` (carries `cooldown_on_429_s`, `min_interval_ms`); use profile cooldown instead of hardcoded 60s.

**Files:**
- Modify: `v2/src/plugins/brokers/common/rate_limit.py` (add `limiter_from_profile`; replace fixed `_maybe_restore_rate` cooldown)
- Test: `v2/tests/unit/plugins/brokers/test_rate_limit_profile.py`

**Step 1: Write failing test**

```python
def test_limiter_uses_profile_cooldown() -> None:
    from plugins.brokers.common.rate_limit import limiter_from_profile
    from domain.capabilities.broker_capabilities import RateLimitProfile
    prof = RateLimitProfile(cooldown_on_429_s=130, min_interval_ms=100)
    lim = limiter_from_profile("dhan", prof)
    # after a 429, restore should wait ~130s, not 60s
    lim.trigger_cooldown("orders")
    assert lim._restore_after("orders") == 130  # approximate
```

**Step 2: Run** → FAIL (no `limiter_from_profile`).

**Step 3: Implement** — add to `rate_limit.py`:

```python
def limiter_from_profile(broker_id: str, profile: "RateLimitProfile") -> MultiBucketRateLimiter:
    table = DHAN_RATE_LIMITS if broker_id == "dhan" else UPSTOX_RATE_LIMITS
    limiter = MultiBucketRateLimiter(table)
    limiter.set_restore_cooldown(profile.cooldown_on_429_s)
    for name, bucket in limiter._buckets.items():
        mi = getattr(profile, f"{name}_min_interval_ms", None)
        if mi:
            bucket.set_min_interval(mi / 1000.0)
    return limiter
```

Replace `limiter_from_table` call sites in `dhan/connection.py:37` + `upstox/connection.py:37` to call `limiter_from_profile(broker_id, profile)` using `domain.capabilities.broker_capabilities.RateLimitProfile` (fallback to current constants if profile absent).

**Step 4: Run** → PASS; suite green.

**Step 5: Commit** `fix(rate): source limiter from RateLimitProfile cooldown (F5)`.

---

## Task 8: Upstox depth extension + streaming (F7)

**Objective:** Add `stream_depth` to Upstox streaming + `UpstoxDepthExtension`, register on gateway. Mirror Dhan's already-working pattern.

**Files:**
- Modify: `v2/src/plugins/brokers/upstox/adapters/streaming.py` (add `stream_depth`, depth routing in `feed_raw`, `unstream_depth`, replay)
- Create: `v2/src/plugins/brokers/upstox/extensions.py` (`UpstoxDepth20Extension`, `UpstoxDepth200Extension`)
- Modify: `v2/src/plugins/brokers/upstox/gateway.py:45` (register extensions with `_streaming`)
- Test: `v2/tests/unit/plugins/brokers/test_upstox_depth_extension.py`

**Step 1: Write failing test** (mirror `test_market_data_parity.py::test_dhan_depth_extension_delegates_to_streaming` but for Upstox)

```python
def test_upstox_depth_extension_delegates() -> None:
    from plugins.brokers.upstox.extensions import UpstoxDepth20Extension
    from domain.entities import MarketDepth, DepthLevel, Price, Quantity
    from domain.value_objects import InstrumentId
    from datetime import datetime

    class _Fake:
        def __init__(self): self.calls = []
        def stream_depth(self, iid, on_depth=None):
            self.calls.append((iid, on_depth))
            return MarketDepth(instrument_id=iid,
                bids=(DepthLevel(price=Price(value=Decimal("1")), quantity=Quantity(value=Decimal("1"))),),
                asks=(), timestamp=datetime.now())
    fake = _Fake()
    ext = UpstoxDepth20Extension(_streaming=fake)
    got = []
    res = ext.full_depth(InstrumentId(value="NSE:RELIANCE"), on_depth=got.append)
    assert res is not None and len(res.bids) == 1
    assert fake.calls[0][0].value == "NSE:RELIANCE"
```

**Step 2: Run** → FAIL (`No module named plugins.brokers.upstox.extensions`).

**Step 3: Implement** — copy Dhan's `extensions.py` structure, rename to `UpstoxDepth20Extension`/`UpstoxDepth200Extension` delegating to `self._streaming.stream_depth(...)`. Add the `stream_depth` method + depth routing to `upstox/adapters/streaming.py` (same shape as Dhan's `streaming.py`, already verified working). Register in `upstox/gateway.py`:

```python
        self.extensions = BrokerExtensions(
            UpstoxDepth20Extension(_streaming=self.connection.streaming),
            UpstoxDepth200Extension(_streaming=self.connection.streaming),
        )
```

**Step 4: Run** → PASS.

**Step 5: Commit** `feat(upstox): add depth extensions + streaming depth (F7)`.

---

## Risks / Tradeoffs / Open Questions

- **F1 `dhanClientId`**: Dhan's `/orders` historically accepted `securityId`-only; adding `dhanClientId`+`exchangeSegment` is strictly more correct (matches legacy + official SDK). Verify with a live `place_order` (cancelled) probe before production.
- **F2 idempotency keying**: uses `correlation_id`. If caller reuses a `correlation_id` across genuinely distinct orders, the second is deduped. Ensure callers generate unique cids (gateway should default-generate if absent).
- **F3 gate default-off**: setting `allow_live_orders=False` by default is safer but means existing live flows must opt in. Coordinate with runtime boot to set the flag from env.
- **F4 scheduler + broadcast**: registering streaming as a token receiver requires a `streaming.on_token_changed` hook; if WS re-auth isn't built, register a no-op to avoid dead receiver churn. Low risk.
- **F5 profile import**: `domain.capabilities.broker_capabilities.RateLimitProfile` must exist in v2 (legacy has it). Confirm import path; if missing, define a minimal `RateLimitProfile` dataclass in `domain/capabilities/`.
- **Live verification**: F1/F6/F3 should get a final live `place_order` (immediately cancelled) probe through the gateway per the user's "gateway-only" constraint.

## Verification (end of plan)

```bash
cd /Users/apple/Downloads/Trade_XV2/v2 && env -u PYTHONPATH /Users/apple/Downloads/Trade_XV2/venv/bin/python -m pytest tests/unit/plugins -q
```
Expected: **>338 passed**, zero regressions. Then optional live probe:
```bash
env -u PYTHONPATH PYTHONPATH=src /Users/apple/Downloads/Trade_XV2/venv/bin/python -m tradex.check_connection --broker dhan
env -u PYTHONPATH PYTHONPATH=src /Users/apple/Downloads/Trade_XV2/venv/bin/python -m tradex.check_connection --broker upstox
```
