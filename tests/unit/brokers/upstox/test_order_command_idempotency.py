"""Regression: Upstox place_order uses reserve/commit idempotency."""

from __future__ import annotations

import threading
from decimal import Decimal
from unittest.mock import MagicMock

from brokers.common.idempotency import IdempotencyCache
from brokers.providers.upstox.orders.order_client import UpstoxRestOrderClient
from brokers.providers.upstox.orders.order_command_adapter import UpstoxOrderCommandAdapter
from domain import ExchangeSegment, Side
from domain import OrderType as EnumsOrderType
from domain import ProductType as EnumsProductType
from domain import Validity as EnumsValidity
from domain.models.dtos import BrokerOrderPayload


class _FakeOrderClient(UpstoxRestOrderClient):
    def __init__(self):
        self.calls = 0

    def place_order_v3(self, payload: dict) -> dict:
        self.calls += 1
        return {"status": "success", "data": {"order_id": f"UPSTOX-{self.calls}"}}


class _SlowOrderClient(UpstoxRestOrderClient):
    def __init__(self):
        self.calls = 0
        self.started = threading.Event()
        self.proceed = threading.Event()

    def place_order_v3(self, payload: dict) -> dict:
        self.calls += 1
        if self.calls == 1:
            self.started.set()
            if not self.proceed.wait(timeout=5):
                raise RuntimeError("timed out waiting to proceed")
        return {"status": "success", "data": {"order_id": "UPSTOX-1"}}


def _request(correlation_id: str) -> BrokerOrderPayload:
    return BrokerOrderPayload(
        symbol="RELIANCE",
        exchange="NSE",
        exchange_segment=ExchangeSegment.NSE,
        transaction_type=Side.BUY,
        quantity=10,
        price=Decimal("2500"),
        order_type=EnumsOrderType.MARKET,
        product_type=EnumsProductType.INTRADAY,
        validity=EnumsValidity.DAY,
        correlation_id=correlation_id,
    )


def test_place_order_concurrent_same_correlation_id_posts_once():
    client = _SlowOrderClient()

    resolver = MagicMock()
    resolver.resolve.return_value = MagicMock(instrument_key="NSE_EQ|RELIANCE")

    adapter = UpstoxOrderCommandAdapter(
        order_client=client,
        instrument_resolver=resolver,
        idempotency_cache=IdempotencyCache(),
    )

    cid = "race-cid"
    results = []
    errors: list[Exception] = []
    start_barrier = threading.Barrier(10)

    def worker() -> None:
        try:
            start_barrier.wait(timeout=2)
            results.append(adapter.place_order(_request(cid)))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()

    assert client.started.wait(timeout=5), "first broker call did not start"
    client.proceed.set()

    for t in threads:
        t.join(timeout=10)

    assert not errors
    assert len(results) == 10
    assert client.calls == 1
    assert {r.order_id for r in results} == {"UPSTOX-1"}


def test_place_order_idempotency_returns_cached_without_second_post():
    client = _FakeOrderClient()
    resolver = MagicMock()
    resolver.resolve.return_value = MagicMock(instrument_key="NSE_EQ|RELIANCE")
    cache = IdempotencyCache()

    adapter = UpstoxOrderCommandAdapter(
        order_client=client,
        instrument_resolver=resolver,
        idempotency_cache=cache,
    )

    cid = "cached-cid"
    first = adapter.place_order(_request(cid))
    second = adapter.place_order(_request(cid))

    assert first.success and second.success
    assert first is second
    assert client.calls == 1
