"""P0/P1: atomic pending exposure reservations under concurrency."""

from __future__ import annotations

import threading
from decimal import Decimal

from application.oms import PositionManager, RiskConfig, RiskManager
from domain import Order, OrderStatus, OrderType, ProductType, Side


def _order(order_id: str, correlation_id: str, qty: int = 10) -> Order:
    return Order(
        order_id=order_id,
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=qty,
        price=Decimal("500"),
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        status=OrderStatus.OPEN,
        correlation_id=correlation_id,
    )


def test_concurrent_pending_reservations_block_second_order():
    """Two concurrent checks cannot both pass when gross limit is exceeded."""
    capital = Decimal("100000")
    config = RiskConfig(max_gross_exposure_pct=Decimal("8"))
    rm = RiskManager(
        PositionManager(),
        config,
        capital_fn=lambda: capital,
    )

    results: list[bool] = []
    barrier = threading.Barrier(2)

    def attempt(cid: str) -> None:
        barrier.wait()
        result = rm.check_order(_order(f"ord-{cid}", cid))
        results.append(result.allowed)

    t1 = threading.Thread(target=attempt, args=("a",))
    t2 = threading.Thread(target=attempt, args=("b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results.count(True) == 1
    assert results.count(False) == 1


def test_release_pending_allows_follow_up_order():
    capital = Decimal("100000")
    config = RiskConfig(max_gross_exposure_pct=Decimal("8"))
    rm = RiskManager(
        PositionManager(),
        config,
        capital_fn=lambda: capital,
    )

    first = rm.check_order(_order("ord-1", "corr-1"))
    assert first.allowed is True

    second = rm.check_order(_order("ord-2", "corr-2"))
    assert second.allowed is False

    rm.release_pending("corr-1")
    third = rm.check_order(_order("ord-3", "corr-3"))
    assert third.allowed is True