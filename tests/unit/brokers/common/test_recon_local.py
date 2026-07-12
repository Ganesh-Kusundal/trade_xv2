"""Local OMS snapshot normalization for reconciliation."""

from __future__ import annotations

from domain import Order, OrderType, Side


def test_local_orders_as_domain_accepts_order_objects() -> None:
    from brokers.common.recon_local import local_orders_as_domain

    order = Order(
        order_id="1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
    )
    out = local_orders_as_domain([order])
    assert out is not None and out[0].order_id == "1"


def test_local_positions_as_domain_from_dict() -> None:
    from brokers.common.recon_local import local_positions_as_domain

    out = local_positions_as_domain(
        [{"trading_symbol": "RELIANCE", "exchange_segment": "NSE", "net_quantity": 3}]
    )
    assert out is not None
    assert out[0].symbol == "RELIANCE"
    assert out[0].quantity == 3