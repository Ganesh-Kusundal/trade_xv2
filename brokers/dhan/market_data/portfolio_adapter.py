"""Portfolio adapter for Dhan."""

from __future__ import annotations

from datetime import date
from typing import Any

from brokers.common.api.ports import PortfolioProvider
from brokers.common.core.models import FundLimits, Holding, Position
from brokers.dhan.market_data.portfolio import DhanPortfolioClient


class DhanPortfolioProvider(PortfolioProvider):
    """Trade_J-style portfolio adapter over ``DhanPortfolioClient``."""

    def __init__(self, portfolio_client: DhanPortfolioClient) -> None:
        self._portfolio_client = portfolio_client

    @property
    def portfolio_client(self) -> DhanPortfolioClient:
        return self._portfolio_client

    def get_positions(self) -> list[Position]:
        return self._portfolio_client.get_positions()

    def get_holdings(self) -> list[Holding]:
        return self._portfolio_client.get_holdings()

    def get_fund_limits(self) -> FundLimits:
        return self._portfolio_client.get_fund_limits()

    def get_profile(self) -> dict[str, Any]:
        return self._portfolio_client.get_profile()

    def get_ledger(self, from_date: date, to_date: date) -> list[dict[str, Any]]:
        return self._portfolio_client.get_ledger(from_date, to_date)
