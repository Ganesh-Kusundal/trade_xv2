"""Upstox V3 historical candle client.

Supports custom intervals: minutes (1-300), hours (1-5), days, weeks, months.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import requests


class UpstoxHistoricalV3Client:
    def __init__(self, http_client: Any) -> None:
        self._http = http_client
        self._base_url = "https://api.upstox.com/v3"

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
            instrument_key: e.g., 'NSE_EQ|INE002A01018'
            unit: 'minutes', 'hours', 'days', 'weeks', 'months'
            interval: '1', '5', '15', '30', '60' etc.
            to_date: End date
            from_date: Start date (optional)
        """
        url = f"{self._base_url}/historical-candle/{instrument_key}/{unit}/{interval}/{to_date.isoformat()}"
        if from_date:
            url += f"/{from_date.isoformat()}"
        return self._http.get_json(url)

    def get_intraday_candles(
        self,
        instrument_key: str,
        unit: str,
        interval: str,
        to_date: date,
    ) -> dict[str, Any]:
        """Fetch intraday candles using V3 API."""
        url = f"{self._base_url}/intraday-candle/{instrument_key}/{unit}/{interval}/{to_date.isoformat()}"
        return self._http.get_json(url)
