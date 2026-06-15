"""DEPRECATED: BrokerFacade is no longer used. Kept for backward compatibility only.

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
from typing import Any

import pandas as pd


def _deprecated():
    warnings.warn(
        "brokers.common.core.facade.BrokerFacade is deprecated. "
        "Use brokers.common.gateway.MarketDataGateway instead.",
        DeprecationWarning,
        stacklevel=3,
    )


class BrokerFacade:
    """DEPRECATED: Use MarketDataGateway instead.

    This class is kept for backward compatibility only.
    All new code should use brokers.common.gateway.MarketDataGateway.
    """

    def __init__(self, connection: Any = None) -> None:
        _deprecated()
        self._conn = connection

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

    def get_historical_data(self, symbol: str, timeframe: str, start: date, end: date) -> pd.DataFrame:
        _deprecated()
        return pd.DataFrame()

    def get_quote(self, symbol: str) -> dict:
        _deprecated()
        return {}

    def get_option_chain(self, underlying: str, expiry: date) -> pd.DataFrame:
        _deprecated()
        return pd.DataFrame()

    def get_market_depth(self, symbol: str) -> pd.DataFrame:
        _deprecated()
        return pd.DataFrame()

    def place_order(self, symbol: str, side: str, quantity: int, price: Decimal, order_type: str) -> Any:
        _deprecated()
        return None

    def get_order(self, order_id: str) -> Any:
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

    def get_fund_limits(self) -> Any:
        _deprecated()
        return None

    def get_trades(self) -> list:
        _deprecated()
        return []
