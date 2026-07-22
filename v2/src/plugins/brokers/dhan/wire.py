"""Dhan native dict ↔ domain types."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping
from uuid import UUID, uuid5, NAMESPACE_URL

from domain.commands import PlaceOrderCommand
from domain.entities import Account, MarketDepth, Order, Position, Quote
from domain.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from domain.value_objects import (
    AccountId,
    CorrelationId,
    InstrumentId,
    Money,
    OrderId,
    Price,
    Quantity,
)
from plugins.brokers.common.quote_normalize import normalize_quote
from plugins.brokers.common.wire import BaseWireAdapter


def _corr(raw: object) -> CorrelationId:
    text = str(raw or "")
    try:
        return CorrelationId(value=UUID(text))
    except (ValueError, AttributeError):
        return CorrelationId(value=uuid5(NAMESPACE_URL, text or "dhan-unknown"))

_SECURITY_IDS: dict[str, str] = {
    "NSE:RELIANCE": "2885",
}

_STATUS: dict[str, OrderStatus] = {
    "TRANSIT": OrderStatus.SUBMITTED,
    "PENDING": OrderStatus.PENDING,
    "TRADED": OrderStatus.FILLED,
    "PART_TRADED": OrderStatus.PARTIALLY_FILLED,
    "REJECTED": OrderStatus.REJECTED,
    "CANCELLED": OrderStatus.CANCELLED,
}

_SIDE: dict[str, OrderSide] = {"BUY": OrderSide.BUY, "SELL": OrderSide.SELL}
_OTYPE: dict[str, OrderType] = {
    "MARKET": OrderType.MARKET,
    "LIMIT": OrderType.LIMIT,
    "STOP_LOSS": OrderType.STOP,
    "STOP_LOSS_MARKET": OrderType.STOP,
}


class DhanWire:
    def security_id(self, instrument_id: InstrumentId) -> str:
        # allow raw security id or mapped symbol
        if instrument_id.value in _SECURITY_IDS:
            return _SECURITY_IDS[instrument_id.value]
        if ":" not in instrument_id.value and instrument_id.value.isdigit():
            return instrument_id.value
        raise KeyError(f"no Dhan securityId for {instrument_id.value}")

    def register_security(self, instrument_id: InstrumentId, security_id: str) -> None:
        _SECURITY_IDS[instrument_id.value] = security_id

    def to_quote(self, native: Mapping[str, Any], *, instrument_id: InstrumentId) -> Quote:
        sec = self.security_id(instrument_id)
        raw = native.get("data", native)
        row = raw[sec] if isinstance(raw, Mapping) and sec in raw else raw
        return normalize_quote(
            {
                "bid": row.get("bid", row.get("best_bid", 0)),
                "ask": row.get("ask", row.get("best_ask", 0)),
                "bid_size": row.get("bid_qty", row.get("bid_size", 0)),
                "ask_size": row.get("ask_qty", row.get("ask_size", 0)),
                "timestamp": row.get("last_trade_time", row.get("timestamp")),
            },
            instrument_id=instrument_id,
        )

    def to_ltp(self, native: Mapping[str, Any], *, instrument_id: InstrumentId) -> Price:
        sec = self.security_id(instrument_id)
        raw = native.get("data", native)
        row = raw[sec] if isinstance(raw, Mapping) and sec in raw else raw
        return Price(value=Decimal(str(row.get("ltp", row.get("last_price", 0)))))

    def to_depth(self, native: Mapping[str, Any], *, instrument_id: InstrumentId) -> MarketDepth:
        from domain.entities import DepthLevel

        raw = native.get("data", native)
        sec = self.security_id(instrument_id)
        row = raw[sec] if isinstance(raw, Mapping) and sec in raw else raw
        bids = tuple(
            DepthLevel(
                price=Price(value=Decimal(str(b["price"]))),
                quantity=Quantity(value=Decimal(str(b.get("quantity", b.get("qty", 0))))),
            )
            for b in (row.get("bids") or row.get("buy") or [])
        )
        asks = tuple(
            DepthLevel(
                price=Price(value=Decimal(str(a["price"]))),
                quantity=Quantity(value=Decimal(str(a.get("quantity", a.get("qty", 0))))),
            )
            for a in (row.get("asks") or row.get("sell") or [])
        )
        return MarketDepth(
            instrument_id=instrument_id,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(timezone.utc),
        )

    def from_place_command(self, command: PlaceOrderCommand) -> dict[str, Any]:
        body: dict[str, Any] = {
            "securityId": self.security_id(command.instrument_id),
            "transactionType": BaseWireAdapter.enum_value(command.side),
            "quantity": int(command.quantity.value),
            "orderType": BaseWireAdapter.enum_value(command.order_type),
            "productType": "INTRADAY",
            "validity": BaseWireAdapter.enum_value(command.time_in_force),
            "correlationId": str(command.correlation_id.value),
        }
        if command.price is not None:
            body["price"] = float(command.price.value)
        return body

    def to_order_id(self, native: Mapping[str, Any]) -> OrderId:
        oid = native.get("orderId") or native.get("order_id")
        if not oid and isinstance(native.get("data"), Mapping):
            oid = native["data"].get("orderId") or native["data"].get("order_id")
        if not oid:
            raise ValueError("Dhan place ack missing orderId")
        return OrderId(value=str(oid))

    def to_order_status(self, native_status: str) -> OrderStatus:
        return _STATUS.get(native_status.upper(), OrderStatus.UNKNOWN)

    def to_order(self, native: Mapping[str, Any]) -> Order:
        row = native.get("data", native) if isinstance(native.get("data"), Mapping) else native
        status = self.to_order_status(str(row.get("orderStatus", row.get("status", "PENDING"))))
        side = _SIDE.get(str(row.get("transactionType", "BUY")).upper(), OrderSide.BUY)
        otype = _OTYPE.get(str(row.get("orderType", "MARKET")).upper(), OrderType.MARKET)
        price_raw = row.get("price")
        return Order(
            order_id=OrderId(value=str(row.get("orderId") or row.get("order_id"))),
            instrument_id=InstrumentId(value=str(row.get("securityId", row.get("symbol", "")))),
            side=side,
            order_type=otype,
            quantity=Quantity(value=Decimal(str(row.get("quantity", 0)))),
            price=Price(value=Decimal(str(price_raw))) if price_raw not in (None, 0, "0") else None,
            time_in_force=TimeInForce.DAY,
            status=status if status != OrderStatus.PENDING else OrderStatus.SUBMITTED,
            correlation_id=_corr(row.get("correlationId") or row.get("orderId")),
            filled_quantity=Quantity(value=Decimal(str(row.get("filledQty", row.get("tradedQuantity", 0))))),
        )

    def to_position(self, native: Mapping[str, Any]) -> Position:
        qty = Decimal(str(native.get("netQty", native.get("quantity", 0))))
        avg = Decimal(str(native.get("avgCostPrice", native.get("averagePrice", 0))))
        pnl = Decimal(str(native.get("realizedProfit", native.get("realized_pnl", 0))))
        upnl = Decimal(str(native.get("unrealizedProfit", native.get("unrealized_pnl", 0))))
        sec = str(native.get("securityId", native.get("tradingSymbol", "")))
        return Position(
            instrument_id=InstrumentId(value=sec),
            quantity=Quantity(value=qty),
            avg_price=Price(value=avg),
            realized_pnl=Money(amount=pnl, currency="INR"),
            unrealized_pnl=Money(amount=upnl, currency="INR"),
        )

    def to_account(self, native: Mapping[str, Any]) -> Account:
        row = native.get("data", native) if isinstance(native.get("data"), Mapping) else native
        avail = row.get("availabelBalance", row.get("availableBalance", row.get("sodLimit", 0)))
        cash = Money(amount=Decimal(str(avail)), currency="INR")
        return Account(
            account_id=AccountId(value="dhan"),
            balance=cash,
            margin=Money(amount=Decimal(str(row.get("utilizedMargin", 0))), currency="INR"),
            equity=cash,
        )
