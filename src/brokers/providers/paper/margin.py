"""Paper margin provider — trivial sim margin (cash required = notional)."""

from __future__ import annotations

from decimal import Decimal

from brokers.common.api import MarginProvider, MarginResult
from brokers.common.oms.margin_provider import parse_margin_response


class PaperMarginProvider(MarginProvider):
    """Sim margin: required = qty * price; available from initial capital."""

    def __init__(self, available: Decimal = Decimal("1000000")) -> None:
        self._available = available

    def calculate_margin(self, payload: dict) -> dict:
        qty = int(payload.get("quantity", 0))
        price = Decimal(str(payload.get("price", 0) or 0))
        required = abs(qty) * price
        return {
            "totalMargin": required,
            "orderMargin": required,
            "availableMargin": self._available,
            "spanMargin": Decimal("0"),
            "exposureMargin": Decimal("0"),
        }

    def calculate_margin_for_order(
        self,
        symbol: str,
        exchange: str,
        quantity: int,
        price: Decimal,
        product_type: str,
        order_type: str,
    ) -> MarginResult:
        return parse_margin_response(
            self.calculate_margin(
                {
                    "symbol": symbol,
                    "exchange": exchange,
                    "quantity": quantity,
                    "price": price,
                    "product_type": product_type,
                    "order_type": order_type,
                }
            )
        )


__all__ = ["PaperMarginProvider"]
