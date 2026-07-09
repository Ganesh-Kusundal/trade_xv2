"""Epic 2 W2 — trade mode gates + modify/cancel contracts (no live order placement).

TR-022: mode=trade requires process OMS; with OMS, orders_enabled.
TR-024: paper modify/cancel already in test_trading_object_model; here we pin
         OrderServicePort contract surface used by both brokers' sim path.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

import tradex
from application.oms.process_context import register_oms_context, reset_oms_context
from application.oms.session_bridge import build_oms_service
from brokers.paper.execution_provider import PaperExecutionProvider
from brokers.paper.paper_gateway import PaperGateway
from domain.connect_errors import ConnectError
from domain.enums import OrderStatus


def _status_value(order) -> str:
    st = getattr(order, "status", None)
    if st is None:
        return ""
    return st.value if hasattr(st, "value") else str(st)


def test_tr022_trade_mode_without_oms_raises() -> None:
    reset_oms_context()
    mock_gw = MagicMock(name="DhanGateway")
    with patch("tradex.runtime.gateway_factory.create_gateway", return_value=mock_gw):
        import brokers.dhan  # noqa: F401

        with pytest.raises(ConnectError) as ei:
            tradex.connect("dhan", mode="trade", load_instruments=False)
        assert ei.value.code == "OMS_REQUIRED"
        assert ei.value.remediation


def test_tr022_trade_mode_with_process_oms_enables_orders() -> None:
    reset_oms_context()
    mock_gw = MagicMock(name="DhanGateway")
    # Process OMS registered from paper EP (transport-agnostic admission gate)
    ep = PaperExecutionProvider(PaperGateway(initial_capital=Decimal("1000000")))
    oms = build_oms_service(ep, broker_id="paper")

    class _Ctx:
        order_manager = oms.order_manager

    register_oms_context(_Ctx())  # type: ignore[arg-type]
    try:
        with patch("tradex.runtime.gateway_factory.create_gateway", return_value=mock_gw):
            import brokers.dhan  # noqa: F401

            session = tradex.connect("dhan", mode="trade", load_instruments=False)
            try:
                assert session.status is not None
                assert session.status.mode == "trade"
                assert session.status.orders_enabled is True
                assert session.order_service is not None
            finally:
                session.close()
    finally:
        reset_oms_context()


def test_tr024_paper_modify_and_cancel_via_order_service() -> None:
    """TR-024 paper contract: modify then cancel through session OMS API."""
    session = tradex.connect("paper")
    try:
        stock = session.universe.equity("RELIANCE")
        placed = stock.buy(
            1,
            price=Decimal("1"),
            correlation_id="e2e:tr024:mod-cancel",
        )
        assert placed.success and placed.order is not None
        oid = placed.order.order_id
        assert _status_value(placed.order) == OrderStatus.OPEN.value

        mod = session.modify(oid, price=Decimal("2"))
        assert mod.success is True

        can = session.cancel(oid)
        assert can.success is True
        if can.order is not None:
            assert _status_value(can.order) in {
                OrderStatus.CANCELLED.value,
                "CANCELLED",
                "CANCELED",
            }
    finally:
        session.close()


def test_tr024_order_service_has_modify_cancel() -> None:
    """Port surface both live brokers must satisfy when OMS is wired."""
    session = tradex.connect("paper")
    try:
        osvc = session.order_service
        assert osvc is not None
        assert callable(getattr(osvc, "cancel", None))
        assert callable(getattr(osvc, "modify", None))
    finally:
        session.close()
