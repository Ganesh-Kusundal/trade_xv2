"""OMS order routing integration via BrokerService (D6: OmsService retired).

Formerly ``test_oms_modify.py``, this exercised ``OmsService`` directly. The
OmsService class has been retired (Decision #7); its order/trade read + write
access and the live_actionable guard now live on ``BrokerService``. This test
verifies the same routing behavior through BrokerService.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from interface.ui.services.broker_service import BrokerService
from domain.entities import OrderResponse


def test_place_order_routes_through_gateway_with_oms_context() -> None:
    from interface.ui.services.cli_broker_facade import CliBrokerFacade

    gw = MagicMock()
    gw.place_order.return_value = OrderResponse.ok(order_id="ORD-1", message="ok")
    ctx = MagicMock()
    svc = BrokerService.__new__(BrokerService)
    # Manually attach the attributes place_order reads.
    svc._trading_context = ctx
    svc._gateway = gw
    svc._live_actionable = False  # place_order must refuse when not live-actionable
    svc._initialized = True
    svc._facade = CliBrokerFacade(svc)
    try:
        svc.place_order("RELIANCE", "NSE", "BUY", 10, price=Decimal("2500"))
        assert False, "expected refusal when not live-actionable"
    except RuntimeError as exc:
        assert "live-actionable" in str(exc)
