"""Upstox market data adapter — implements ``MarketDataProvider`` port.

Uses V3 LTP (ltq/volume/cp) when available, full snapshot via documented
v2/v3 quotes path, and native multi-key batching (≤500 keys per request).
"""

from __future__ import annotations

from datetime import date
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from brokers.common.api import MarketDataProvider
from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
from brokers.upstox.market_data.client_v2 import UpstoxMarketDataV2Client
from brokers.upstox.market_data.client_v3 import (
    UPSTOX_QUOTE_MAX_KEYS,
    UpstoxMarketDataV3Client,
)
from brokers.upstox.market_data.historical_v2 import UpstoxHistoricalV2Client
from domain import MarketDepth, OptionContract, Quote
from domain.candles.historical import (
    DateRange,
    HistoricalBar,
    HistoricalSeries,
    InstrumentRef,
)


def _chunked(items: list[str], size: int) -> list[list[str]]:
    if size <= 0:
        size = UPSTOX_QUOTE_MAX_KEYS
    return [items[i : i + size] for i in range(0, len(items), size)]


class UpstoxMarketDataAdapter(MarketDataProvider):
    """Market data adapter with native multi-key batch + V3 LTP preference."""

    def __init__(
        self,
        v2: UpstoxMarketDataV2Client,
        v3: UpstoxMarketDataV3Client,
        historical: UpstoxHistoricalV2Client,
        *,
        max_keys_per_request: int = UPSTOX_QUOTE_MAX_KEYS,
    ) -> None:
        self._v2 = v2
        self._v3 = v3
        self._historical = historical
        self._max_keys = max(1, int(max_keys_per_request))

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        """Fetch full quote with OHLCV (+ depth when API returns it)."""
        instrument_key = _as_instrument_key(symbol, exchange)
        body = self._v2.get_quote([instrument_key])
        return UpstoxDomainMapper.to_quote(body)

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        """Fetch last traded price — prefer V3 LTP, fall back to full quote."""
        instrument_key = _as_instrument_key(symbol, exchange)
        try:
            body = self._v3.get_ltp_v3([instrument_key])
            q = UpstoxDomainMapper.to_quote(body)
            if q.ltp and q.ltp != 0:
                return q.ltp
        except Exception:
            pass
        body = self._v2.get_quote([instrument_key])
        return UpstoxDomainMapper.to_quote(body).ltp

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        """Fetch order book depth (best five via full quote endpoint)."""
        instrument_key = _as_instrument_key(symbol, exchange)
        body = self._v2.get_order_book(instrument_key)
        return UpstoxDomainMapper.to_market_depth(body)

    def quotes_batch(self, instrument_keys: list[str]) -> dict[str, Quote]:
        """Native multi-key full quotes. Chunks at ``max_keys_per_request`` (≤500)."""
        return self._fetch_quotes_chunked(instrument_keys, mode="full")

    def ltps_batch(self, instrument_keys: list[str]) -> dict[str, Decimal]:
        """Native multi-key LTP via V3 (fallback full). Chunks at ≤500."""
        quotes = self._fetch_quotes_chunked(instrument_keys, mode="ltp")
        return {k: q.ltp for k, q in quotes.items()}

    def _fetch_quotes_chunked(
        self,
        instrument_keys: list[str],
        *,
        mode: str,
    ) -> dict[str, Quote]:
        keys = [k for k in instrument_keys if k]
        if not keys:
            return {}
        out: dict[str, Quote] = {}
        for chunk in _chunked(keys, self._max_keys):
            body = self._fetch_chunk(chunk, mode=mode)
            mapped = UpstoxDomainMapper.to_quotes(body)
            out.update(mapped)
        return out

    def _fetch_chunk(self, chunk: list[str], *, mode: str) -> dict[str, Any]:
        if mode == "ltp":
            try:
                return self._v3.get_ltp_v3(chunk)
            except Exception:
                try:
                    return self._v2.get_ltp(chunk)
                except Exception:
                    return self._v2.get_quote(chunk)
        # full quote — documented multi-key path
        return self._v2.get_quote(chunk)

    def get_history_series(
        self,
        symbol: str | list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> HistoricalSeries:
        """Fetch historical candles as domain ``HistoricalSeries`` (SSOT)."""
        if isinstance(symbol, list):
            symbol = symbol[0]

        bars = self._fetch_historical_bars(
            symbol,
            exchange,
            timeframe,
            lookback_days=lookback_days,
            from_date=from_date,
            to_date=to_date,
        )
        ref = InstrumentRef(symbol=symbol, exchange=exchange)
        coverage = (
            DateRange(bars[0].event_time.date(), bars[-1].event_time.date())
            if bars
            else DateRange(date.today(), date.today())
        )
        return HistoricalSeries(
            bars=bars,
            coverage=coverage,
            instrument=ref,
            timeframe=timeframe,
        )

    def history(
        self,
        symbol: str | list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        """Fetch historical candle data (DataFrame export of ``get_history_series``)."""
        return self.get_history_series(
            symbol,
            exchange,
            timeframe,
            lookback_days=lookback_days,
            from_date=from_date,
            to_date=to_date,
        ).to_dataframe()

    def _fetch_historical_bars(
        self,
        symbol: str,
        exchange: str,
        timeframe: str,
        *,
        lookback_days: int,
        from_date: str | None,
        to_date: str | None,
    ) -> list[HistoricalBar]:
        instrument_key = _as_instrument_key(symbol, exchange)

        interval = timeframe.lower()
        if interval == "1d":
            interval = "day"
        elif interval == "1h":
            interval = "1hour"
        elif interval == "15m":
            interval = "15minute"
        elif interval == "5m":
            interval = "5minute"
        elif interval == "1m":
            interval = "1minute"

        from datetime import datetime, timedelta

        to_dt = datetime.now() if to_date is None else datetime.fromisoformat(to_date)

        if from_date is None:
            from_dt = to_dt - timedelta(days=lookback_days)
        else:
            from_dt = datetime.fromisoformat(from_date)

        body = self._historical.get_candles(
            instrument_key, interval, to_dt.date(), from_dt.date()
        )
        return UpstoxDomainMapper.to_historical_candles(
            body, symbol=symbol, exchange=exchange, timeframe=timeframe
        )

    def get_historical_daily(
        self,
        security_id: str,
        exchange_segment: Any,
        from_date: date,
        to_date: date,
        instrument: str = "EQUITY",
    ) -> list[HistoricalBar]:
        instrument_key = f"{_segment_wire(exchange_segment)}|{security_id}"
        body = self._historical.get_candles(instrument_key, "day", to_date, from_date)
        return UpstoxDomainMapper.to_historical_candles(body)

    def get_historical_intraday(
        self,
        security_id: str,
        exchange_segment: Any,
        from_date: date,
        to_date: date,
        interval: str | None = None,
    ) -> list[HistoricalBar]:
        instrument_key = f"{_segment_wire(exchange_segment)}|{security_id}"
        body = self._historical.get_candles(
            instrument_key, interval or "1minute", to_date, from_date
        )
        return UpstoxDomainMapper.to_historical_candles(body)

    def get_option_chain(
        self, underlying: str, exchange_segment: Any, expiry: str
    ) -> list[OptionContract]:
        return []

    def get_option_expiries(self, underlying: str, exchange_segment: Any) -> list[str]:
        return []


def _as_instrument_key(symbol: str, exchange: str) -> str:
    if "|" in symbol:
        return symbol
    return f"{_segment_wire(exchange)}|{symbol}"


def _segment_wire(segment: Any) -> str:
    from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper

    return UpstoxDomainMapper.segment_to_wire(segment)
