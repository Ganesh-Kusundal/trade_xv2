"""Upstox margin adapter — implements ``MarginProvider`` port via shared normalizer."""

from __future__ import annotations

from typing import Any

from brokers.common.api import MarginProvider
from brokers.common.oms.margin_provider import parse_margin_response
from brokers.upstox.market_data.margin import UpstoxMarginClient


class UpstoxMarginAdapter(MarginProvider):
    def __init__(self, client: UpstoxMarginClient) -> None:
        self._client = client

    def calculate_margin(self, payload: dict[str, Any]):
        raw = self._client.calculate_margin(payload)
        if isinstance(raw, dict) and "data" in raw and isinstance(raw["data"], dict):
            raw = raw["data"]
        return parse_margin_response(raw if isinstance(raw, dict) else {})
