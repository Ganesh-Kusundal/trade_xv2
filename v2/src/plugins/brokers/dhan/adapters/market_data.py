"""Dhan market data — quote / ltp / depth / history."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from domain.entities import Bar, MarketDepth, Quote
from domain.value_objects import InstrumentId, Price, Quantity, TimeFrame
from plugins.brokers.dhan.wire import DhanWire

if TYPE_CHECKING:
    from plugins.brokers.common.transport import BaseTransport

logger = logging.getLogger(__name__)

# Dhan intraday session times by exchange.
_SESSION_OPEN = {"MCX": "09:00:00", "MCX_COMM": "09:00:00"}
_SESSION_CLOSE = {"MCX": "23:30:00", "MCX_COMM": "23:30:00"}
_DEFAULT_OPEN = "09:15:00"
_DEFAULT_CLOSE = "15:30:00"

# Map TimeFrame values to Dhan intraday interval strings.
_INTRADAY_INTERVALS = {
    "1": "1", "1M": "1", "1m": "1",
    "5": "5", "5M": "5", "5m": "5",
    "15": "15", "15M": "15", "15m": "15",
    "25": "25",
    "60": "60", "60M": "60", "60m": "60",
}


class DhanMarketDataAdapter:
    def __init__(self, transport: BaseTransport, wire: DhanWire) -> None:
        self._transport = transport
        self._wire = wire

    def get_quote(self, instrument_id: InstrumentId) -> Quote:
        sec = self._wire.security_id(instrument_id)
        segment = self._wire.get_segment(instrument_id)
        native = self._transport.post("/marketfeed/quote", json={segment: [int(sec)]})
        data = native.get("data", {})
        quote_data = data.get(segment, {}).get(sec, {})
        return self._wire.to_quote(quote_data, instrument_id=instrument_id)

    def get_ltp(self, instrument_id: InstrumentId) -> Price:
        sec = self._wire.security_id(instrument_id)
        segment = self._wire.get_segment(instrument_id)
        native = self._transport.post("/marketfeed/ltp", json={segment: [int(sec)]})
        data = native.get("data", {})
        ltp_data = data.get(segment, {}).get(sec, {})
        return self._wire.to_ltp(ltp_data, instrument_id=instrument_id)

    def get_depth(self, instrument_id: InstrumentId) -> MarketDepth:
        """Depth is extracted from the /marketfeed/quote response (no separate depth endpoint)."""
        sec = self._wire.security_id(instrument_id)
        segment = self._wire.get_segment(instrument_id)
        native = self._transport.post("/marketfeed/quote", json={segment: [int(sec)]})
        data = native.get("data", {})
        quote_data = data.get(segment, {}).get(sec, {})
        return self._wire.to_depth(quote_data, instrument_id=instrument_id)

    def get_history(
        self,
        instrument_id: InstrumentId,
        timeframe: TimeFrame,
        start: datetime,
        end: datetime,
    ) -> list[Bar]:
        from decimal import Decimal

        sec = self._wire.security_id(instrument_id)
        segment = self._wire.get_segment(instrument_id)
        instrument_type = self._wire.get_instrument_type(instrument_id)
        interval = timeframe.value if hasattr(timeframe, "value") else str(timeframe)

        # Dhan expects ISO-style YYYY-MM-DD (daily) / YYYY-MM-DD HH:MM:SS (intraday)
        from_date = start.strftime("%Y-%m-%d")
        to_date = end.strftime("%Y-%m-%d")

        if interval in _INTRADAY_INTERVALS:
            # Intraday: use /charts/intraday with session times
            exchange = instrument_id.value.split(":")[0] if ":" in instrument_id.value else "NSE"
            sess_open = _SESSION_OPEN.get(exchange.upper(), _DEFAULT_OPEN)
            sess_close = _SESSION_CLOSE.get(exchange.upper(), _DEFAULT_CLOSE)
            endpoint = "/charts/intraday"
            payload = {
                "securityId": sec,
                "exchangeSegment": segment,
                "instrument": instrument_type,
                "interval": _INTRADAY_INTERVALS[interval],
                "oi": True,
                "fromDate": f"{from_date} {sess_open}",
                "toDate": f"{to_date} {sess_close}",
            }
        else:
            # Daily: use /charts/historical
            endpoint = "/charts/historical"
            payload = {
                "securityId": sec,
                "exchangeSegment": segment,
                "instrument": instrument_type,
                "expiryCode": 0,
                "oi": True,
                "fromDate": from_date,
                "toDate": to_date,
            }

        native = self._transport.post(endpoint, json=payload)
        # Dhan returns either:
        #  - columnar dict: {"open":[...],"high":[...],"timestamp":[...]}  (both daily & intraday)
        #  - list of row dicts (some callers)
        candles = native if isinstance(native, list) else native.get("data", native)
        if isinstance(candles, dict) and "open" in candles:
            # Columnar format — transpose to rows aligned by index.
            n = len(candles.get("open", []))
            rows = []
            for i in range(n):
                rows.append(
                    {
                        "timestamp": candles.get("timestamp", [None] * n)[i],
                        "open": candles.get("open", [0] * n)[i],
                        "high": candles.get("high", [0] * n)[i],
                        "low": candles.get("low", [0] * n)[i],
                        "close": candles.get("close", [0] * n)[i],
                        "volume": candles.get("volume", [0] * n)[i],
                    }
                )
        elif isinstance(candles, dict):
            rows = candles.get("data", [])
        else:
            rows = candles
        bars: list[Bar] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            ts = start
            if "timestamp" in row and row["timestamp"] is not None:
                try:
                    ts = datetime.fromtimestamp(int(row["timestamp"]))
                except (ValueError, TypeError, OSError):
                    try:
                        ts = datetime.fromisoformat(str(row["timestamp"]))
                    except (ValueError, TypeError):
                        pass
            bars.append(
                Bar(
                    instrument_id=instrument_id,
                    open=Price(value=Decimal(str(row.get("open", 0)))),
                    high=Price(value=Decimal(str(row.get("high", 0)))),
                    low=Price(value=Decimal(str(row.get("low", 0)))),
                    close=Price(value=Decimal(str(row.get("close", 0)))),
                    volume=Quantity(value=Decimal(str(row.get("volume", 0)))),
                    timeframe=timeframe,
                    timestamp=ts,
                )
            )
        return bars

    def get_batch_ltp(self, instrument_ids: list[InstrumentId]) -> dict[InstrumentId, Price]:
        """Native batch LTP — single HTTP call for multiple symbols."""
        from decimal import Decimal

        segment_map: dict[str, list[int]] = {}
        id_map: dict[str, InstrumentId] = {}
        for iid in instrument_ids:
            try:
                sec = self._wire.security_id(iid)
                segment = self._wire.get_segment(iid)
                segment_map.setdefault(segment, []).append(int(sec))
                id_map[sec] = iid
            except (KeyError, ValueError):
                continue
        if not segment_map:
            return {}
        native = self._transport.post("/marketfeed/ltp", json=segment_map)
        result: dict[InstrumentId, Price] = {}
        for _seg, sids in native.get("data", {}).items():
            for sid_str, info in sids.items():
                iid = id_map.get(sid_str)
                if iid:
                    result[iid] = Price(value=Decimal(str(info.get("last_price", 0))))
        return result

    def get_batch_quote(self, instrument_ids: list[InstrumentId]) -> dict[InstrumentId, Quote]:
        """Native batch quote — single HTTP call for multiple symbols."""
        segment_map: dict[str, list[int]] = {}
        id_map: dict[str, InstrumentId] = {}
        for iid in instrument_ids:
            try:
                sec = self._wire.security_id(iid)
                segment = self._wire.get_segment(iid)
                segment_map.setdefault(segment, []).append(int(sec))
                id_map[sec] = iid
            except (KeyError, ValueError):
                continue
        if not segment_map:
            return {}
        native = self._transport.post("/marketfeed/quote", json=segment_map)
        result: dict[InstrumentId, Quote] = {}
        for _seg, sids in native.get("data", {}).items():
            for sid_str, info in sids.items():
                iid = id_map.get(sid_str)
                if iid:
                    result[iid] = self._wire.to_quote(info, instrument_id=iid)
        return result
