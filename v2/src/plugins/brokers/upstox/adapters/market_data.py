"""Upstox market data adapter."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from domain.entities import Bar, MarketDepth, Quote
from domain.value_objects import InstrumentId, Price, Quantity, TimeFrame
from plugins.brokers.upstox.wire import UpstoxWire

if TYPE_CHECKING:
    from plugins.brokers.common.transport import BaseTransport


class UpstoxMarketDataAdapter:
    # Upstox /historical-candle only supports this restricted interval set
    # (per live API: UDAPI1020 — "Interval accepts one of
    # (1minute,30minute,day,week,month)"). Anything else 400s at the broker.
    _INTERVAL_MAP = {
        "1": "1minute", "1m": "1minute", "1M": "1minute",
        "30": "30minute", "30m": "30minute", "30M": "30minute",
        "day": "day", "d": "day", "DAY": "day",
        "week": "week", "month": "month",
    }

    def __init__(self, transport: BaseTransport, wire: UpstoxWire) -> None:
        self._transport = transport
        self._wire = wire

    def get_quote(self, instrument_id: InstrumentId) -> Quote:
        key = self._wire.instrument_key(instrument_id)
        native = self._transport.get("/market-quote/quotes", params={"instrument_key": key})
        return self._wire.to_quote(native, instrument_id=instrument_id)

    def get_ltp(self, instrument_id: InstrumentId) -> Price:
        key = self._wire.instrument_key(instrument_id)
        native = self._transport.get("/market-quote/ltp", params={"instrument_key": key})
        return self._wire.to_ltp(native, instrument_id=instrument_id)

    def get_depth(self, instrument_id: InstrumentId) -> MarketDepth:
        key = self._wire.instrument_key(instrument_id)
        native = self._transport.get("/market-quote/quotes", params={"instrument_key": key})
        return self._wire.to_depth(native, instrument_id=instrument_id)

    def get_history(
        self,
        instrument_id: InstrumentId,
        timeframe: TimeFrame,
        start: datetime,
        end: datetime,
    ) -> list[Bar]:
        key = self._wire.instrument_key(instrument_id)
        interval = self._INTERVAL_MAP.get(timeframe.value)
        if interval is None:
            raise ValueError(
                f"Unsupported Upstox history interval {timeframe.value!r}. "
                f"Supported: {sorted(self._INTERVAL_MAP.values())}"
            )
        native = self._transport.get(
            f"/historical-candle/{key}/{interval}/{end.date()}/{start.date()}"
        )
        rows = native.get("data", {}).get("candles", []) if isinstance(native, dict) else []
        bars: list[Bar] = []
        for row in rows:
            # Upstox candle: [ts, open, high, low, close, volume, oi]
            bars.append(
                Bar(
                    instrument_id=instrument_id,
                    open=Price(value=Decimal(str(row[1]))),
                    high=Price(value=Decimal(str(row[2]))),
                    low=Price(value=Decimal(str(row[3]))),
                    close=Price(value=Decimal(str(row[4]))),
                    volume=Quantity(value=Decimal(str(row[5] if len(row) > 5 else 0))),
                    timeframe=timeframe,
                    timestamp=datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
                    if isinstance(row[0], str)
                    else start,
                )
            )
        return bars
