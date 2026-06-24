"""Upstox margin adapter — implements ``MarginProvider`` port."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from brokers.common.api.ports import MarginCalculationError, MarginProvider, MarginResult
from brokers.upstox.market_data.margin import UpstoxMarginClient


class UpstoxMarginAdapter(MarginProvider):
    def __init__(self, client: UpstoxMarginClient) -> None:
        self._client = client

    def calculate_margin(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._client.calculate_margin(payload)

    def calculate_margin_for_order(
        self,
        symbol: str,
        exchange: str,
        quantity: int,
        price: Decimal,
        product_type: str,
        order_type: str,
    ) -> MarginResult:
        payload = {
            "symbol": symbol,
            "exchange": exchange,
            "quantity": quantity,
            "price": float(price),
            "product_type": product_type,
            "order_type": order_type,
        }
        try:
            raw = self.calculate_margin(payload)
        except Exception as exc:
            raise MarginCalculationError(f"Upstox margin API call failed: {exc}") from exc
        return _parse_margin_response(raw)


def _parse_margin_response(raw: dict[str, Any]) -> MarginResult:
    data = raw.get("data", raw) if isinstance(raw, dict) else {}
    if not isinstance(data, dict):
        data = raw if isinstance(raw, dict) else {}

    required = Decimal("0")
    for key in ("total_margin", "totalMargin", "order_margin", "orderMargin", "required_margin"):
        if key in data:
            required = Decimal(str(data[key]))
            break

    available = Decimal("0")
    for key in ("available_margin", "availableMargin", "net_available"):
        if key in data:
            available = Decimal(str(data[key]))
            break

    span: Decimal | None = None
    for key in ("span_margin", "spanMargin"):
        if key in data and data[key] is not None:
            span = Decimal(str(data[key]))
            break

    exposure: Decimal | None = None
    for key in ("exposure_margin", "exposureMargin"):
        if key in data and data[key] is not None:
            exposure = Decimal(str(data[key]))
            break

    return MarginResult(
        required_margin=required,
        available_margin=available,
        span_margin=span,
        exposure_margin=exposure,
    )
