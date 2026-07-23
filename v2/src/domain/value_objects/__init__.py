"""Frozen value objects — Decimal for money/price/qty, UUID for CorrelationId."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import ClassVar
from uuid import UUID

from domain.enums import AssetKind, ExchangeId


def _norm_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _norm_exchange(exchange: str) -> str:
    return exchange.strip().upper()


@dataclass(frozen=True, slots=True)
class InstrumentId:
    """Canonical instrument identity — single source of truth across the app.

    Format: ``EXCHANGE:UNDERLYING[:EXPIRY(YYYYMMDD)[:STRIKE]][:RIGHT]``
    (ported from legacy ``domain/instruments/instrument_id.py`` — proven design,
    not reinvented). Broker-native formats (Dhan's ``NIFTY-31DEC2026-25000-CE``,
    Upstox's ``NSE_EQ|INE002A01018``) live only inside broker adapters and must
    never leak past ``plugins/brokers/*/instrument_adapter.py``.

    Examples::

        NSE:RELIANCE                    equity
        NSE:NIFTY                       index
        NFO:NIFTY:20260730:FUT          future
        NFO:NIFTY:20260730:25000:CE     option

    Construct via the factory methods (``.equity()``, ``.index()``, ``.future()``,
    ``.option()``, ...) or ``.parse()`` — never via raw field assignment for
    anything beyond equity/index.
    """

    exchange: str
    underlying: str
    expiry: date | None = None
    strike: Decimal | None = None
    right: str | None = None
    kind: str | None = None

    VALID_EXCHANGES: ClassVar[frozenset[str]] = frozenset(e.value for e in ExchangeId)
    VALID_RIGHTS: ClassVar[frozenset[str]] = frozenset({"CE", "PE", "FUT"})

    def __post_init__(self) -> None:
        if self.strike is not None and not isinstance(self.strike, Decimal):
            object.__setattr__(self, "strike", Decimal(str(self.strike)))
        if self.kind is not None:
            parsed = AssetKind.parse(self.kind)
            if parsed is None:
                raise ValueError(f"Invalid AssetKind: {self.kind!r}")
            object.__setattr__(self, "kind", parsed.value)
        exch = _norm_exchange(self.exchange)
        if exch not in self.VALID_EXCHANGES:
            raise ValueError(f"Invalid exchange: {self.exchange!r}. Must be one of {sorted(self.VALID_EXCHANGES)}")
        object.__setattr__(self, "exchange", exch)
        object.__setattr__(self, "underlying", _norm_symbol(self.underlying))
        if self.right and self.right.upper() not in self.VALID_RIGHTS:
            raise ValueError(f"Invalid right: {self.right!r}. Must be one of {self.VALID_RIGHTS}")
        if self.right:
            object.__setattr__(self, "right", self.right.upper())

    # ── Factory methods ───────────────────────────────────────────────────

    @classmethod
    def equity(cls, exchange: str, symbol: str) -> InstrumentId:
        return cls(exchange=exchange, underlying=symbol, kind=AssetKind.EQUITY.value)

    @classmethod
    def index(cls, exchange: str, name: str) -> InstrumentId:
        return cls(exchange=exchange, underlying=name, kind=AssetKind.INDEX.value)

    @classmethod
    def etf(cls, exchange: str, symbol: str) -> InstrumentId:
        return cls(exchange=exchange, underlying=symbol, kind=AssetKind.ETF.value)

    @classmethod
    def spot(cls, exchange: str, symbol: str) -> InstrumentId:
        return cls(exchange=exchange, underlying=symbol, kind=AssetKind.SPOT.value)

    @classmethod
    def currency(cls, exchange: str, symbol: str) -> InstrumentId:
        return cls(exchange=exchange, underlying=symbol, kind=AssetKind.CURRENCY.value)

    @classmethod
    def future(cls, exchange: str, underlying: str, expiry: date, *, kind: str | None = None) -> InstrumentId:
        k = AssetKind.parse(kind) if kind is not None else AssetKind.FUTURES
        if k == AssetKind.FUTURES and _norm_exchange(exchange) == "MCX":
            k = AssetKind.COMMODITY
        return cls(exchange=exchange, underlying=underlying, expiry=expiry, right="FUT", kind=(k or AssetKind.FUTURES).value)

    @classmethod
    def commodity(cls, exchange: str, underlying: str, expiry: date) -> InstrumentId:
        return cls.future(exchange, underlying, expiry, kind=AssetKind.COMMODITY.value)

    @classmethod
    def option(cls, exchange: str, underlying: str, expiry: date, strike: Decimal | float | int, right: str) -> InstrumentId:
        return cls(
            exchange=exchange,
            underlying=underlying,
            expiry=expiry,
            strike=Decimal(str(strike)),
            right=right,
            kind=AssetKind.OPTIONS.value,
        )

    # ── Serialization ─────────────────────────────────────────────────────

    def __str__(self) -> str:
        parts = [self.exchange, self.underlying]
        if self.expiry:
            parts.append(self.expiry.strftime("%Y%m%d"))
        if self.strike is not None:
            parts.append(str(int(self.strike)) if self.strike == self.strike.to_integral_value() else str(self.strike))
        if self.right:
            parts.append(self.right)
        return ":".join(parts)

    def __repr__(self) -> str:
        return f"InstrumentId({self})"

    @property
    def value(self) -> str:
        """Backward-compatible canonical string accessor (``str(self)``)."""
        return str(self)

    @classmethod
    def parse(cls, s: str) -> InstrumentId:
        parts = s.strip().split(":")
        if len(parts) < 2:
            raise ValueError(f"Invalid InstrumentId format: {s!r}. Expected at least 'EXCHANGE:UNDERLYING'")
        exchange = parts[0].upper()
        underlying = parts[1].upper()
        expiry: date | None = None
        strike: Decimal | None = None
        right: str | None = None
        if len(parts) > 2 and parts[2]:
            if re.match(r"^\d{8}$", parts[2]):
                expiry = datetime.strptime(parts[2], "%Y%m%d").date()
            elif parts[2].upper() == "FUT":
                right = "FUT"
        if len(parts) > 3 and parts[3]:
            try:
                strike = Decimal(parts[3])
            except Exception:
                if parts[3].upper() == "FUT":
                    right = "FUT"
        if len(parts) > 4 and parts[4]:
            right = parts[4].upper()
        if expiry and not right:
            right = "FUT"
        return cls(exchange=exchange, underlying=underlying, expiry=expiry, strike=strike, right=right)

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def asset_type(self) -> str:
        if self.kind:
            return self.kind
        if self.right == "FUT":
            return AssetKind.FUTURES.value
        if self.right in ("CE", "PE"):
            return AssetKind.OPTIONS.value
        if self.underlying in ("NIFTY", "BANKNIFTY", "FINNIFTY", "SENSEX", "MIDCPNIFTY"):
            return AssetKind.INDEX.value
        return AssetKind.EQUITY.value

    @property
    def is_option(self) -> bool:
        return self.asset_type == AssetKind.OPTIONS.value

    @property
    def is_future(self) -> bool:
        return self.asset_type in {AssetKind.FUTURES.value, AssetKind.COMMODITY.value}

    @property
    def is_index(self) -> bool:
        return self.asset_type == AssetKind.INDEX.value

    @property
    def is_call(self) -> bool:
        return self.right == "CE"

    @property
    def is_put(self) -> bool:
        return self.right == "PE"

    # ── Identity (kind excluded — classification metadata, not identity) ──

    @property
    def _key(self) -> tuple[str, str, str | None, str | None, str | None]:
        strike_str = str(int(self.strike)) if self.strike is not None and self.strike == self.strike.to_integral_value() else (str(self.strike) if self.strike is not None else None)
        return (self.exchange, self.underlying, self.expiry.isoformat() if self.expiry else None, strike_str, self.right)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, InstrumentId):
            return NotImplemented
        return self._key == other._key

    def __hash__(self) -> int:
        return hash(self._key)


@dataclass(frozen=True, slots=True)
class OrderId:
    value: str


@dataclass(frozen=True, slots=True)
class AccountId:
    value: str


@dataclass(frozen=True, slots=True)
class StrategyId:
    value: str


@dataclass(frozen=True, slots=True)
class ComponentId:
    value: str


@dataclass(frozen=True, slots=True)
class CorrelationId:
    value: UUID


@dataclass(frozen=True, slots=True)
class TimeFrame:
    value: str


@dataclass(frozen=True, slots=True)
class Timestamp:
    """Nanosecond UTC precision timestamp."""
    value: int


@dataclass(frozen=True, slots=True)
class Price:
    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal):
            raise TypeError("Price.value must be Decimal")

    def __mul__(self, other: Quantity | Decimal) -> Decimal:
        if isinstance(other, Quantity):
            return self.value * other.value
        return self.value * other


@dataclass(frozen=True, slots=True)
class Quantity:
    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal):
            raise TypeError("Quantity.value must be Decimal")

    def __mul__(self, other: Price | Decimal) -> Decimal:
        if isinstance(other, Price):
            return other.value * self.value
        return self.value * other


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError("Money.amount must be Decimal")

    def _check_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError(f"currency mismatch: {self.currency} vs {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._check_currency(other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check_currency(other)
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __mul__(self, factor: Decimal) -> Money:
        return Money(amount=self.amount * factor, currency=self.currency)
