"""Upstox native dict ↔ domain types."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping
from uuid import UUID, uuid5, NAMESPACE_URL

from domain.commands import PlaceOrderCommand
from domain.entities import Account, DepthLevel, MarketDepth, Order, Position, Quote
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

_INSTRUMENT_KEYS: dict[str, str] = {
    "NSE:RELIANCE": "NSE_EQ:RELIANCE",
}

_STATUS: dict[str, OrderStatus] = {
    "open": OrderStatus.SUBMITTED,
    "complete": OrderStatus.FILLED,
    "rejected": OrderStatus.REJECTED,
    "cancelled": OrderStatus.CANCELLED,
    "trigger pending": OrderStatus.SUBMITTED,
}


def _corr(raw: object) -> CorrelationId:
    text = str(raw or "")
    try:
        return CorrelationId(value=UUID(text))
    except (ValueError, AttributeError):
        return CorrelationId(value=uuid5(NAMESPACE_URL, text or "upstox-unknown"))


class UpstoxWire:
    def instrument_key(self, instrument_id: InstrumentId) -> str:
        if instrument_id.value in _INSTRUMENT_KEYS:
            return _INSTRUMENT_KEYS[instrument_id.value]
        if ":" in instrument_id.value and instrument_id.value.startswith("NSE_"):
            return instrument_id.value
        raise KeyError(f"no Upstox instrument_key for {instrument_id.value}")

    def register_key(self, instrument_id: InstrumentId, key: str) -> None:
        _INSTRUMENT_KEYS[instrument_id.value] = key

    def to_quote(self, native: Mapping[str, Any], *, instrument_id: InstrumentId) -> Quote:
        key = self.instrument_key(instrument_id)
        data = native.get("data", native)
        row = data[key] if isinstance(data, Mapping) and key in data else data
        depth = row.get("depth", {}) if isinstance(row, Mapping) else {}
        buys = depth.get("buy") or [{"price": row.get("last_price", 0), "quantity": 0}]
        sells = depth.get("sell") or [{"price": row.get("last_price", 0), "quantity": 0}]
        return normalize_quote(
            {
                "bid": buys[0]["price"],
                "ask": sells[0]["price"],
                "bid_size": buys[0].get("quantity", 0),
                "ask_size": sells[0].get("quantity", 0),
                "timestamp": row.get("timestamp"),
            },
            instrument_id=instrument_id,
        )

    def to_ltp(self, native: Mapping[str, Any], *, instrument_id: InstrumentId) -> Price:
        key = self.instrument_key(instrument_id)
        data = native.get("data", native)
        row = data[key] if isinstance(data, Mapping) and key in data else data
        return Price(value=Decimal(str(row.get("last_price", row.get("ltp", 0)))))

    def to_depth(self, native: Mapping[str, Any], *, instrument_id: InstrumentId) -> MarketDepth:
        key = self.instrument_key(instrument_id)
        data = native.get("data", native)
        row = data[key] if isinstance(data, Mapping) and key in data else data
        depth = row.get("depth", row)
        bids = tuple(
            DepthLevel(
                price=Price(value=Decimal(str(b["price"]))),
                quantity=Quantity(value=Decimal(str(b.get("quantity", 0)))),
            )
            for b in (depth.get("buy") or [])
        )
        asks = tuple(
            DepthLevel(
                price=Price(value=Decimal(str(a["price"]))),
                quantity=Quantity(value=Decimal(str(a.get("quantity", 0)))),
            )
            for a in (depth.get("sell") or [])
        )
        return MarketDepth(
            instrument_id=instrument_id,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(timezone.utc),
        )

    def from_place_command(self, command: PlaceOrderCommand) -> dict[str, Any]:
        body: dict[str, Any] = {
            "instrument_token": self.instrument_key(command.instrument_id),
            "transaction_type": BaseWireAdapter.enum_value(command.side),
            "quantity": int(command.quantity.value),
            "order_type": BaseWireAdapter.enum_value(command.order_type),
            "product": "I",
            "validity": BaseWireAdapter.enum_value(command.time_in_force),
            "tag": str(command.correlation_id.value),
        }
        if command.price is not None:
            body["price"] = float(command.price.value)
        return body

    def to_order_id(self, native: Mapping[str, Any]) -> OrderId:
        data = native.get("data", native)
        oid = data.get("order_id") if isinstance(data, Mapping) else None
        if not oid:
            raise ValueError("Upstox place ack missing order_id")
        return OrderId(value=str(oid))

    def to_order_status(self, native_status: str) -> OrderStatus:
        return _STATUS.get(native_status.lower(), OrderStatus.UNKNOWN)

    def to_order(self, native: Mapping[str, Any]) -> Order:
        row = native.get("data", native) if isinstance(native.get("data"), Mapping) else native
        status = self.to_order_status(str(row.get("status", "open")))
        side = OrderSide.BUY if str(row.get("transaction_type", "BUY")).upper() == "BUY" else OrderSide.SELL
        otype = OrderType.LIMIT if str(row.get("order_type", "")).upper() == "LIMIT" else OrderType.MARKET
        price_raw = row.get("price")
        return Order(
            order_id=OrderId(value=str(row.get("order_id"))),
            instrument_id=InstrumentId(value=str(row.get("instrument_token", row.get("tradingsymbol", "")))),
            side=side,
            order_type=otype,
            quantity=Quantity(value=Decimal(str(row.get("quantity", 0)))),
            price=Price(value=Decimal(str(price_raw))) if price_raw not in (None, 0, "0") else None,
            time_in_force=TimeInForce.DAY,
            status=status if status != OrderStatus.PENDING else OrderStatus.SUBMITTED,
            correlation_id=_corr(row.get("tag") or row.get("order_id")),
            filled_quantity=Quantity(value=Decimal(str(row.get("filled_quantity", 0)))),
        )

    def to_position(self, native: Mapping[str, Any]) -> Position:
        qty = Decimal(str(native.get("quantity", native.get("day_buy_quantity", 0))))
        avg = Decimal(str(native.get("average_price", 0)))
        pnl = Decimal(str(native.get("realised", native.get("realized_pnl", 0))))
        upnl = Decimal(str(native.get("unrealised", native.get("unrealized_pnl", 0))))
        key = str(native.get("instrument_token", native.get("tradingsymbol", "")))
        return Position(
            instrument_id=InstrumentId(value=key),
            quantity=Quantity(value=qty),
            avg_price=Price(value=avg),
            realized_pnl=Money(amount=pnl, currency="INR"),
            unrealized_pnl=Money(amount=upnl, currency="INR"),
        )

    def to_account(self, native: Mapping[str, Any]) -> Account:
        data = native.get("data", native) if isinstance(native.get("data"), Mapping) else native
        equity = data.get("equity", data) if isinstance(data, Mapping) else {}
        avail = equity.get("available_margin", equity.get("available_balance", 0)) if isinstance(equity, Mapping) else 0
        cash = Money(amount=Decimal(str(avail)), currency="INR")
        return Account(
            account_id=AccountId(value="upstox"),
            balance=cash,
            margin=Money(amount=Decimal("0"), currency="INR"),
            equity=cash,
        )
