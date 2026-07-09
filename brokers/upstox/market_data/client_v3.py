"""Upstox V3 market data REST client (LTP/OHLC/greeks + full snapshot via v2 path)."""

from __future__ import annotations

from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver

# Official REST limits (Upstox Developer API, 2026).
UPSTOX_QUOTE_MAX_KEYS = 500
UPSTOX_OPTION_GREEK_MAX_KEYS = 50


class UpstoxMarketDataV3Client:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def get_full_quote(self, instrument_keys: list[str]) -> dict[str, Any]:
        """Full snapshot (depth+OHLC). Docs still serve this under /v2/market-quote/quotes."""
        if isinstance(instrument_keys, str):
            instrument_keys = [instrument_keys]
        params = {"instrument_key": ",".join(instrument_keys)}
        return self._http.get_json(self._urls.market_quote_full_v3_url(), params=params)

    def get_ltp_v3(self, instrument_keys: list[str]) -> dict[str, Any]:
        """V3 LTP with ltq / volume / cp. Max 500 instrument keys."""
        if isinstance(instrument_keys, str):
            instrument_keys = [instrument_keys]
        params = {"instrument_key": ",".join(instrument_keys)}
        return self._http.get_json(self._urls.market_quote_ltp_v3_url(), params=params)

    def get_ohlc_v3(
        self,
        instrument_keys: list[str],
        *,
        interval: str = "1d",
    ) -> dict[str, Any]:
        """V3 OHLC with live_ohlc / prev_ohlc. interval: 1d | I1 | I30."""
        if isinstance(instrument_keys, str):
            instrument_keys = [instrument_keys]
        params = {
            "instrument_key": ",".join(instrument_keys),
            "interval": interval,
        }
        return self._http.get_json(self._urls.market_quote_ohlc_v3_url(), params=params)

    def get_option_greeks_v3(self, instrument_keys: list[str]) -> dict[str, Any]:
        """Option greeks. Max 50 instrument keys per docs."""
        if isinstance(instrument_keys, str):
            instrument_keys = [instrument_keys]
        params = {"instrument_key": ",".join(instrument_keys)}
        return self._http.get_json(self._urls.market_quote_option_greeks_v3_url(), params=params)

    def get_mtf_positions(self) -> list[dict[str, Any]]:
        body = self._http.get_json(self._urls.mtf_positions_v3_url())
        if not isinstance(body, dict):
            return []
        return body.get("data") if isinstance(body.get("data"), list) else []

    def get_funds_v3(self) -> dict[str, Any]:
        return self._http.get_json(self._urls.user_fund_margin_v3_url())
