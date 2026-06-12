"""BrokerFacade — adapts any BrokerConnection into the Broker ABC interface.

Allows new broker adapters to implement only BrokerConnection (capability-based),
then wraps them with this facade for consumers that need the Broker ABC
(DataFrames + domain types).

Usage::

    conn = SomeBrokerConnection(...)
    conn.connect()
    facade = BrokerFacade(conn)
    df = facade.get_historical_data("RELIANCE", "NSE", from_date, to_date)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from brokers.common.core import mappers
from brokers.common.core.broker import Broker
from brokers.common.core.connection import BrokerConnection, Capability
from brokers.common.core.domain import (
    FundLimits,
    Holding,
    Order,
    OrderResponse,
    Position,
    Side,
    Trade,
)


class BrokerFacade(Broker):
    """Wraps a BrokerConnection to satisfy the Broker ABC.

    Delegates to capability providers discovered at runtime.
    Market data methods return DataFrames; trading methods return domain objects.
    """

    def __init__(self, connection: BrokerConnection) -> None:
        self._conn = connection

    @property
    def connection(self) -> BrokerConnection:
        return self._conn

    @property
    def name(self) -> str:
        return self._conn.name

    @property
    def broker_id(self) -> str:
        return self._conn.broker_id

    def connect(self) -> bool:
        return self._conn.connect()

    def disconnect(self) -> bool:
        return self._conn.disconnect()

    def is_connected(self) -> bool:
        return self._conn.status.is_connected()

    def _provider(self, cap: Capability) -> Any:
        p = self._conn.get_capability(cap)
        if p is None:
            raise NotImplementedError(f"Broker '{self.name}' lacks capability: {cap.value}")
        return p

    # ── Market data (DataFrames) ──────────────────────────────────

    def get_historical_data(
        self, symbol: str, exchange: str, from_date: date, to_date: date, timeframe: str = "1d"
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "Historical data via capability providers requires broker-specific mapping"
        )

    def get_quote(self, symbol: str, exchange: str) -> pd.DataFrame:
        raise NotImplementedError(
            "Quote DataFrame via capability providers requires broker-specific mapping"
        )

    def get_option_chain(self, underlying: str, exchange: str, expiry: str) -> pd.DataFrame:
        raise NotImplementedError(
            "Option chain DataFrame via capability providers requires broker-specific mapping"
        )

    def get_market_depth(self, symbol: str, exchange: str) -> pd.DataFrame:
        raise NotImplementedError(
            "Market depth DataFrame via capability providers requires broker-specific mapping"
        )

    # ── Trading (domain objects) ──────────────────────────────────

    def place_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        price: Decimal = Decimal("0"),
        order_type: str = "MARKET",
        product_type: str = "INTRADAY",
        validity: str = "DAY",
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str | None = None,
    ) -> OrderResponse:
        raise NotImplementedError(
            "place_order via facade requires broker-specific order construction"
        )

    def get_order(self, order_id: str) -> Order | None:
        query = self._provider(Capability.ORDER_QUERY)
        raw = query.get_order(order_id)
        if raw is None:
            return None
        return mappers.order_to_domain(raw)

    def get_orders(self) -> list[Order]:
        query = self._provider(Capability.ORDER_QUERY)
        return mappers.order_list_to_domain(query.get_order_list())

    def cancel_order(self, order_id: str) -> bool:
        cmd = self._provider(Capability.ORDER_COMMAND)
        return cmd.cancel_order(order_id)

    # ── Portfolio (domain objects) ────────────────────────────────

    def get_positions(self) -> list[Position]:
        portfolio = self._provider(Capability.PORTFOLIO)
        return mappers.position_list_to_domain(portfolio.get_positions())

    def get_holdings(self) -> list[Holding]:
        portfolio = self._provider(Capability.PORTFOLIO)
        return mappers.holding_list_to_domain(portfolio.get_holdings())

    def get_fund_limits(self) -> FundLimits:
        portfolio = self._provider(Capability.PORTFOLIO)
        return mappers.fund_limits_to_domain(portfolio.get_fund_limits())

    def get_trades(self) -> list[Trade]:
        query = self._provider(Capability.ORDER_QUERY)
        return mappers.trade_list_to_domain(query.get_trades())
