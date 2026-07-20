"""Dhan order gateway — thin adapter mirroring upstox/adapters/order_gateway."""

from __future__ import annotations

from typing import Any


class DhanOrderGateway:
    """Order placement gateway delegating to Dhan OrdersAdapter."""

    def __init__(self, orders_adapter: Any) -> None:
        self._orders = orders_adapter

    def place_order(self, *args: Any, **kwargs: Any) -> Any:
        return self._orders.place_order(*args, **kwargs)

    def modify_order(self, *args: Any, **kwargs: Any) -> Any:
        return self._orders.modify_order(*args, **kwargs)

    def cancel_order(self, *args: Any, **kwargs: Any) -> Any:
        return self._orders.cancel_order(*args, **kwargs)
