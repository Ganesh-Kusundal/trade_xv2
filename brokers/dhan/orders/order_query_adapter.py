"""Order query adapter for Dhan."""

from __future__ import annotations

from typing import Any

from brokers.common.api.ports import OrderQuery
from brokers.common.core.enums import (
    ExchangeSegment,
    InstrumentType,
    OrderStatus,
    OrderType,
    ProductType,
    TransactionType,
    Validity,
)
from brokers.common.core.models import Order, Trade
from brokers.dhan.mapper.mapping import (
    decimal_value,
    int_value,
    str_field,
    timestamp_from_value,
)
from brokers.dhan.orders.orders import DhanRestOrderClient


class DhanOrderQueryAdapter(OrderQuery):
    """Trade_J-style order query adapter over ``DhanRestOrderClient``."""

    def __init__(self, order_client: DhanRestOrderClient) -> None:
        self._order_client = order_client

    @property
    def order_client(self) -> DhanRestOrderClient:
        return self._order_client

    def get_order(self, order_id: str) -> Order | None:
        return self._order_to_domain(self._order_client.get_order(order_id))

    def get_order_by_correlation_id(self, correlation_id: str) -> Order | None:
        return self._order_to_domain(self._order_client.get_order_by_correlation_id(correlation_id))

    def get_order_list(self) -> list[Order]:
        return [
            order
            for order in (self._order_to_domain(item) for item in self._order_client.get_orders())
            if order is not None
        ]

    def get_trades(self) -> list[Trade]:
        return [
            trade
            for trade in (self._trade_to_domain(item) for item in self._order_client.get_trades())
            if trade is not None
        ]

    def get_trades_for_order(self, order_id: str) -> list[Trade]:
        return [
            trade
            for trade in (
                self._trade_to_domain(item)
                for item in self._order_client.get_trades_for_order(order_id)
            )
            if trade is not None
        ]

    def _order_to_domain(self, payload: dict[str, Any] | None) -> Order | None:
        data = self._unwrap_data(payload)
        if not data:
            return None
        return Order(
            order_id=str_field(data, "orderId", "id", "externalOrderId"),
            correlation_id=str_field(data, "correlationId", "externalOrderId"),
            exchange_segment=self._exchange_segment(
                str_field(data, "exchangeSegment", default=ExchangeSegment.NSE.value)
            ),
            transaction_type=self._transaction_type(str_field(data, "transactionType")),
            quantity=int_value(data.get("quantity") or data.get("orderQuantity")),
            price=decimal_value(data.get("price") or data.get("limitPrice")),
            trigger_price=decimal_value(data.get("triggerPrice")),
            order_type=self._order_type(str_field(data, "orderType")),
            product_type=self._product_type(str_field(data, "productType")),
            validity=self._validity(str_field(data, "validity")),
            status=self._order_status(str_field(data, "orderStatus", "status")),
            filled_quantity=int_value(data.get("filledQuantity") or data.get("filledQty")),
            remaining_quantity=int_value(
                data.get("remainingQuantity")
                or data.get("pendingQuantity")
                or max(
                    int_value(data.get("quantity") or data.get("orderQuantity"))
                    - int_value(data.get("filledQuantity") or data.get("filledQty")),
                    0,
                )
            ),
            average_price=decimal_value(
                data.get("averagePrice") or data.get("avgPrice") or data.get("tradedPrice")
            ),
            order_timestamp=timestamp_from_value(
                data.get("orderTime") or data.get("createdAt") or data.get("updateTime")
            ),
            exchange_order_id=str_field(data, "exchangeOrderId", "exchangeTradeId"),
            reject_reason=str_field(
                data, "rejectReason", "remarks", "message", "omsErrorDescription"
            ),
            instrument_type=self._instrument_type(str_field(data, "instrumentType")),
        )

    def _trade_to_domain(self, payload: dict[str, Any] | None) -> Trade | None:
        data = self._unwrap_data(payload)
        if not data:
            return None
        value = decimal_value(data.get("tradeValue") or data.get("turnover"))
        return Trade(
            trade_id=str_field(data, "tradeId", "exchangeTradeId", "id"),
            order_id=str_field(data, "orderId"),
            exchange_order_id=str_field(data, "exchangeOrderId", "exchangeTradeId"),
            exchange_segment=self._exchange_segment(
                str_field(data, "exchangeSegment", default=ExchangeSegment.NSE.value)
            ),
            transaction_type=self._transaction_type(str_field(data, "transactionType")),
            quantity=int_value(data.get("quantity") or data.get("tradedQuantity")),
            price=decimal_value(data.get("price") or data.get("tradedPrice")),
            trade_value=value
            if value
            else decimal_value(data.get("price") or data.get("tradedPrice"))
            * int_value(data.get("quantity") or data.get("tradedQuantity")),
            trade_timestamp=timestamp_from_value(
                data.get("tradeTime") or data.get("createdAt") or data.get("updateTime")
            ),
            product_type=self._product_type(str_field(data, "productType")),
        )

    @staticmethod
    def _unwrap_data(payload: dict[str, Any] | None) -> dict[str, Any]:
        if not payload:
            return {}
        data = payload.get("data")
        return data if isinstance(data, dict) else payload

    @staticmethod
    def _transaction_type(value: str) -> TransactionType:
        try:
            return TransactionType(value)
        except ValueError:
            return TransactionType.BUY

    @staticmethod
    def _order_type(value: str) -> OrderType:
        try:
            return OrderType(value)
        except ValueError:
            return OrderType.MARKET

    @staticmethod
    def _product_type(value: str) -> ProductType:
        try:
            return ProductType(value)
        except ValueError:
            return ProductType.INTRADAY

    @staticmethod
    def _validity(value: str) -> Validity | None:
        try:
            return Validity(value)
        except ValueError:
            return None

    @staticmethod
    def _order_status(value: str) -> OrderStatus:
        try:
            return OrderStatus(value)
        except ValueError:
            return OrderStatus.PENDING

    @staticmethod
    def _instrument_type(value: str) -> InstrumentType:
        try:
            return InstrumentType(value)
        except ValueError:
            return InstrumentType.EQUITY

    @staticmethod
    def _exchange_segment(value: str) -> ExchangeSegment:
        try:
            return ExchangeSegment(value)
        except ValueError:
            return ExchangeSegment.NSE

    # ── Order stream integration ─────────────────────────────────────

    def subscribe_order_stream(self, order_ids: list[str]) -> bool:
        """Subscribe to order stream for specific order IDs."""
        return self._order_client.subscribe_order_stream(order_ids)

    def unsubscribe_order_stream(self, order_ids: list[str]) -> bool:
        """Unsubscribe from order stream for specific order IDs."""
        return self._order_client.unsubscribe_order_stream(order_ids)

    def get_order_stream_status(self) -> dict[str, Any]:
        """Get order stream status."""
        return self._order_client.get_order_stream_status()

    def add_order_listener(self, listener: Any) -> None:
        """Add an order event listener."""
        self._order_client.add_order_listener(listener)

    def remove_order_listener(self, listener: Any) -> None:
        """Remove an order event listener."""
        self._order_client.remove_order_listener(listener)
