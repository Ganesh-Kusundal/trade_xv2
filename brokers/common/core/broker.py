"""DEPRECATED: This module is no longer used. Kept for backward compatibility only.

The Broker ABC has been replaced by broker-specific gateway classes:
- Dhan: brokers.dhan.gateway.BrokerGateway
- Paper: brokers.paper.PaperGateway
- Upstox: brokers.upstox.gateway.UpstoxBrokerGateway

All gateways now implement the MarketDataGateway ABC from brokers.common.gateway.
"""

from __future__ import annotations

import warnings
from datetime import date
from decimal import Decimal

from pandas import DataFrame


def _deprecated():
    warnings.warn(
        "brokers.common.core.broker.Broker is deprecated. "
        "Use brokers.common.gateway.MarketDataGateway instead.",
        DeprecationWarning,
        stacklevel=3,
    )


class Broker:
    """DEPRECATED: Use MarketDataGateway instead.

    This class is kept for backward compatibility only.
    All new code should use brokers.common.gateway.MarketDataGateway.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _deprecated()

    @property
    def name(self) -> str:
        _deprecated()
        return ""

    @property
    def broker_id(self) -> str:
        _deprecated()
        return ""

    def connect(self) -> None:
        _deprecated()

    def disconnect(self) -> None:
        _deprecated()

    def is_connected(self) -> bool:
        _deprecated()
        return False

    def get_historical_data(self, symbol: str, timeframe: str, start: date, end: date) -> DataFrame:
        _deprecated()
        return DataFrame()

    def get_quote(self, symbol: str) -> dict:
        _deprecated()
        return {}

    def get_option_chain(self, underlying: str, expiry: date) -> DataFrame:
        _deprecated()
        return DataFrame()

    def get_market_depth(self, symbol: str) -> DataFrame:
        _deprecated()
        return DataFrame()

    def place_order(self, symbol: str, side: str, quantity: int, price: Decimal, order_type: str) -> object:
        _deprecated()
        return None

    def get_order(self, order_id: str) -> object:
        _deprecated()
        return None

    def get_orders(self) -> list:
        _deprecated()
        return []

    def cancel_order(self, order_id: str) -> bool:
        _deprecated()
        return False

    def get_positions(self) -> list:
        _deprecated()
        return []

    def get_holdings(self) -> list:
        _deprecated()
        return []

    def get_fund_limits(self) -> object:
        _deprecated()
        return None

    def get_trades(self) -> list:
        _deprecated()
        return []
