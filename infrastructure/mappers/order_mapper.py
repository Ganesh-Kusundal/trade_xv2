"""Broker order field mapping and dict → Order parsing.

Lives in the adapter layer — domain ``Order`` must not know broker dict shapes.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any, Protocol

from domain.entities.order import Order
from domain.parsing import parse_decimal as _parse_optional_decimal
from domain.status_mapper import StatusMapperRegistry
from domain.types import OrderType, Side


class FieldMapping(Protocol):
    """Broker-specific field name mapping for Order parsing."""

    def map_order_id(self, data: dict) -> str: ...
    def map_symbol(self, data: dict) -> str: ...
    def map_exchange(self, data: dict) -> str: ...
    def map_side(self, data: dict) -> str: ...
    def map_order_type(self, data: dict) -> str: ...
    def map_status(self, data: dict) -> str: ...
    def map_quantity(self, data: dict) -> int: ...
    def map_filled_quantity(self, data: dict) -> int: ...
    def map_price(self, data: dict) -> str | None: ...
    def map_avg_price(self, data: dict) -> str | None: ...
    def map_reject_reason(self, data: dict) -> str: ...


class DefaultFieldMapping:
    """Fallback mapping for camelCase (Dhan) and snake_case field names."""

    def map_order_id(self, data: dict) -> str:
        return str(data.get("orderId", data.get("order_id", "")))

    def map_symbol(self, data: dict) -> str:
        return str(data.get("tradingSymbol", data.get("symbol", "")))

    def map_exchange(self, data: dict) -> str:
        return str(data.get("exchangeSegment", data.get("exchange", "NSE")))

    def map_side(self, data: dict) -> str:
        return str(data.get("transactionType", data.get("side", "BUY"))).upper()

    def map_order_type(self, data: dict) -> str:
        raw = str(data.get("orderType", data.get("order_type", "MARKET"))).upper()
        aliases = {
            "STOPLOSS_LIMIT": "STOP_LOSS",
            "STOPLOSS_MARKET": "STOP_LOSS_MARKET",
            "STOPLOSS-MARKET": "STOP_LOSS_MARKET",
            "SL": "STOP_LOSS",
            "SLM": "STOP_LOSS_MARKET",
        }
        return aliases.get(raw, raw)

    def map_status(self, data: dict) -> str:
        return str(data.get("orderStatus", data.get("status", "OPEN"))).upper()

    def map_quantity(self, data: dict) -> int:
        return int(data.get("quantity", 0))

    def map_filled_quantity(self, data: dict) -> int:
        return int(data.get("filledQty", data.get("filled_quantity", 0)))

    def map_price(self, data: dict) -> str | None:
        v = data.get("price")
        return None if v in (None, "") else str(v)

    def map_avg_price(self, data: dict) -> str | None:
        v = data.get("averagePrice", data.get("avg_price", data.get("average_price")))
        return None if v in (None, "") else str(v)

    def map_reject_reason(self, data: dict) -> str:
        return str(data.get("rejectReason", data.get("reject_reason", "")))


def _normalize_side(raw: str) -> Side:
    return Side.BUY if raw == "BUY" else Side.SELL


def _normalize_order_type(raw: str) -> OrderType:
    try:
        return OrderType(raw)
    except ValueError:
        return OrderType.MARKET


def order_from_broker_dict(
    d: dict,
    field_mapping: FieldMapping | None = None,
    exchange_resolver: Callable[[str], Any] | None = None,
) -> Order:
    """Construct a canonical Order from a broker-specific dict."""
    mapping = field_mapping or DefaultFieldMapping()
    return Order(
        order_id=mapping.map_order_id(d),
        symbol=mapping.map_symbol(d),
        exchange=exchange_resolver(mapping.map_exchange(d))
        if exchange_resolver
        else mapping.map_exchange(d),
        side=_normalize_side(mapping.map_side(d)),
        order_type=_normalize_order_type(mapping.map_order_type(d)),
        status=StatusMapperRegistry.normalize(mapping.map_status(d)),
        quantity=mapping.map_quantity(d),
        filled_quantity=mapping.map_filled_quantity(d),
        price=_parse_optional_decimal(mapping.map_price(d)) or Decimal("0"),
        avg_price=_parse_optional_decimal(mapping.map_avg_price(d)) or Decimal("0"),
        reject_reason=mapping.map_reject_reason(d),
    )
