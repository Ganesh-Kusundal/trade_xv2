"""Dhan cover order adapter."""

from __future__ import annotations

from decimal import Decimal

from brokers.common.api.ports import CoverOrderProvider
from brokers.common.core.models import Order, OrderRequest


class DhanCoverOrderAdapter(CoverOrderProvider):
    """Dhan cover-order adapter.

    Trade_J implements this as unsupported until Dhan exposes a dedicated cover
    endpoint. This adapter preserves the capability surface and raises the same
    explicit error instead of silently misrouting the request.
    """

    def place_cover_order(self, request: OrderRequest, stop_loss_price: Decimal) -> Order:
        raise NotImplementedError(
            "Dhan cover order placement requires a dedicated Dhan API endpoint"
        )

    def exit_cover_order(self, order_id: str) -> Order:
        raise NotImplementedError("Dhan cover order exit requires a dedicated Dhan API endpoint")
