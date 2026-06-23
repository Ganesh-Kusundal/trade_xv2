"""Broker-agnostic instrument registry."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from brokers.common.core.domain import ExchangeSegment, InstrumentType
from brokers.common.core.exchange_segments import canonical_exchange_short, parse_segment


@dataclass(frozen=True)
class Instrument:
    """Canonical instrument used by the trading engine."""

    symbol: str
    exchange: str
    asset_class: InstrumentType = InstrumentType.EQUITY
    expiry: str | None = None
    strike: Decimal | None = None
    option_type: str | None = None
    lot_size: int = 0
    tick_size: Decimal = Decimal("0")
    broker_identifier: str = ""
    broker_symbol: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return self.symbol.upper(), self.exchange.upper()


class InstrumentRegistry:
    """Maps canonical instruments to broker identifiers.

    Core systems use ``Instrument(symbol, exchange)``. Broker adapters use the
    registry only at their boundary to translate between canonical symbols and
    broker-specific identifiers such as Dhan security IDs or Zerodha tokens.
    """

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], Instrument] = {}
        self._by_broker_identifier: dict[tuple[str, str], Instrument] = {}
        self._register_seed_instruments()

    def register(
        self,
        symbol: str,
        exchange: str,
        asset_class: InstrumentType = InstrumentType.EQUITY,
        *,
        expiry: str | None = None,
        strike: Decimal | str | int | float | None = None,
        option_type: str | None = None,
        lot_size: int = 0,
        tick_size: Decimal | str | int | float = Decimal("0"),
        broker_identifier: str = "",
        broker_symbol: str = "",
    ) -> Instrument:
        instrument = Instrument(
            symbol=symbol.upper(),
            exchange=exchange.upper(),
            asset_class=asset_class,
            expiry=expiry,
            strike=self._decimal(strike),
            option_type=option_type.upper() if option_type else None,
            lot_size=lot_size,
            tick_size=self._decimal(tick_size),
            broker_identifier=broker_identifier,
            broker_symbol=broker_symbol,
        )
        self._by_key[instrument.key] = instrument
        if broker_identifier:
            self._by_broker_identifier[(broker_identifier, exchange.upper())] = instrument
        return instrument

    def register_many(self, instruments: Iterable[Instrument]) -> None:
        for instrument in instruments:
            key = instrument.key
            self._by_key[key] = instrument
            if instrument.broker_identifier:
                self._by_broker_identifier[(instrument.broker_identifier, instrument.exchange)] = (
                    instrument
                )

    def resolve(self, symbol: str, exchange: str) -> Instrument | None:
        return self._by_key.get((symbol.upper(), exchange.upper()))

    def require(self, symbol: str, exchange: str) -> Instrument:
        instrument = self.resolve(symbol, exchange)
        if instrument is None:
            raise KeyError(f"No instrument registered for {symbol} {exchange}")
        return instrument

    def broker_identifier(self, symbol: str, exchange: str) -> str:
        return self.require(symbol, exchange).broker_identifier

    def resolve_by_broker_identifier(
        self, broker_identifier: str, exchange: str
    ) -> Instrument | None:
        return self._by_broker_identifier.get((str(broker_identifier), exchange.upper()))

    def canonical_symbol(self, broker_identifier: str, exchange: str) -> str:
        instrument = self.resolve_by_broker_identifier(broker_identifier, exchange)
        if instrument is None:
            return str(broker_identifier)
        return instrument.symbol

    def all(self) -> list[Instrument]:
        return list(self._by_key.values())

    @staticmethod
    def canonical_exchange(segment: ExchangeSegment) -> str:
        return canonical_exchange_short(segment)

    @staticmethod
    def exchange_segment(exchange: str) -> ExchangeSegment:
        parsed = parse_segment(exchange)
        if parsed is None:
            raise ValueError(f"Unknown exchange segment: {exchange!r}")
        return parsed

    @staticmethod
    def _decimal(value: Decimal | str | int | float | None) -> Decimal:
        if value is None:
            return Decimal("0")
        return Decimal(str(value))

    def _register_seed_instruments(self) -> None:
        # No-op: instrument resolution is now handled by brokers.dhan.resolver.SymbolResolver
        # which loads from the Dhan instrument master CSV at runtime.
        pass
