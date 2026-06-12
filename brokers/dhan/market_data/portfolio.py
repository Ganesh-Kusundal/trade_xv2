"""Portfolio client — positions, holdings, funds, ledger, profile.

Design reference: Trade_J ``DhanPortfolioProvider``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from brokers.common.core.models import FundLimits, Holding, Position
from brokers.common.resilience.retry import RetryExecutor
from brokers.dhan.mapper.mapping import (
    decimal_field,
    decimal_value,
    first_present,
    int_field,
    list_data,
    response_data,
    str_field,
)


class DhanPortfolioClient:
    """Portfolio, funds, ledger, and profile endpoints."""

    def __init__(
        self,
        http_client: Any,
        settings: Any,
        url_resolver: Any,
        retry_executor: RetryExecutor,
    ) -> None:
        self._http_client = http_client
        self._settings = settings
        self._url_resolver = url_resolver
        self._retry_executor = retry_executor

    # ── Portfolio ───────────────────────────────────────────────────

    def get_positions(self) -> list[Position]:
        response = self._retry_executor.execute(
            lambda: self._http_client.get_json(self._url_resolver.positions_url())
        )
        return [self._position(item) for item in list_data(response)]

    def get_holdings(self) -> list[Holding]:
        response = self._retry_executor.execute(
            lambda: self._http_client.get_json(self._url_resolver.holdings_url())
        )
        return [self._holding(item) for item in list_data(response)]

    def get_fund_limits(self) -> FundLimits:
        response = self._retry_executor.execute(
            lambda: self._http_client.get_json(self._url_resolver.fund_limit_url())
        )
        data = response_data(response, response)
        return FundLimits(
            available_balance=decimal_value(
                first_present(data, "availableBalance", "available_balance")
            ),
            used_margin=decimal_value(first_present(data, "usedMargin", "used_margin")),
            total_margin=decimal_value(first_present(data, "totalMargin", "total_margin")),
        )

    def get_profile(self) -> dict[str, Any]:
        response = self._retry_executor.execute(
            lambda: self._http_client.get_json(self._url_resolver.profile_url())
        )
        return response.get("data", response)

    def get_ledger(self, from_date: date, to_date: date) -> list[dict[str, Any]]:
        response = self._retry_executor.execute(
            lambda: self._http_client.get_json(self._url_resolver.ledger_url(from_date, to_date))
        )
        return list_data(response)

    # ── Mappers ─────────────────────────────────────────────────────

    def _position(self, item: dict[str, Any]) -> Position:
        return Position(
            exchange_segment=str_field(item, "exchangeSegment", default="NSE_EQ"),
            quantity=int_field(item, "netQuantity", "quantity"),
            buy_quantity=int_field(item, "buyQuantity"),
            sell_quantity=int_field(item, "sellQuantity"),
            buy_average_price=decimal_field(item, "buyAveragePrice"),
            sell_average_price=decimal_field(item, "sellAveragePrice"),
            net_quantity=int_field(item, "netQuantity"),
            net_value=decimal_field(item, "netValue"),
            unrealized_pnl=decimal_field(item, "unrealizedPnl"),
            realized_pnl=decimal_field(item, "realizedPnl"),
            product_type=str_field(item, "productType", default="INTRADAY"),
        )

    def _holding(self, item: dict[str, Any]) -> Holding:
        return Holding(
            exchange_segment=str_field(item, "exchangeSegment", default="NSE_EQ"),
            quantity=int_field(item, "quantity"),
            available_quantity=int_field(item, "availableQuantity"),
            cost_price=decimal_field(item, "costPrice"),
            last_price=decimal_field(item, "lastPrice"),
            pnl_value=decimal_field(item, "pnlValue"),
        )
