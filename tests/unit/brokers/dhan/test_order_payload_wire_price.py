"""REF-4 functional regression: a placed Dhan order transmits a numeric-float
``price``/``triggerPrice`` on the wire.

This drives the REAL placement path end to end —
``OrdersAdapter.place_order`` → ``OrderPlacer._place_order_impl`` (identity
resolution, enum canonicalisation, validation, ``assert_dhan_payload``) →
``client.post("/orders", json=payload)`` — and asserts the payload actually
captured by the HTTP client. It does NOT poke the private payload builder in
isolation, so it verifies the *behaviour a caller depends on* (the exact bytes
sent to Dhan), not just the one dict we edited.

Before REF-4, ``price`` was ``str(request.price)``; Dhan super/forever/margin
orders and the official dhanhq SDK (``_order.py``: ``"price": float(price)``)
send a numeric float. This locks the regular-order path to the same,
broker-spec-correct representation.

Real components only: real ``OrdersAdapter`` + ``OrderPlacer`` + ``OrderValidator``
+ ``SymbolResolver`` (via the shared ``resolver`` fixture). The HTTP client is the
repo's standard ``FakeHttpClient`` double, which records the outbound payload.
"""

from __future__ import annotations

from decimal import Decimal

from brokers.providers.dhan.execution.orders import OrdersAdapter
from domain.models.dtos import BrokerOrderPayload


def _place(fake_client, resolver, **overrides) -> dict:
    """Place one order through the real adapter, return the wire payload sent."""
    fake_client.set_response("POST", "/orders", {"data": {"orderId": "ORD-TEST"}})
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)
    fields = {
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "transaction_type": "BUY",
        "quantity": 1,
        "product_type": "INTRADAY",
        **overrides,
    }
    response = adapter.place_order(BrokerOrderPayload(**fields))
    assert response.success, f"placement failed: {response.message}"
    calls = fake_client.calls_for("POST", "/orders")
    assert len(calls) == 1
    return calls[0]


def test_limit_order_transmits_numeric_float_price(fake_client, resolver) -> None:
    # 100.15 is a real fractional tick (multiple of RELIANCE's 0.05 tick); the
    # validator rejects non-aligned prices, which is *why* this end-to-end test
    # is stronger than poking the payload builder directly.
    payload = _place(fake_client, resolver, order_type="LIMIT", price=Decimal("100.15"))
    assert isinstance(payload["price"], float), "price must be numeric float, not str"
    assert payload["price"] == 100.15
    assert "triggerPrice" not in payload


def test_stop_loss_order_transmits_numeric_float_price_and_trigger(fake_client, resolver) -> None:
    payload = _place(
        fake_client,
        resolver,
        transaction_type="SELL",
        quantity=5,
        order_type="STOP_LOSS",
        price=Decimal("100.15"),
        trigger_price=Decimal("99.95"),
    )
    assert isinstance(payload["price"], float)
    assert isinstance(payload["triggerPrice"], float)
    assert payload["price"] == 100.15
    assert payload["triggerPrice"] == 99.95


def test_market_order_transmits_numeric_zero_price(fake_client, resolver) -> None:
    payload = _place(fake_client, resolver, order_type="MARKET")
    assert payload["price"] == 0.0
    assert isinstance(payload["price"], float)
    assert "triggerPrice" not in payload
