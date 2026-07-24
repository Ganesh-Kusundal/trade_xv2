"""Upstox native dict ↔ domain types."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping
from uuid import UUID, uuid5, NAMESPACE_URL

from domain.commands import PlaceOrderCommand
from domain.entities import Account, DepthLevel, MarketDepth, Order, Position, Quote
from domain.enums import OrderSide, OrderStatus, OrderType, ProductType, TimeInForce
from domain.value_objects import (
    AccountId,
    CorrelationId,
    InstrumentId,
    Money,
    OrderId,
    Price,
    Quantity,
)
from plugins.brokers.common.instruments import InMemoryInstrumentResolver
from plugins.brokers.common.quote_normalize import normalize_quote
from plugins.brokers.common.wire import BaseWireAdapter
from shared.errors import MappingError

_UPSTOX_SEGMENT: dict[str, str] = {
    "NSE": "NSE_EQ",
    "NFO": "NSE_FO",
    "BFO": "BSE_FO",
    "MCX": "MCX_FO",
    "BSE": "BSE_EQ",
    "CDS": "NCD_FO",
    "BCD": "BCD_FO",
    "IDX": "NSE_INDEX",
}

# Upstox has no distinct "MARGIN" product beyond MTF — ProductType.MARGIN is
# intentionally unmapped here and raises from_place_command() if used.
_PRODUCT_TYPE_UPSTOX: dict[ProductType, str] = {
    ProductType.INTRADAY: "I",
    ProductType.DELIVERY: "D",
    ProductType.MTF: "MTF",
    ProductType.COVER_ORDER: "CO",
}

_STATUS: dict[str, OrderStatus] = {
    "open": OrderStatus.SUBMITTED,
    "complete": OrderStatus.FILLED,
    "rejected": OrderStatus.REJECTED,
    "cancelled": OrderStatus.CANCELLED,
    "trigger pending": OrderStatus.SUBMITTED,
    "after_market_order_req_received": OrderStatus.SUBMITTED,
    "queued": OrderStatus.SUBMITTED,
    "pending": OrderStatus.PENDING,
    "expired": OrderStatus.CANCELLED,
}


def _corr(raw: object) -> CorrelationId:
    text = str(raw or "")
    try:
        return CorrelationId(value=UUID(text))
    except (ValueError, AttributeError):
        return CorrelationId(value=uuid5(NAMESPACE_URL, text or "upstox-unknown"))


class UpstoxWire:
    def __init__(self) -> None:
        self._resolver = InMemoryInstrumentResolver()

    def get_segment(self, instrument_id: InstrumentId) -> str:
        # The spot index itself (not a derivative on an index) resolves via the
        # shared registry; everything else uses the exchange→segment map.
        from plugins.brokers.common.index_map import is_pure_index, upstox_index_segment

        if is_pure_index(instrument_id):
            seg = upstox_index_segment(instrument_id.underlying)
            if seg:
                return seg
        exchange = instrument_id.value.split(":")[0] if ":" in instrument_id.value else "NSE"
        return _UPSTOX_SEGMENT.get(exchange, "NSE_EQ")

    def instrument_key(self, instrument_id: InstrumentId) -> str:
        # Only the spot index itself resolves from the shared registry — a
        # derivative on an index (NFO:NIFTY:…) must hit the instrument master.
        from plugins.brokers.common.index_map import index_upstox_key, is_pure_index

        if is_pure_index(instrument_id):
            key = index_upstox_key(instrument_id.underlying)
            if key is not None:
                return key
        return self._resolver.resolve_ref(instrument_id).require("instrument_key")

    def register_key(
        self,
        instrument_id: InstrumentId,
        key: str,
        *,
        symbol: str | None = None,
        exchange: str | None = None,
        instrument_type: str | None = None,
        underlying: str | None = None,
        expiry: str | None = None,
        strike: Any | None = None,
        option_type: str | None = None,
        canonical_symbol: str | None = None,
    ) -> None:
        self._resolver.register(
            instrument_id,
            {"instrument_key": key},
            symbol=symbol,
            exchange=exchange,
            instrument_type=instrument_type,
            underlying=underlying,
            expiry=expiry,
            strike=strike,
            option_type=option_type,
            canonical_symbol=canonical_symbol,
        )

    def register_bulk(self, rows: list[dict], *, source: str = "bulk") -> None:
        """Atomic bulk load — see InMemoryInstrumentResolver.load_from_rows."""
        self._resolver.load_from_rows(rows, source=source)

    def _canon_iid(self, raw_id: str) -> InstrumentId:
        """Resolve raw Upstox instrument_key to canonical EXCHANGE:SYMBOL InstrumentId.

        Never guesses — a miss means the instrument master isn't loaded or the
        id is unknown, and callers must see that instead of a fabricated symbol.
        """
        canonical = self._resolver.reverse("instrument_key", raw_id)
        if canonical is not None:
            return canonical
        raise MappingError(f"no canonical instrument for Upstox instrument_key={raw_id!r}")

    def response_key(self, instrument_id: InstrumentId) -> str:
        """Upstox quote/ltp responses are keyed by ``EXCHANGE:SYMBOL`` (colon),

        not by the ``instrument_key`` (``EXCHANGE|ISIN``). Derive it from the
        canonical InstrumentId so lookups hit the right row.
        """
        exchange = instrument_id.value.split(":")[0] if ":" in instrument_id.value else "NSE"
        symbol = instrument_id.value.split(":", 1)[1] if ":" in instrument_id.value else instrument_id.value
        return f"{_UPSTOX_SEGMENT.get(exchange, 'NSE_EQ')}:{symbol}"

    def to_quote(self, native: Mapping[str, Any], *, instrument_id: InstrumentId) -> Quote:
        key = self.response_key(instrument_id)
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
        key = self.response_key(instrument_id)
        data = native.get("data", native)
        row = data[key] if isinstance(data, Mapping) and key in data else data
        return Price(value=Decimal(str(row.get("last_price", row.get("ltp", 0)))))

    def to_depth(self, native: Mapping[str, Any], *, instrument_id: InstrumentId) -> MarketDepth:
        key = self.response_key(instrument_id)
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
        disclosed = getattr(command, "disclosed_quantity", None)
        market_protection = getattr(command, "market_protection", None)
        if command.product_type is None:
            product = "I"
        elif command.product_type in _PRODUCT_TYPE_UPSTOX:
            product = _PRODUCT_TYPE_UPSTOX[command.product_type]
        else:
            raise ValueError(f"Upstox does not support product_type {command.product_type!r}")
        body: dict[str, Any] = {
            "instrument_token": self.instrument_key(command.instrument_id),
            "transaction_type": BaseWireAdapter.enum_value(command.side),
            "quantity": int(command.quantity.value),
            "order_type": BaseWireAdapter.enum_value(command.order_type),
            "product": product,
            "validity": BaseWireAdapter.enum_value(command.time_in_force),
            "disclosed_quantity": int(disclosed.value) if disclosed is not None else 0,
            "market_protection": int(market_protection) if market_protection is not None else -1,
            "tag": str(command.correlation_id.value),
        }
        if command.price is not None:
            body["price"] = float(command.price.value)
        if command.trigger_price is not None:
            body["trigger_price"] = float(command.trigger_price.value)
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
            instrument_id=self._canon_iid(str(row.get("instrument_token", row.get("tradingsymbol", "")))),
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
            instrument_id=self._canon_iid(key),
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
