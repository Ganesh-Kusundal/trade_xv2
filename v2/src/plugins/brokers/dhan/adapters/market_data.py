"""Dhan market data — quote / ltp / depth / history."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from domain.entities import Bar, MarketDepth, Quote
from domain.value_objects import InstrumentId, Price, Quantity, TimeFrame
from plugins.brokers.dhan.wire import DhanWire

if TYPE_CHECKING:
    from plugins.brokers.common.transport import BaseTransport


class DhanMarketDataAdapter:
    def __init__(self, transport: BaseTransport, wire: DhanWire) -> None:
        self._transport = transport
        self._wire = wire

    def get_quote(self, instrument_id: InstrumentId) -> Quote:
        sec = self._wire.security_id(instrument_id)
        native = self._transport.get("/marketfeed/quote", params={"securityId": sec})
        return self._wire.to_quote(native, instrument_id=instrument_id)

    def get_ltp(self, instrument_id: InstrumentId) -> Price:
        sec = self._wire.security_id(instrument_id)
        native = self._transport.get("/marketfeed/ltp", params={"securityId": sec})
        return self._wire.to_ltp(native, instrument_id=instrument_id)

    def get_depth(self, instrument_id: InstrumentId) -> MarketDepth:
        sec = self._wire.security_id(instrument_id)
        native = self._transport.get("/marketfeed/depth", params={"securityId": sec})
        return self._wire.to_depth(native, instrument_id=instrument_id)

    def get_history(
        self,
        instrument_id: InstrumentId,
        timeframe: TimeFrame,
        start: datetime,
        end: datetime,
    ) -> list[Bar]:
        from decimal import Decimal

        sec = self._wire.security_id(instrument_id)
        native = self._transport.get(
            "/charts/historical",
            params={
                "securityId": sec,
                "interval": timeframe.value if hasattr(timeframe, "value") else str(timeframe),
                "from": start.isoformat(),
                "to": end.isoformat(),
            },
        )
        rows = native if isinstance(native, list) else native.get("data", [])
        bars: list[Bar] = []
        for row in rows:
            bars.append(
                Bar(
                    instrument_id=instrument_id,
                    open=Price(value=Decimal(str(row["open"]))),
                    high=Price(value=Decimal(str(row["high"]))),
                    low=Price(value=Decimal(str(row["low"]))),
                    close=Price(value=Decimal(str(row["close"]))),
                    volume=Quantity(value=Decimal(str(row.get("volume", 0)))),
                    timeframe=timeframe,
                    timestamp=start if "timestamp" not in row else datetime.fromisoformat(str(row["timestamp"])),
                )
            )
        return bars
