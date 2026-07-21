"""Helpers for placing/cancelling via BrokerSession.gateway (object-model migration).

Also accepts domain ``Session`` (uses ``session.buy`` / intent+place) so unit
tests that construct a bare OMS-stamped Session keep working.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from tests.support.order_request_factory import make_order_request


def place_via_gateway(
    session: Any,
    instrument: Any,
    quantity: int,
    *,
    side: str = "BUY",
    price: Decimal | None = None,
    order_type: str | None = None,
    product_type: str = "INTRADAY",
    correlation_id: str | None = None,
) -> Any:
    """Place via ``session.gateway`` when present, else domain ``Session`` OMS."""
    ot = order_type or ("LIMIT" if price is not None else "MARKET")
    gw = getattr(session, "gateway", None)
    if gw is not None:
        return gw.place_order(
            make_order_request(
                symbol=getattr(instrument, "symbol", ""),
                exchange=getattr(instrument, "exchange", "NSE"),
                side=side,
                quantity=quantity,
                price=price if price is not None else Decimal("0"),
                order_type=ot,
                product_type=product_type,
                correlation_id=correlation_id,
            )
        )
    # Domain Session: preserve correlation_id via intent + place
    if correlation_id is not None:
        intent = session.intent(
            instrument,
            side,
            quantity,
            price=price,
            order_type=ot,
            product_type=product_type,
            correlation_id=correlation_id,
        )
        return session.place(intent)
    if str(side).upper() == "SELL":
        return session.sell(instrument, quantity, price=price, order_type=ot, product_type=product_type)
    return session.buy(instrument, quantity, price=price, order_type=ot, product_type=product_type)


def cancel_via_gateway(session: Any, order_id: str) -> Any:
    gw = getattr(session, "gateway", None)
    if gw is not None:
        return gw.cancel_order(order_id)
    return session.cancel(order_id)


def modify_via_gateway(session: Any, order_id: str, **changes: Any) -> Any:
    gw = getattr(session, "gateway", None)
    if gw is not None:
        return gw.modify_order(order_id, **changes)
    return session.modify(order_id, **changes)


def subscribe_via_gateway(
    session: Any,
    instrument: Any,
    callback: Any | None = None,
    *,
    depth: bool = False,
) -> Any:
    """Subscribe through gateway when present; else instrument ``_subscribe_core``."""
    gw = getattr(session, "gateway", None)
    if gw is not None:
        handles = gw.subscribe([instrument], callback, depth=depth)
        return handles[0] if handles else None
    return instrument._subscribe_core(callback, depth=depth)


__all__ = [
    "place_via_gateway",
    "cancel_via_gateway",
    "modify_via_gateway",
    "subscribe_via_gateway",
    "make_order_request",
]
