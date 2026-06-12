"""DhanHQ broker adapter package.

Mirrors Trade_J's ``broker/dhan`` layout:

- ``broker``        — ``DhanBroker`` facade (Trade_J DhanBrokerConnection)
- ``auth``          — ``DhanAuthClient``, ``DhanTokenManager``, ``read_secret_file``
- ``config``        — ``DhanConnectionSettings``, ``DhanSettingsLoader``
- ``context``       — ``DhanAdapterContext`` (settings container)
- ``client``        — ``DhanClientHolder`` (token rotation callbacks)
- ``http``          — ``DhanAuthenticatedHttpClient``
- ``urls``          — ``DhanApiUrlResolver``
- ``instruments``   — ``DhanInstrumentDefinition``, ``DhanInstrumentResolver``
- ``orders``        — ``DhanRestOrderClient``
- ``market_data``   — ``DhanMarketDataClient``
- ``portfolio``     — ``DhanPortfolioClient``
- ``options``       — ``DhanOptionsClient``
- ``margin``        — ``DhanMarginClient``
- ``validator``     — ``DhanOrderValidator``, ``OrderPreview``
- ``exceptions``    — ``DhanApiError``
"""

from __future__ import annotations

# Facade
# Auth (moved from broker/dhan_auth.py)
from brokers.dhan.auth.auth import (
    DhanAuthClient,
    DhanAuthRejected,
    DhanHttpError,
    DhanTokenInfo,
    DhanTokenManager,
    DhanTokenState,
    read_secret_file,
)

# Config (moved from broker/dhan_config.py)
from brokers.dhan.auth.config import DhanConnectionSettings, DhanSettingsLoader
from brokers.dhan.auth.context import DhanAdapterContext
from brokers.dhan.auth.http import DhanAuthenticatedHttpClient
from brokers.dhan.auth.urls import DhanApiUrlResolver
from brokers.dhan.broker import DhanBroker
from brokers.dhan.instrument_service import InstrumentService
from brokers.dhan.instruments import DhanInstrumentMixin, ResolvedInstrument

# New split modules
from brokers.dhan.client import DhanClientHolder, TokenRotationListener
from brokers.dhan.exceptions import DhanApiError
from brokers.dhan.mapper.instruments import (
    DhanInstrumentDefinition,
    DhanInstrumentResolver,
)
from brokers.dhan.market_data.margin import DhanMarginClient
from brokers.dhan.market_data.margin_adapter import DhanMarginProvider
from brokers.dhan.market_data.market_data import DhanMarketDataClient
from brokers.dhan.market_data.market_data_adapter import DhanMarketDataProvider
from brokers.dhan.market_data.market_status_adapter import DhanMarketStatusProvider
from brokers.dhan.market_data.options import DhanOptionsClient
from brokers.dhan.market_data.options_adapter import DhanOptionsAdapter
from brokers.dhan.market_data.portfolio import DhanPortfolioClient
from brokers.dhan.market_data.portfolio_adapter import DhanPortfolioProvider
from brokers.dhan.market_data.provider import DhanBrokerProvider
from brokers.dhan.orders.conditional_alert_adapter import DhanConditionalAlertProvider
from brokers.dhan.orders.cover_order_adapter import DhanCoverOrderAdapter
from brokers.dhan.orders.futures_adapter import DhanFuturesAdapter
from brokers.dhan.orders.order_command_adapter import DhanOrderCommandAdapter
from brokers.dhan.orders.order_query_adapter import DhanOrderQueryAdapter
from brokers.dhan.orders.orders import DhanRestOrderClient
from brokers.dhan.orders.session_risk_adapter import DhanSessionRiskProvider
from brokers.dhan.orders.special_orders_adapter import (
    DhanBracketOrderAdapter,
    DhanGttOrderAdapter,
    DhanSliceOrderAdapter,
)
from brokers.dhan.orders.validator import DhanOrderValidator, OrderPreview
from brokers.dhan.websocket.order_stream_adapter import DhanOrderStreamProvider

__all__ = [
    # Split package modules
    "DhanAdapterContext",
    "DhanApiError",
    "DhanApiUrlResolver",
    "DhanAuthClient",
    "DhanAuthRejected",
    "DhanAuthenticatedHttpClient",
    # Adapter layer
    "DhanBracketOrderAdapter",
    # Facade / auth / config (flat-module compat surface)
    "DhanBroker",
    "DhanBrokerProvider",
    "DhanClientHolder",
    "DhanConditionalAlertProvider",
    "DhanConnectionSettings",
    "DhanCoverOrderAdapter",
    "DhanFuturesAdapter",
    "DhanGttOrderAdapter",
    "DhanHttpError",
    "DhanInstrumentDefinition",
    "DhanInstrumentMixin",
    "DhanInstrumentResolver",
    "InstrumentService",
    "ResolvedInstrument",
    "DhanMarginClient",
    "DhanMarginProvider",
    "DhanMarketDataClient",
    "DhanMarketDataProvider",
    "DhanMarketStatusProvider",
    "DhanOptionsAdapter",
    "DhanOptionsClient",
    "DhanOrderCommandAdapter",
    "DhanOrderQueryAdapter",
    "DhanOrderStreamProvider",
    "DhanOrderValidator",
    "DhanPortfolioClient",
    "DhanPortfolioProvider",
    "DhanRestOrderClient",
    "DhanSessionRiskProvider",
    "DhanSettingsLoader",
    "DhanSliceOrderAdapter",
    "DhanTokenInfo",
    "DhanTokenManager",
    "DhanTokenState",
    "OrderPreview",
    "TokenRotationListener",
    "read_secret_file",
]
