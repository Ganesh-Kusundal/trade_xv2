"""Canonical domain dataclasses — value objects returned by broker adapters.

These are the single source of truth for every domain model that flows
through the system after the adapter boundary. DataFrames are used for
market data (OHLCV, quotes, option chain, depth); these dataclasses are
used for orders, positions, holdings, and trades.

Usage::

    from domain.entities import Order, Position

    order = Order(
        order_id="O-123",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        price=Decimal("2500"),
    )
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from domain.constants import DEFAULT_TICK_SIZE
from domain.types import (
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)
from domain.status_mapper import StatusMapperRegistry  # P2-Phase 2: Import for status normalization


class FieldMapping(Protocol):
    """Broker-specific field name mapping for Order parsing.
    
    Implement this protocol to define how broker-specific API responses
    map to canonical Order fields. Each broker adapter should provide
    its own implementation.
    
    Example::
    
        from domain.field_mapping import DefaultFieldMapping
        mapping = DefaultFieldMapping()
    """
    
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


@dataclass(slots=True, frozen=True)
class Order:
    """Canonical order — returned by every broker adapter."""

    order_id: str
    symbol: str
    exchange: str
    side: Side
    order_type: OrderType
    quantity: int
    filled_quantity: int = 0
    price: Decimal = Decimal("0")
    trigger_price: Decimal = Decimal("0")
    status: OrderStatus = OrderStatus.OPEN
    timestamp: datetime | None = None
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY
    avg_price: Decimal = Decimal("0")
    reject_reason: str = ""
    correlation_id: str | None = None

    @property
    def average_price(self) -> Decimal:
        """Alias for avg_price — Dhan and some brokers use this name."""
        return self.avg_price

    @property
    def remaining_quantity(self) -> int:
        return max(self.quantity - self.filled_quantity, 0)

    @property
    def is_complete(self) -> bool:
        return self.status.is_terminal

    def with_status(self, status: OrderStatus) -> Order:
        """Return a new Order with the given status."""
        return replace(self, status=status)

    def with_fill(self, filled_quantity: int, avg_price: Decimal) -> Order:
        """Return a new Order with updated fill quantity and average fill price."""
        return replace(self, filled_quantity=filled_quantity, avg_price=avg_price)

    @classmethod
    def from_broker_dict(
        cls,
        d: dict,
        field_mapping: FieldMapping | None = None,
        exchange_resolver: Callable[[str], Any] | None = None,
    ) -> Order:
        """Construct a canonical Order from a broker-specific dict.
        
        Args:
            d: Broker-specific order dict
            field_mapping: Broker-specific field name mapping (optional)
            exchange_resolver: Optional function to convert exchange string to Exchange enum
        
        If field_mapping is None, uses default Dhan-compatible mapping for backward compatibility.
        """
        from domain.field_mapping import DefaultFieldMapping
        
        mapping = field_mapping or DefaultFieldMapping()
        
        order_id = mapping.map_order_id(d)
        symbol = mapping.map_symbol(d)
        raw_exchange = mapping.map_exchange(d)
        exchange = exchange_resolver(raw_exchange) if exchange_resolver else raw_exchange
        
        side_str = mapping.map_side(d)
        side = Side.BUY if side_str == "BUY" else Side.SELL
        
        ot_str = mapping.map_order_type(d)
        try:
            order_type = OrderType(ot_str)
        except ValueError:
            order_type = OrderType.MARKET
        
        status_str = mapping.map_status(d)
        # P2-Phase 2: Use StatusMapperRegistry directly (fixed Clean Architecture violation)
        status = StatusMapperRegistry.normalize(status_str)
        
        def _opt_dec(v: str | None) -> Decimal | None:
            if v in (None, ""):
                return None
            return Decimal(v)
        
        return cls(
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            order_type=order_type,
            quantity=mapping.map_quantity(d),
            filled_quantity=mapping.map_filled_quantity(d),
            price=_opt_dec(mapping.map_price(d)) or Decimal("0"),
            avg_price=_opt_dec(mapping.map_avg_price(d)) or Decimal("0"),
            status=status,
            reject_reason=mapping.map_reject_reason(d),
        )


@dataclass(slots=True, frozen=True)
class Position:
    """Canonical position — returned by every broker adapter."""

    symbol: str
    exchange: str
    quantity: int = 0
    avg_price: Decimal = Decimal("0")
    ltp: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    product_type: ProductType = ProductType.INTRADAY
    correlation_id: str | None = None

    @property
    def pnl(self) -> Decimal:
        if self.quantity > 0:
            return Decimal(str(self.quantity)) * (self.ltp - self.avg_price)
        elif self.quantity < 0:
            return Decimal(str(abs(self.quantity))) * (self.avg_price - self.ltp)
        return Decimal("0")

    def with_ltp(self, ltp: Decimal) -> Position:
        """Return a new Position with the last traded price updated."""
        unrealized = (
            Decimal(str(self.quantity)) * (ltp - self.avg_price)
            if self.quantity != 0
            else Decimal("0")
        )
        return replace(self, ltp=ltp, unrealized_pnl=unrealized)

    def with_fill(self, quantity: int, price: Decimal) -> Position:
        """Return a new Position after applying a signed fill."""
        old_qty = self.quantity
        old_avg = self.avg_price
        delta = quantity
        new_qty = old_qty + delta

        if old_qty == 0:
            new_avg = price
            new_realized = self.realized_pnl
        elif (old_qty > 0 and delta < 0) or (old_qty < 0 and delta > 0):
            closed = min(abs(old_qty), abs(delta))
            pnl_factor = Decimal("1") if old_qty > 0 else Decimal("-1")
            new_realized = self.realized_pnl + Decimal(str(closed)) * (price - old_avg) * pnl_factor
            if new_qty == 0:
                new_avg = Decimal("0")
            elif abs(delta) > abs(old_qty):
                new_avg = price
            else:
                new_avg = old_avg
        else:
            new_realized = self.realized_pnl
            new_avg = (Decimal(str(old_qty)) * old_avg + Decimal(str(delta)) * price) / Decimal(str(new_qty))

        unrealized = (
            Decimal(str(new_qty)) * (price - new_avg)
            if new_qty != 0
            else Decimal("0")
        )
        return replace(
            self,
            quantity=new_qty,
            avg_price=new_avg,
            ltp=price,
            unrealized_pnl=unrealized,
            realized_pnl=new_realized,
        )


@dataclass(slots=True, frozen=True)
class Holding:
    """Canonical holding — returned by every broker adapter."""

    symbol: str
    exchange: str
    quantity: int = 0
    available_quantity: int = 0
    avg_price: Decimal = Decimal("0")
    ltp: Decimal = Decimal("0")
    pnl: Decimal = Decimal("0")
    correlation_id: str | None = None


@dataclass(slots=True, frozen=True)
class Trade:
    """Canonical trade — returned by every broker adapter."""

    trade_id: str
    order_id: str
    symbol: str
    exchange: str
    side: Side
    quantity: int
    price: Decimal = Decimal("0")
    trade_value: Decimal = Decimal("0")
    timestamp: datetime | None = None
    product_type: ProductType = ProductType.INTRADAY
    correlation_id: str | None = None

    @property
    def value(self) -> Decimal:
        if self.trade_value > 0:
            return self.trade_value
        return self.price * Decimal(str(self.quantity))


@dataclass(slots=True, frozen=False)
class FundLimits:
    """Canonical fund limits — returned by every broker adapter."""

    available_balance: Decimal = Decimal("0")
    used_margin: Decimal = Decimal("0")
    total_margin: Decimal = Decimal("0")

    def has_sufficient(self, required: Decimal) -> bool:
        return self.available_balance >= required


@dataclass(slots=True, frozen=False)
class OrderResponse:
    """Canonical response from any order write operation.

    Used for ``place_order``, ``modify_order``, ``cancel_order``,
    ``place_slice_order`` and the corresponding delete operations. The
    previous design had each adapter returning a heterogeneous mix of
    ``bool``, ``dict`` and ``(broker_id, broker_msg)`` tuples, which
    forced the OMS to special-case success detection for each broker.

    Invariants
    ----------
    * ``success`` MUST be ``True`` when the broker confirmed the action.
      ``"pending"`` or ``"transit"`` are NOT success — the call must be
      retried. Callers that need a tri-state can use :attr:`status` and
      :class:`OrderStatus`.
    * ``order_id`` is the **broker's** id when the broker returned one.
      For modify/cancel, the original id of the affected order.
    * ``broker_order_id`` is an alias for ``order_id`` kept for callers
      that already used the older name; new code should use ``order_id``.
    * ``error_code`` is the canonical :class:`BrokerErrorCode` (string)
      and ``http_status`` is the wire status the broker returned; both
      are diagnostic only and must not be parsed for business logic.
    * ``raw_payload`` is the broker's raw response body, kept verbatim
      for forensic / audit / reconciliation. It is **not** part of the
      contract — schema differences across brokers are expected.
    """

    success: bool
    order_id: str = ""
    message: str = ""
    status: OrderStatus = OrderStatus.OPEN
    broker_order_id: str = ""
    error_code: str = ""
    http_status: int | None = None
    raw_payload: dict[str, Any] | None = None
    latency_ms: float = 0.0

    @classmethod
    def ok(
        cls,
        order_id: str = "",
        message: str = "Success",
        status: OrderStatus = OrderStatus.OPEN,
        raw_payload: dict[str, Any] | None = None,
        http_status: int | None = 200,
        latency_ms: float = 0.0,
    ) -> OrderResponse:
        """Construct a successful response.

        ``broker_order_id`` defaults to ``order_id`` so callers that only
        pass one argument do not have to duplicate it.
        """
        return cls(
            success=True,
            order_id=order_id,
            broker_order_id=order_id,
            message=message,
            status=status,
            http_status=http_status,
            raw_payload=raw_payload,
            latency_ms=latency_ms,
        )

    @classmethod
    def fail(
        cls,
        message: str,
        error_code: str = "",
        http_status: int | None = None,
        raw_payload: dict[str, Any] | None = None,
        latency_ms: float = 0.0,
        status: OrderStatus = OrderStatus.REJECTED,
    ) -> OrderResponse:
        """Construct a failed response.

        ``error_code`` SHOULD be a :class:`BrokerErrorCode` string when
        the broker returned a recognisable error; otherwise the broker's
        own error code (e.g. ``"DH-906"``) is acceptable.
        """
        return cls(
            success=False,
            message=message,
            status=status,
            error_code=error_code,
            http_status=http_status,
            raw_payload=raw_payload,
            latency_ms=latency_ms,
        )

    def with_broker_id(self, broker_id: str) -> OrderResponse:
        """Return a copy with ``broker_order_id`` populated.

        Useful when the response is created before the broker returns
        its native id (e.g. inside a retry wrapper).
        """
        return _replace(self, broker_order_id=broker_id)


# Sentinel for the ``_replace`` helper above; we cannot use
# ``dataclasses.replace`` as a default because ``OrderResponse`` has
# ``frozen=False`` and we want to remain compatible with that.
def _replace(resp: OrderResponse, **changes: Any) -> OrderResponse:
    from dataclasses import replace as _dc_replace
    return _dc_replace(resp, **changes)


@dataclass(slots=True, frozen=True)
class Balance:
    """Canonical account balance — returned by every broker adapter."""

    available_balance: Decimal = Decimal("0")
    used_margin: Decimal = Decimal("0")
    total_margin: Decimal = Decimal("0")
    sod_limit: Decimal = Decimal("0")
    collateral_amount: Decimal = Decimal("0")
    utilized_amount: Decimal = Decimal("0")
    withdrawable_balance: Decimal = Decimal("0")


@dataclass(slots=True, frozen=True)
class DepthLevel:
    """Single price level in market depth."""

    price: Decimal = Decimal("0")
    quantity: int = 0
    orders: int = 0


@dataclass(slots=True, frozen=False)
class MarketDepth:
    """Canonical market depth — bid/ask ladder."""

    symbol: str = ""
    bids: list[DepthLevel] | None = None
    asks: list[DepthLevel] | None = None
    timestamp: datetime | None = None
    depth_type: str = "DEPTH_5"  # DEPTH_5, DEPTH_20, DEPTH_200

    def __post_init__(self) -> None:
        if self.bids is None:
            self.bids = []
        if self.asks is None:
            self.asks = []


@dataclass(slots=True, frozen=True)
class Quote:
    """Canonical quote snapshot — returned by every broker adapter."""

    symbol: str
    ltp: Decimal = Decimal("0")
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: int = 0
    change: Decimal = Decimal("0")
    bid: Decimal | None = None
    ask: Decimal | None = None
    timestamp: datetime | None = None


@dataclass(slots=True, frozen=False)
class Instrument:
    """Canonical instrument master record — returned by broker adapters.

    This is the broker-adapter-level instrument, populated by Dhan/Upstox
    instrument loaders. Distinct from:

    * ``brokers.common.core.instruments.Instrument`` — the trading-engine
      instrument used by the strategy layer (has ``asset_class``,
      ``broker_identifier``).
    * ``brokers.dhan.domain.Instrument`` — Dhan-specific instrument with
      typed ``Exchange`` and ``InstrumentType`` enums.
    """

    symbol: str
    exchange: str
    security_id: str
    instrument_type: str
    lot_size: int = 1
    tick_size: Decimal = DEFAULT_TICK_SIZE
    name: str | None = None
    option_type: str | None = None
    strike_price: Decimal | None = None
    expiry: str | None = None
    underlying: str | None = None
    canonical_symbol: str | None = None


@dataclass(slots=True, frozen=False)
class OptionContract:
    """Option chain contract with greeks and market data."""

    strike: Decimal = Decimal("0")
    expiry: str = ""
    instrument_type: str = "OPTION"
    exchange: str = "NFO"
    lot_size: int = 0
    call_ltp: Decimal | None = None
    call_bid: Decimal | None = None
    call_ask: Decimal | None = None
    call_iv: Decimal | None = None
    call_oi: int | None = None
    call_volume: int | None = None
    put_ltp: Decimal | None = None
    put_bid: Decimal | None = None
    put_ask: Decimal | None = None
    put_iv: Decimal | None = None
    put_oi: int | None = None
    put_volume: int | None = None


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True, frozen=True)
class OptionLeg:
    """Single CE or PE leg within an option chain strike row."""

    ltp: Decimal | None = None
    oi: int | None = None
    volume: int | None = None
    iv: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    symbol: str | None = None
    instrument_key: str | None = None
    trading_symbol: str | None = None
    greeks: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> OptionLeg:
        if not isinstance(data, dict):
            return cls()
        greeks = data.get("greeks")
        return cls(
            ltp=_decimal_or_none(data.get("ltp")),
            oi=_int_or_none(data.get("oi")),
            volume=_int_or_none(data.get("volume")),
            iv=_decimal_or_none(data.get("iv")),
            bid=_decimal_or_none(data.get("bid")),
            ask=_decimal_or_none(data.get("ask")),
            symbol=data.get("symbol"),
            instrument_key=data.get("instrument_key") or data.get("security_id"),
            trading_symbol=data.get("trading_symbol") or data.get("tradingSymbol"),
            greeks=dict(greeks) if isinstance(greeks, dict) else None,
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ltp": self.ltp,
            "oi": self.oi,
            "volume": self.volume,
            "iv": self.iv,
            "bid": self.bid,
            "ask": self.ask,
            "symbol": self.symbol,
            "instrument_key": self.instrument_key,
            "trading_symbol": self.trading_symbol,
        }
        if self.greeks:
            out["greeks"] = self.greeks
        return out


@dataclass(slots=True, frozen=True)
class OptionStrike:
    """One strike row with call and put legs."""

    strike: Decimal
    call: OptionLeg = field(default_factory=OptionLeg)
    put: OptionLeg = field(default_factory=OptionLeg)

    @classmethod
    def from_dict(cls, data: dict) -> OptionStrike:
        strike_val = data.get("strike") or data.get("strikePrice")
        strike = _decimal_or_none(strike_val) or Decimal("0")
        call_raw = data.get("call") or data.get("CE") or {}
        put_raw = data.get("put") or data.get("PE") or {}
        return cls(
            strike=strike,
            call=OptionLeg.from_dict(call_raw if isinstance(call_raw, dict) else {}),
            put=OptionLeg.from_dict(put_raw if isinstance(put_raw, dict) else {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "strike": self.strike,
            "call": self.call.to_dict(),
            "put": self.put.to_dict(),
        }


@dataclass(slots=True, frozen=True)
class OptionChain:
    """Canonical option chain returned by :class:`~brokers.common.gateway.MarketDataGateway`."""

    underlying: str
    exchange: str
    expiry: str
    strikes: tuple[OptionStrike, ...] = ()
    spot: Decimal | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> OptionChain:
        if not data:
            return cls(underlying="", exchange="", expiry="")
        strikes = tuple(
            OptionStrike.from_dict(row)
            for row in data.get("strikes", [])
            if isinstance(row, dict)
        )
        return cls(
            underlying=str(data.get("underlying", "")),
            exchange=str(data.get("exchange", "")),
            expiry=str(data.get("expiry", "")),
            strikes=strikes,
            spot=_decimal_or_none(data.get("spot")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "underlying": self.underlying,
            "exchange": self.exchange,
            "expiry": self.expiry,
            "strikes": [row.to_dict() for row in self.strikes],
            "spot": self.spot,
        }


@dataclass(slots=True, frozen=True)
class FutureContract:
    """Single futures contract within a chain."""

    symbol: str = ""
    expiry: str = ""
    ltp: Decimal | None = None
    oi: int | None = None
    lot_size: int = 1
    underlying: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> FutureContract:
        return cls(
            symbol=str(data.get("symbol", "")),
            expiry=str(data.get("expiry", "")),
            ltp=_decimal_or_none(data.get("ltp")),
            oi=_int_or_none(data.get("oi")),
            lot_size=int(data.get("lot_size", 1) or 1),
            underlying=str(data.get("underlying", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "expiry": self.expiry,
            "ltp": self.ltp,
            "oi": self.oi,
            "lot_size": self.lot_size,
            "underlying": self.underlying,
        }


@dataclass(slots=True, frozen=True)
class FutureChain:
    """Canonical futures chain returned by :class:`~brokers.common.gateway.MarketDataGateway`."""

    underlying: str
    exchange: str
    expiries: tuple[str, ...] = ()
    contracts: tuple[FutureContract, ...] = ()

    @classmethod
    def from_dict(cls, data: dict | None) -> FutureChain:
        if not data:
            return cls(underlying="", exchange="")
        contracts = tuple(
            FutureContract.from_dict(row)
            for row in data.get("contracts", [])
            if isinstance(row, dict)
        )
        expiries_raw = data.get("expiries", [])
        expiries = tuple(str(e) for e in expiries_raw) if isinstance(expiries_raw, list) else ()
        return cls(
            underlying=str(data.get("underlying", "")),
            exchange=str(data.get("exchange", "")),
            expiries=expiries,
            contracts=contracts,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "underlying": self.underlying,
            "exchange": self.exchange,
            "expiries": list(self.expiries),
            "contracts": [c.to_dict() for c in self.contracts],
        }


@dataclass(slots=True, frozen=False)
class ConditionalAlert:
    """Conditional alert state."""

    alert_id: str = ""
    symbol: str = ""
    condition: str = ""
    status: str = "ACTIVE"


@dataclass(slots=True, frozen=False)
class ConditionalAlertRequest:
    """Request model for placing a conditional alert."""

    symbol: str = ""
    exchange: str = "NSE"
    condition_type: str = ""
    threshold: Decimal = Decimal("0")


@dataclass(slots=True, frozen=False)
class MarketIntelligenceSnapshot:
    """One-shot aggregate of market intelligence for an underlying."""

    underlying: str = ""
    pcr: Decimal = Decimal("0")
    max_pain: Decimal = Decimal("0")
    oi_data: dict = field(default_factory=dict)


@dataclass(slots=True, frozen=False)
class PnlExitPolicy:
    """Policy for PnL-based exit automation."""

    target_pnl: Decimal = Decimal("0")
    stop_loss: Decimal = Decimal("0")


@dataclass(slots=True, frozen=False)
class PnlExitResult:
    """Result returned by PnL-exit automation."""

    success: bool = False
    message: str = ""
