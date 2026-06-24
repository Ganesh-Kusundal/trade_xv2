"""Upstox market data adapter — implements ``MarketDataProvider`` port.

Mirrors Trade_J ``UpstoxMarketDataProvider``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from brokers.common.api import MarketDataProvider
from domain import MarketDepth, OptionContract, Quote
from domain import HistoricalCandle
from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
from brokers.upstox.market_data.client_v2 import UpstoxMarketDataV2Client
from brokers.upstox.market_data.client_v3 import UpstoxMarketDataV3Client
from brokers.upstox.market_data.historical_v2 import UpstoxHistoricalV2Client


class UpstoxMarketDataAdapter(MarketDataProvider):
    def __init__(
        self,
        v2: UpstoxMarketDataV2Client,
        v3: UpstoxMarketDataV3Client,
        historical: UpstoxHistoricalV2Client,
    ) -> None:
        self._v2 = v2
        self._v3 = v3
        self._historical = historical

    def get_quote(self, security_id: str, exchange_segment: Any, mode: str = "quote") -> Quote:
        instrument_key = f"{_segment_wire(exchange_segment)}|{security_id}"
        body = self._v2.get_quote([instrument_key])
        return UpstoxDomainMapper.to_quote(body)

    def get_historical_daily(
        self,
        security_id: str,
        exchange_segment: Any,
        from_date: date,
        to_date: date,
        instrument: str = "EQUITY",
    ) -> list[HistoricalCandle]:
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
    ) -> list[HistoricalCandle]:
        instrument_key = f"{_segment_wire(exchange_segment)}|{security_id}"
        body = self._historical.get_candles(
            instrument_key, interval or "1minute", to_date, from_date
        )
        return UpstoxDomainMapper.to_historical_candles(body)

    def get_depth(self, security_id: str, exchange_segment: Any) -> MarketDepth:
        instrument_key = f"{_segment_wire(exchange_segment)}|{security_id}"
        body = self._v2.get_order_book(instrument_key)
        return UpstoxDomainMapper.to_market_depth(body)

    def get_option_chain(
        self, underlying: str, exchange_segment: Any, expiry: str
    ) -> list[OptionContract]:
        return []  # delegated to UpstoxOptionsAdapter

    def get_option_expiries(self, underlying: str, exchange_segment: Any) -> list[str]:
        return []  # delegated to UpstoxOptionsAdapter


def _segment_wire(segment: Any) -> str:
    from ..mappers.domain_mapper import UpstoxDomainMapper

    return UpstoxDomainMapper.segment_to_wire(segment)
