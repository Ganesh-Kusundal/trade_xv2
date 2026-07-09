"""Upstox V3 historical candle client.

Supports custom intervals: minutes (1-300), hours (1-5), days, weeks, months.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


class UpstoxHistoricalV3Client:
    """Client for the Upstox v3 historical and intraday candle endpoints.

    The host and version segment are owned by
    :class:`brokers.upstox.auth.urls.UpstoxApiUrlResolver` — this
    client only composes the instrument/unit/interval path. This
    keeps the audit (see ``docs/UPSTOX_WIRE_FORMAT.md``) in sync:
    if the resolver moves a host, this client follows automatically.
    """

    def __init__(self, http_client: Any, url_resolver: Any) -> None:
        self._http = http_client
        # The resolver is the canonical owner of the host and path.
        # This client only composes the instrument/unit/interval
        # tail of the URL.
        self._urls = url_resolver

    def get_candles(
        self,
        instrument_key: str,
        unit: str,
        interval: str,
        to_date: date,
        from_date: date | None = None,
    ) -> dict[str, Any]:
        """Fetch historical candles using V3 API.

        Args:
            instrument_key: e.g., 'NSE_EQ|INE002A01018' (will be URL-encoded)
            unit: 'minutes', 'hours', 'days', 'weeks', 'months'
            interval: '1', '5', '15', '30', '60' etc.
            to_date: End date
            from_date: Start date (optional)
        """
        url = self._urls.historical_candle_v3_url(
            instrument_key=instrument_key,
            unit=unit,
            interval=int(interval),
            to_date=to_date.isoformat(),
            from_date=from_date.isoformat() if from_date else None,
        )
        logger.debug("Fetching historical candles: %s", url)
        return self._http.get_json(url)

    def get_intraday_candles(
        self,
        instrument_key: str,
        unit: str,
        interval: str,
        to_date: date,
    ) -> dict[str, Any]:
        """Fetch intraday candles using V3 API."""
        url = self._urls.intraday_candle_v3_url(
            instrument_key=instrument_key,
            unit=unit,
            interval=int(interval),
            to_date=to_date.isoformat(),
        )
        return self._http.get_json(url)
