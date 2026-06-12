"""Upstox market intelligence adapter — implements ``MarketIntelligencePort``."""

from __future__ import annotations

from typing import Any

from brokers.common.api.ports import MarketIntelligencePort
from brokers.upstox.market_intelligence.client import UpstoxMarketIntelligenceClient


class UpstoxMarketIntelligenceAdapter(MarketIntelligencePort):
    def __init__(self, client: UpstoxMarketIntelligenceClient) -> None:
        self._client = client

    def get_pcr(self, underlying: str, interval: str = "1d") -> dict[str, Any]:
        return self._client.get_pcr(underlying, interval)

    def get_max_pain(self, underlying: str, expiry: str, date: str) -> dict[str, Any]:
        return self._client.get_max_pain(underlying, expiry, date)

    def get_oi(self, underlying: str, expiry: str, date: str) -> dict[str, Any]:
        return self._client.get_oi(underlying, expiry, date)

    def get_fii_flow(self, segment: str = "ALL", interval: str = "1D") -> dict[str, Any]:
        return self._client.get_fii_flow(segment, interval)

    def get_dii_flow(self, interval: str = "1D") -> dict[str, Any]:
        return self._client.get_dii_flow(interval)

    def get_smartlist(self, kind: str, asset_type: str, category: str) -> list[dict[str, Any]]:
        if kind == "futures":
            return self._client.get_smartlist_futures()
        return self._client.get_smartlist_options(kind)
