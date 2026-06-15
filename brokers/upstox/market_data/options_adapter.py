"""Upstox options adapter — implements ``OptionsProvider`` port."""

from __future__ import annotations

from brokers.common.api.ports import OptionsProvider
from brokers.common.core.domain import OptionContract
from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
from brokers.upstox.market_data.options_client import UpstoxOptionsClient


class UpstoxOptionsAdapter(OptionsProvider):
    def __init__(self, client: UpstoxOptionsClient) -> None:
        self._client = client

    def get_expiries(self, underlying: str, exchange_segment: str) -> list[str]:
        return self._client.get_expiries(underlying)

    def get_option_chain(
        self, underlying: str, exchange_segment: str, expiry: str
    ) -> list[OptionContract]:
        body = self._client.get_chain(underlying, expiry)
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            return []
        out: list[OptionContract] = []
        for row in data:
            if isinstance(row, dict):
                out.append(UpstoxDomainMapper.to_option_contract(row))
        return out
