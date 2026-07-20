"""OMS acceptance — BrokerFillSource cancel/modify/capabilities (Phase 1a)."""

from __future__ import annotations

from decimal import Decimal

from application.execution.fill_source import BrokerFillSource
from application.oms.order_manager import OmsOrderCommand
from domain import OrderStatus, OrderType, ProductType, Side
from domain.entities import OrderResponse
from domain.orders.requests import ModifyOrderRequest
from domain.ports.execution_target import ExecutionTargetKind


class _RecordingGateway:
    """Minimal gateway recording cancel/modify/place calls."""

    def __init__(self) -> None:
        self.cancelled: list[str] = []
        self.modified: list[tuple[str, dict]] = []
        self._open_order = "broker-order-1"

    def place_order(self, symbol: str, exchange: str, side: str, quantity: int, **kwargs):
        return OrderResponse(
            success=True,
            order_id=self._open_order,
            broker_order_id=self._open_order,
            status=OrderStatus.OPEN,
        )

    def cancel_order(self, order_id: str) -> OrderResponse:
        self.cancelled.append(order_id)
        return OrderResponse(success=True, order_id=order_id, status=OrderStatus.CANCELLED)

    def modify_order(self, order_id: str, **changes) -> OrderResponse:
        self.modified.append((order_id, changes))
        return OrderResponse(success=True, order_id=order_id, status=OrderStatus.OPEN)

    def capabilities(self):
        return {"cancel": True, "modify": True}


def test_broker_fill_source_cancel_modify_capabilities() -> None:
    from runtime.paper_session import build_paper_session

    gateway = _RecordingGateway()
    source = BrokerFillSource(gateway, kind=ExecutionTargetKind.LIVE)

    assert source.capabilities() == {"cancel": True, "modify": True}
    assert source.cancel_fn() is not None
    assert source.modify_fn() is not None

    session = build_paper_session(initial_capital=100_000)
    om = session.trading_context.order_manager

    cmd = OmsOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        price=Decimal("2500"),
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        correlation_id="broker-accept:1",
    )
    placed = om.place_order(cmd, submit_fn=source.submit_fn())
    assert placed.success
    assert placed.order is not None
    order_id = placed.order.order_id

    modify_result = om.modify_order(
        ModifyOrderRequest(order_id=order_id, quantity=2, price=Decimal("2510")),
        modify_fn=source.modify_fn(),
    )
    assert modify_result.success
    assert gateway.modified
    assert gateway.modified[0][0] == order_id
    assert gateway.modified[0][1]["quantity"] == 2

    cancel_result = om.cancel_order(order_id, cancel_fn=source.cancel_fn())
    assert cancel_result.success
    assert gateway.cancelled == [order_id]
