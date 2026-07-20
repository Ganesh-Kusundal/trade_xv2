"""Order & news services — place/cancel/modify orders plus news and order lists."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from brokers.session import BrokerSession

from ._session import _borrow_session, check_live_actionable
from .capabilities import _session_gateway
from .order_port import order_port_from_session


def get_news(
    broker: str,
    *,
    symbol: str | None = None,
    category: str = "holdings",
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> Any:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        gw = _session_gateway(s)
        if gw is None:
            raise RuntimeError(f"broker {broker!r} has no gateway for news")
        news = getattr(gw, "news", None)
        if news is None:
            raise RuntimeError(f"broker {broker!r} does not support news")
        client = news() if callable(news) else news
        if symbol:
            fn = getattr(client, "get_news", None) or getattr(client, "symbol_news", None)
            if fn is None:
                raise RuntimeError("news client has no symbol lookup")
            return fn(symbol=symbol)
        fn = getattr(client, "get_news", None)
        if fn is None:
            raise RuntimeError("news client unavailable")
        return fn(category=category)
    finally:
        if close:
            s.close()


def list_super_orders(broker: str, *, session: BrokerSession | None = None, **kwargs: Any) -> Any:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        gw = _session_gateway(s)
        ext = getattr(gw, "extended", None) if gw is not None else None
        fn = getattr(ext, "get_super_orders", None) if ext is not None else None
        if fn is None:
            raise RuntimeError(f"broker {broker!r} does not expose super orders")
        return fn()
    finally:
        if close:
            s.close()


def list_forever_orders(broker: str, *, session: BrokerSession | None = None, **kwargs: Any) -> Any:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        gw = _session_gateway(s)
        ext = getattr(gw, "extended", None) if gw is not None else None
        fn = getattr(ext, "get_all_forever_orders", None) if ext is not None else None
        if fn is None:
            raise RuntimeError(f"broker {broker!r} does not expose forever orders")
        return fn()
    finally:
        if close:
            s.close()


def place_order(
    broker: str,
    symbol: str,
    quantity: int,
    *,
    side: str = "BUY",
    price: Any | None = None,
    order_type: str = "LIMIT",
    product_type: str = "INTRADAY",
    exchange: str = "NSE",
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> Any:
    # M1: live-actionable gate — refuse live brokers unless the production
    # readiness gate has passed.  Paper/mock always allowed.
    check_live_actionable(broker)
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        port = order_port_from_session(s)
        if port is not None:
            px = Decimal(str(price)) if price is not None else None
            return port.place_order(
                symbol=symbol,
                exchange=exchange,
                side=(side or "BUY").upper(),
                quantity=quantity,
                price=px,
                order_type=order_type,
                product_type=product_type,
            )
        inst = s.stock(symbol, exchange=exchange)
        px = Decimal(str(price)) if price is not None else None
        if (side or "BUY").upper() == "SELL":
            return s.sell(
                inst, quantity, price=px, order_type=order_type, product_type=product_type
            )
        return s.buy(inst, quantity, price=px, order_type=order_type, product_type=product_type)
    finally:
        if close:
            s.close()


def cancel_order(
    broker: str,
    order_id: str,
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> Any:
    check_live_actionable(broker)
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        port = order_port_from_session(s)
        if port is not None and hasattr(port, "cancel_order"):
            return port.cancel_order(order_id)
        return s.cancel(order_id)
    finally:
        if close:
            s.close()


def modify_order(
    broker: str,
    order_id: str,
    *,
    quantity: int | None = None,
    price: Any | None = None,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> Any:
    check_live_actionable(broker)
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        kw: dict[str, Any] = {}
        if quantity is not None:
            kw["quantity"] = quantity
        if price is not None:
            kw["price"] = Decimal(str(price))
        port = order_port_from_session(s)
        if port is not None and hasattr(port, "modify_order"):
            return port.modify_order(order_id, **kw)
        return s.modify(order_id, **kw)
    finally:
        if close:
            s.close()


__all__ = [
    "cancel_order",
    "get_news",
    "list_forever_orders",
    "list_super_orders",
    "modify_order",
    "place_order",
]
