"""Margin adapter for Dhan."""

from __future__ import annotations

from typing import Any

from brokers.common.api.ports import MarginProvider
from brokers.dhan.market_data.margin import DhanMarginClient


class DhanMarginProvider(MarginProvider):
    """Trade_J-style margin adapter over ``DhanMarginClient``."""

    def __init__(self, margin_client: DhanMarginClient) -> None:
        self._margin_client = margin_client

    @property
    def margin_client(self) -> DhanMarginClient:
        return self._margin_client

    def calculate_margin(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._margin_client.calculate(payload)
