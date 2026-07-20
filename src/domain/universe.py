"""Universe — builds domain instruments from symbols. Broker-free by design.

Session lives in :mod:`domain.session` (split for LOC compliance).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from domain.constants.market import DEFAULT_EXCHANGE
from domain.instruments.instrument import (
    ETF,
    Commodity,
    Currency,
    Equity,
    Future,
    Index,
    Instrument,
    Option,
    Spot,
)
from domain.instruments.instrument_id import InstrumentId


# Re-export Session / SessionDx so existing ``from domain.universe import Session`` works.
# Lazy import to avoid circular dependency with domain.__init__.
def __getattr__(name: str):
    if name in ("Session", "SessionDx"):
        from domain.session import Session, SessionDx

        return Session if name == "Session" else SessionDx
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if TYPE_CHECKING:
    from domain.ports.event_publisher import EventBusPort
    from domain.ports.order_service import OrderServicePort
    from domain.ports.protocols import DataProvider, ExecutionProvider


__all__ = ["Session", "SessionDx", "Universe"]


class Universe:
    """Builds domain instruments from symbols. Broker-free by design."""

    def __init__(
        self,
        provider: DataProvider,
        *,
        event_bus: EventBusPort | None = None,
        execution_provider: ExecutionProvider | None = None,
        order_service: OrderServicePort | None = None,
    ) -> None:
        self._provider = provider
        self._event_bus = event_bus
        self._execution_provider = execution_provider
        self._order_service = order_service
        self._broker_facade: Any | None = None

    def _stamp(self, instrument: Instrument) -> Instrument:
        """Stamp data/execution/OMS ports + broker facade (KD-12)."""
        instrument._bind_session_ports(
            data_provider=self._provider,
            execution_provider=self._execution_provider,
            order_service=self._order_service,
        )
        if self._broker_facade is not None:
            facade = self._broker_facade
            instrument._extensions.register(facade.broker_id, facade)
            for ext in getattr(facade, "extensions", None) or []:
                name = getattr(ext, "name", None)
                if name:
                    instrument._extensions.register(str(name), ext)
        return instrument

    def equity(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> Equity:
        return self._stamp(
            Equity(
                symbol,
                exchange,
                data_provider=self._provider,
                execution_provider=self._execution_provider,
            )
        )

    def etf(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> ETF:
        return self._stamp(
            ETF(
                symbol,
                exchange,
                data_provider=self._provider,
                execution_provider=self._execution_provider,
            )
        )

    def spot(self, symbol: str, exchange: str = "CDS") -> Spot:
        return self._stamp(
            Spot(
                symbol,
                exchange,
                data_provider=self._provider,
                execution_provider=self._execution_provider,
            )
        )

    def currency(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> Currency:
        return self._stamp(
            Currency(
                symbol,
                exchange,
                data_provider=self._provider,
                execution_provider=self._execution_provider,
            )
        )

    def index(self, name: str, exchange: str = DEFAULT_EXCHANGE) -> Index:
        return self._stamp(
            Index(
                name,
                exchange,
                data_provider=self._provider,
                execution_provider=self._execution_provider,
            )
        )

    def future(self, symbol: str, *, expiry: date, exchange: str = "NFO") -> Future:
        return self._stamp(
            Future(
                symbol,
                exchange,
                expiry=expiry,
                data_provider=self._provider,
                execution_provider=self._execution_provider,
            )
        )

    def commodity(self, symbol: str, *, expiry: date, exchange: str = "MCX") -> Commodity:
        return self._stamp(
            Commodity(
                symbol,
                exchange,
                expiry=expiry,
                data_provider=self._provider,
                execution_provider=self._execution_provider,
            )
        )

    def option(
        self,
        underlying: str,
        strike: Any,
        right: str,
        *,
        expiry: date,
        exchange: str = "NFO",
        leg: Any | None = None,
    ) -> Option:
        iid = InstrumentId.option(exchange, underlying, expiry, strike, right)
        return self._stamp(
            Option(
                iid,
                strike=strike,
                expiry=expiry,
                right=right,
                data_provider=self._provider,
                execution_provider=self._execution_provider,
                leg=leg,
            )
        )

    def get(self, instrument_id: InstrumentId) -> Instrument:
        """Build stamped instrument from id — dispatches to typed factories when kind known."""
        kind = instrument_id.asset_type
        if instrument_id.is_option and instrument_id.expiry and instrument_id.strike is not None:
            return self.option(
                instrument_id.underlying,
                instrument_id.strike,
                instrument_id.right or "CE",
                expiry=instrument_id.expiry,
                exchange=instrument_id.exchange,
            )
        if instrument_id.is_future and instrument_id.expiry:
            if kind == "COMMODITY":
                return self.commodity(
                    instrument_id.underlying,
                    expiry=instrument_id.expiry,
                    exchange=instrument_id.exchange,
                )
            return self.future(
                instrument_id.underlying,
                expiry=instrument_id.expiry,
                exchange=instrument_id.exchange,
            )
        if kind == "INDEX" or instrument_id.is_index:
            return self.index(instrument_id.underlying, instrument_id.exchange)
        if kind == "ETF":
            return self.etf(instrument_id.underlying, instrument_id.exchange)
        if kind == "SPOT":
            return self.spot(instrument_id.underlying, instrument_id.exchange)
        if kind == "CURRENCY":
            return self.currency(instrument_id.underlying, instrument_id.exchange)
        return self._stamp(
            Instrument(
                instrument_id,
                data_provider=self._provider,
                execution_provider=self._execution_provider,
            )
        )
