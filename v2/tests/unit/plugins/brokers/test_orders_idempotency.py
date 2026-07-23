"""Regression: order placement is idempotent by correlation_id (F2).

Mirrors legacy IdempotencyCache.reserve -> post -> commit semantics: a
repeated place_order with the same correlation_id must not send a second
HTTP POST (which would duplicate the broker order on retry/restart).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from domain.commands import PlaceOrderCommand
from domain.enums import OrderSide, OrderType, TimeInForce
from domain.value_objects import InstrumentId, Price, Quantity, CorrelationId

from plugins.brokers.dhan.adapters.orders import DhanOrdersAdapter
from plugins.brokers.dhan.wire import DhanWire
from plugins.brokers.upstox.adapters.orders import UpstoxOrdersAdapter
from plugins.brokers.upstox.wire import UpstoxWire


class _FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def post(self, path: str, **kwargs: object) -> dict:
        self.calls.append(("POST", path))
        return {"orderId": "O123", "order_id": "O123"}

    def get(self, path: str, **kwargs: object) -> dict:
        self.calls.append(("GET", path))
        return {}

    def put(self, path: str, **kwargs: object) -> dict:
        self.calls.append(("PUT", path))
        return {}

    def delete(self, path: str, **kwargs: object) -> dict:
        self.calls.append(("DELETE", path))
        return {}


def _cmd(cid: CorrelationId) -> PlaceOrderCommand:
    return PlaceOrderCommand(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Quantity(value=Decimal("1")),
        price=None,
        time_in_force=TimeInForce.DAY,
        correlation_id=cid,
    )


def test_dhan_place_order_is_idempotent() -> None:
    t = _FakeTransport()
    w = DhanWire(client_id="x")
    w.register_security(InstrumentId.parse("NSE:RELIANCE"), "2885")
    adapter = DhanOrdersAdapter(t, w)
    cid = CorrelationId(value=uuid.uuid4())
    adapter.place_order(_cmd(cid))
    adapter.place_order(_cmd(cid))  # same correlation_id
    posts = [c for c in t.calls if c[0] == "POST"]
    assert len(posts) == 1  # only one POST for one unique cid


def test_upstox_place_order_is_idempotent() -> None:
    t = _FakeTransport()
    w = UpstoxWire()
    w.register_key(InstrumentId.parse("NSE:RELIANCE"), "NSE_EQ|INE002A01018")
    adapter = UpstoxOrdersAdapter(t, w)
    cid = CorrelationId(value=uuid.uuid4())
    adapter.place_order(_cmd(cid))
    adapter.place_order(_cmd(cid))
    posts = [c for c in t.calls if c[0] == "POST"]
    assert len(posts) == 1


def test_distinct_correlation_ids_send_distinct_posts() -> None:
    t = _FakeTransport()
    w = DhanWire(client_id="x")
    w.register_security(InstrumentId.parse("NSE:RELIANCE"), "2885")
    adapter = DhanOrdersAdapter(t, w)
    adapter.place_order(_cmd(CorrelationId(value=uuid.uuid4())))
    adapter.place_order(_cmd(CorrelationId(value=uuid.uuid4())))
    posts = [c for c in t.calls if c[0] == "POST"]
    assert len(posts) == 2
