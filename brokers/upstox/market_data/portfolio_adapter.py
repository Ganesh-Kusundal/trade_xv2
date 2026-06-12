"""Upstox portfolio adapter — implements ``PortfolioProvider`` port."""

from __future__ import annotations

from datetime import date
from typing import Any

from brokers.common.api.ports import PortfolioProvider
from brokers.common.core.models import FundLimits, Holding, Position
from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
from brokers.upstox.market_data.portfolio_client import UpstoxPortfolioClient


class UpstoxPortfolioAdapter(PortfolioProvider):
    def __init__(self, client: UpstoxPortfolioClient) -> None:
        self._client = client

    def get_positions(self) -> list[Position]:
        rows = self._client.get_short_term_positions()
        return [UpstoxDomainMapper.to_position(r) for r in rows]

    def get_holdings(self) -> list[Holding]:
        rows = self._client.get_long_term_holdings()
        return [UpstoxDomainMapper.to_holding(r) for r in rows]

    def get_fund_limits(self) -> FundLimits:
        return UpstoxDomainMapper.to_fund_limits(self._client.get_funds())

    def get_profile(self) -> dict[str, Any]:
        return self._client.get_profile()

    def get_ledger(self, from_date: date, to_date: date) -> list[dict[str, Any]]:
        return []
