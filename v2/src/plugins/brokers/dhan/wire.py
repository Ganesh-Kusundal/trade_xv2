"""Dhan native dict ↔ domain types."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping
from uuid import UUID, uuid5, NAMESPACE_URL

from domain.commands import PlaceOrderCommand
from domain.entities import Account, MarketDepth, Order, Position, Quote
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


def _corr(raw: object) -> CorrelationId:
    text = str(raw or "")
    try:
        return CorrelationId(value=UUID(text))
    except (ValueError, AttributeError):
        return CorrelationId(value=uuid5(NAMESPACE_URL, text or "dhan-unknown"))

_STATUS: dict[str, OrderStatus] = {
    "TRANSIT": OrderStatus.SUBMITTED,
    "PENDING": OrderStatus.PENDING,
    "TRADED": OrderStatus.FILLED,
    "PART_TRADED": OrderStatus.PARTIALLY_FILLED,
    "REJECTED": OrderStatus.REJECTED,
    "CANCELLED": OrderStatus.CANCELLED,
    "TRIGGER_PENDING": OrderStatus.SUBMITTED,
    "AFTER_MARKET_ORDER": OrderStatus.SUBMITTED,
    "AMO_CANCELLED": OrderStatus.CANCELLED,
    "OPEN_PENDING": OrderStatus.SUBMITTED,
}

_SIDE: dict[str, OrderSide] = {"BUY": OrderSide.BUY, "SELL": OrderSide.SELL}
_OTYPE: dict[str, OrderType] = {
    "MARKET": OrderType.MARKET,
    "LIMIT": OrderType.LIMIT,
    "STOP_LOSS": OrderType.STOP,
    "STOP_LOSS_MARKET": OrderType.STOP,
}

_PRODUCT_TYPE_DHAN: dict[ProductType, str] = {
    ProductType.INTRADAY: "INTRADAY",
    ProductType.DELIVERY: "CNC",
    ProductType.MARGIN: "MARGIN",
    ProductType.MTF: "MTF",
    ProductType.COVER_ORDER: "CO",
}

_DHAN_SEGMENT: dict[str, str] = {
    "NSE": "NSE_EQ",
    "NFO": "NSE_FNO",
    "BFO": "BSE_FNO",
    "MCX": "MCX_COMM",
    "NSE_COMM": "NSE_COMM",
    "BSE": "BSE_EQ",
    "CDS": "NSE_CURRENCY",
    "BCD": "BSE_CURRENCY",
    "IDX": "IDX_I",
    "INDEX": "IDX_I",
}


class DhanWire:
    def __init__(self, client_id: str | None = None) -> None:
        self._resolver = InMemoryInstrumentResolver()
        self.client_id = client_id or ""

    def get_segment(self, instrument_id: InstrumentId) -> str:
        # The spot index itself (not a derivative on an index) resolves via the
        # shared registry; everything else uses the exchange→segment map.
        from plugins.brokers.common.index_map import dhan_index_segment, is_pure_index

        if is_pure_index(instrument_id):
            seg = dhan_index_segment(instrument_id.underlying)
            if seg:
                return seg
        exchange = instrument_id.value.split(":")[0] if ":" in instrument_id.value else "NSE"
        return _DHAN_SEGMENT.get(exchange, "NSE_EQ")

    def get_instrument_type(self, instrument_id: InstrumentId) -> str:
        """Return the Dhan instrument type string for history API payloads."""
        exchange = instrument_id.exchange
        if exchange in ("INDEX", "IDX"):
            return "EQUITY"  # Dhan uses "EQUITY" for index history
        if exchange in ("NFO", "BFO"):
            return "FUTIDX" if instrument_id.right == "FUT" else "OPTIDX"
        if exchange in ("MCX", "NSE_COMM"):
            return "FUTCOM"
        return "EQUITY"

    def security_id(self, instrument_id: InstrumentId) -> str:
        # Only the spot index itself resolves from the shared registry — a
        # derivative on an index (NFO:NIFTY:…) must hit the instrument master.
        from plugins.brokers.common.index_map import get_index_entry, is_pure_index

        if is_pure_index(instrument_id):
            entry = get_index_entry(instrument_id.underlying)
            if entry is not None and entry.dhan_security_id is not None:
                return entry.dhan_security_id
        return self._resolver.resolve_ref(instrument_id).require("security_id")

    def register_security(
        self,
        instrument_id: InstrumentId,
        security_id: str,
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
            {"security_id": security_id},
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
        """Resolve raw Dhan securityId to canonical EXCHANGE:SYMBOL InstrumentId.

        Never guesses — a miss means the instrument master isn't loaded or the
        id is unknown, and callers must see that instead of a fabricated symbol.
        """
        canonical = self._resolver.reverse("security_id", raw_id)
        if canonical is not None:
            return canonical
        raise MappingError(f"no canonical instrument for Dhan securityId={raw_id!r}")

    def to_quote(self, native: Mapping[str, Any], *, instrument_id: InstrumentId) -> Quote:
        """Map Dhan /marketfeed/quote response to domain Quote.

        Dhan quote response structure:
          last_price, ohlc{open,high,low,close}, volume, net_change, oi,
          depth{buy:[{price,quantity,...}], sell:[{price,quantity,...}]}
        """
        raw = native.get("data", native)
        sec = self.security_id(instrument_id)
        row = raw[sec] if isinstance(raw, Mapping) and sec in raw else raw
        ohlc = row.get("ohlc", {}) or {}
        depth = row.get("depth", {}) or {}
        buys = depth.get("buy") or []
        sells = depth.get("sell") or []
        bid = Decimal(str(buys[0]["price"])) if buys else Decimal("0")
        ask = Decimal(str(sells[0]["price"])) if sells else Decimal("0")
        bid_size = int(buys[0].get("quantity", 0)) if buys else 0
        ask_size = int(sells[0].get("quantity", 0)) if sells else 0
        return normalize_quote(
            {
                "ltp": row.get("last_price", 0),
                "open": ohlc.get("open", 0),
                "high": ohlc.get("high", 0),
                "low": ohlc.get("low", 0),
                "close": ohlc.get("close", 0),
                "bid": bid,
                "ask": ask,
                "bid_size": bid_size,
                "ask_size": ask_size,
                "volume": row.get("volume", 0),
                "change": row.get("net_change", 0),
                "oi": row.get("oi", 0),
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
        """Map Dhan /marketfeed/quote response depth arrays to domain MarketDepth.

        The depth is nested under ``depth: {buy: [...], sell: [...]}`` in the
        quote response — not a separate endpoint.
        """
        from domain.entities import DepthLevel

        raw = native.get("data", native)
        sec = self.security_id(instrument_id)
        row = raw[sec] if isinstance(raw, Mapping) and sec in raw else raw
        depth = row.get("depth", row) if isinstance(row, Mapping) else {}
        bids = tuple(
            DepthLevel(
                price=Price(value=Decimal(str(b["price"]))),
                quantity=Quantity(value=Decimal(str(b.get("quantity", 0)))),
            )
            for b in (depth.get("buy") or [])[:5]
        )
        asks = tuple(
            DepthLevel(
                price=Price(value=Decimal(str(a["price"]))),
                quantity=Quantity(value=Decimal(str(a.get("quantity", 0)))),
            )
            for a in (depth.get("sell") or [])[:5]
        )
        return MarketDepth(
            instrument_id=instrument_id,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(timezone.utc),
        )

    def from_place_command(self, command: PlaceOrderCommand) -> dict[str, Any]:
        if command.product_type is None:
            product_type = "INTRADAY"
        elif command.product_type in _PRODUCT_TYPE_DHAN:
            product_type = _PRODUCT_TYPE_DHAN[command.product_type]
        else:
            raise ValueError(f"Dhan does not support product_type {command.product_type!r}")
        body: dict[str, Any] = {
            "dhanClientId": self.client_id,
            "exchangeSegment": self.get_segment(command.instrument_id),
            "securityId": self.security_id(command.instrument_id),
            "transactionType": BaseWireAdapter.enum_value(command.side),
            "quantity": int(command.quantity.value),
            "orderType": BaseWireAdapter.enum_value(command.order_type),
            "productType": product_type,
            "validity": BaseWireAdapter.enum_value(command.time_in_force),
            "correlationId": str(command.correlation_id.value),
        }
        if command.price is not None:
            body["price"] = float(command.price.value)
        if command.trigger_price is not None:
            body["triggerPrice"] = float(command.trigger_price.value)
        if command.disclosed_quantity is not None and command.disclosed_quantity.value > 0:
            body["disclosedQuantity"] = int(command.disclosed_quantity.value)
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
            instrument_id=self._canon_iid(str(row.get("securityId", row.get("symbol", "")))),
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
            instrument_id=self._canon_iid(sec),
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
