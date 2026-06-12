"""Market data client — quotes, historical candles, option data.

Design reference: Trade_J ``DhanMarketDataProvider`` / ``DhanHistoricalDataClient``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from brokers.common.core.enums import ExchangeSegment
from brokers.common.core.models import HistoricalCandle, MarketDepth, MarketDepthLevel, Quote
from brokers.common.resilience.retry import RetryExecutor
from brokers.dhan.mapper.mapping import (
    candles_from_columns,
    decimal_value,
    quote_payload_from_response,
)
from brokers.dhan.market_data.depth.provider import DhanMarketDepthProvider


def _coerce_security_id(security_id: str):
    if security_id.isdigit():
        return int(security_id)
    return security_id


class DhanMarketDataClient:
    """Market data endpoints: LTP, quote, OHLC, history, option chain."""

    def __init__(
        self,
        http_client: Any,
        settings: Any,
        url_resolver: Any,
        retry_executor: RetryExecutor,
        depth_provider: DhanMarketDepthProvider | None = None,
    ) -> None:
        self._http_client = http_client
        self._settings = settings
        self._url_resolver = url_resolver
        self._retry_executor = retry_executor
        self._depth_provider = depth_provider

    # ── Quotes ──────────────────────────────────────────────────────

    def get_quote(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
        mode: str = "quote",
    ) -> Quote:
        endpoint = {
            "ltp": self._url_resolver.market_feed_ltp_url(),
            "quote": self._url_resolver.market_feed_quote_url(),
            "ohlc": self._url_resolver.market_feed_ohlc_url(),
        }.get(mode)
        if endpoint is None:
            raise ValueError(f"Unsupported Dhan market data mode: {mode}")
        response = self._retry_executor.execute(
            lambda: self._http_client.post_json(
                endpoint,
                {exchange_segment.value: [_coerce_security_id(security_id)]},
            )
        )
        return self._quote_from_response(response, security_id, exchange_segment)

    def get_depth(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
    ) -> MarketDepth:
        if self._depth_provider:
            return self._depth_provider.get_depth(security_id, exchange_segment)

        response = self._retry_executor.execute(
            lambda: self._http_client.post_json(
                self._url_resolver.market_feed_quote_url(),
                {exchange_segment.value: [_coerce_security_id(security_id)]},
            )
        )
        return self._depth_from_response(response, security_id, exchange_segment)

    # ── Historical data ─────────────────────────────────────────────

    def get_historical_data(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
        from_date: date,
        to_date: date,
        instrument: str = "EQUITY",
        interval: str | None = None,
    ) -> list[HistoricalCandle]:
        endpoint = (
            self._url_resolver.historical_intraday_url()
            if interval
            else self._url_resolver.historical_daily_url()
        )
        payload: dict[str, Any] = {
            "securityId": security_id,
            "exchangeSegment": exchange_segment.value,
            "instrument": instrument,
            "fromDate": from_date.isoformat(),
            "toDate": to_date.isoformat(),
        }
        if interval:
            payload["interval"] = interval
        response = self._retry_executor.execute(
            lambda: self._http_client.post_json(endpoint, payload)
        )
        return self._candles_from_response(response)

    # ── Option chain ────────────────────────────────────────────────

    def get_option_expiries(
        self,
        underlying: str,
        exchange_segment: ExchangeSegment,
    ) -> list[str]:
        response = self._retry_executor.execute(
            lambda: self._http_client.post_json(
                self._url_resolver.option_chain_expiry_list_url(),
                {
                    "UnderlyingScrip": _coerce_security_id(underlying),
                    "UnderlyingSeg": exchange_segment.value,
                },
            )
        )
        data = response.get("data", {})
        if isinstance(data, dict):
            values = data.get("expiryList") or data.get("expiries") or data.get("expiry") or []
        else:
            values = data
        return [str(v) for v in values]

    def get_option_chain(
        self,
        underlying: str,
        exchange_segment: ExchangeSegment,
        expiry: str,
    ) -> dict[str, Any]:
        return self._retry_executor.execute(
            lambda: self._http_client.post_json(
                self._url_resolver.option_chain_url(),
                {
                    "UnderlyingScrip": _coerce_security_id(underlying),
                    "UnderlyingSeg": exchange_segment.value,
                    "Expiry": expiry,
                },
            )
        )

    # ── Parse helpers ───────────────────────────────────────────────

    def _quote_from_response(
        self,
        response: dict[str, Any],
        security_id: str,
        exchange_segment: ExchangeSegment,
    ) -> Quote:
        data = quote_payload_from_response(response, security_id)
        return Quote(
            security_id=security_id,
            exchange_segment=exchange_segment,
            last_price=decimal_value(
                data.get("last_price") or data.get("lastTradedPrice") or data.get("ltp")
            ),
            open=decimal_value(data.get("open")),
            high=decimal_value(data.get("high")),
            low=decimal_value(data.get("low")),
            close=decimal_value(data.get("close")),
            volume=int(data.get("volume") or 0),
            timestamp=datetime.now(),  # Dhan feed typically omits timestamp
        )

    def _depth_from_response(
        self,
        response: dict[str, Any],
        security_id: str,
        exchange_segment: ExchangeSegment,
    ) -> MarketDepth:
        data = quote_payload_from_response(response, security_id)
        raw_depth = data.get("depth") or data.get("marketDepth") or {}
        if isinstance(raw_depth, list):
            raw_depth = {
                "buy": raw_depth[:10],
                "sell": raw_depth[10:],
            }
        return MarketDepth(
            security_id=security_id,
            exchange_segment=exchange_segment,
            bids=[self._depth_level(level) for level in raw_depth.get("buy", [])],
            asks=[self._depth_level(level) for level in raw_depth.get("sell", [])],
            timestamp=datetime.now(),
        )

    @staticmethod
    def _depth_level(level: dict[str, Any]) -> MarketDepthLevel:
        return MarketDepthLevel(
            price=decimal_value(
                level.get("price") or level.get("buyPrice") or level.get("sellPrice")
            ),
            quantity=int(level.get("quantity") or level.get("qty") or 0),
            orders=int(level.get("orders") or level.get("orderCount") or 0),
        )

    def _candles_from_response(self, response: dict[str, Any]) -> list[HistoricalCandle]:
        candles = candles_from_columns(
            response,
            timestamp_factory=lambda value: (
                datetime.fromtimestamp(value) if isinstance(value, int | float) else datetime.now()
            ),
        )
        return [
            HistoricalCandle(
                timestamp=candle["timestamp"],
                open=candle["open"],
                high=candle["high"],
                low=candle["low"],
                close=candle["close"],
                volume=candle["volume"],
            )
            for candle in candles
        ]
