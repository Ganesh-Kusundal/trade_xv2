"""Factory for creating Dhan adapter instances — extracted from DhanBroker.__init__.

Centralises all adapter construction so DhanBroker.__init__ stays lean
and tests can inject mock factories.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Dict, Optional

from brokers.common.resilience.retry import RetryExecutor
from brokers.dhan.auth.config import DhanConnectionSettings
from brokers.dhan.auth.context import DhanAdapterContext
from brokers.dhan.auth.http import DhanAuthenticatedHttpClient
from brokers.dhan.auth.urls import DhanApiUrlResolver
from brokers.dhan.instrument_service import InstrumentService
from brokers.dhan.market_data.margin import DhanMarginClient
from brokers.dhan.market_data.margin_adapter import DhanMarginProvider
from brokers.dhan.market_data.market_data import DhanMarketDataClient
from brokers.dhan.market_data.market_data_adapter import DhanMarketDataProvider
from brokers.dhan.market_data.market_status_adapter import DhanMarketStatusProvider
from brokers.dhan.market_data.options import DhanOptionsClient
from brokers.dhan.market_data.options_adapter import DhanOptionsAdapter
from brokers.dhan.market_data.portfolio import DhanPortfolioClient
from brokers.dhan.market_data.portfolio_adapter import DhanPortfolioProvider
from brokers.dhan.orders.conditional_alert_adapter import DhanConditionalAlertProvider
from brokers.dhan.orders.cover_order_adapter import DhanCoverOrderAdapter
from brokers.dhan.orders.futures_adapter import DhanFuturesAdapter
from brokers.dhan.orders.idempotency import InMemoryIdempotencyCache
from brokers.dhan.orders.order_command_adapter import DhanOrderCommandAdapter
from brokers.dhan.orders.order_query_adapter import DhanOrderQueryAdapter
from brokers.dhan.orders.orders import DhanRestOrderClient
from brokers.dhan.orders.session_risk_adapter import DhanSessionRiskProvider
from brokers.dhan.orders.special_orders_adapter import (
    DhanBracketOrderAdapter,
    DhanGttOrderAdapter,
    DhanSliceOrderAdapter,
)
from brokers.dhan.orders.validator import DhanOrderValidator
from brokers.dhan.websocket.order_stream_adapter import DhanOrderStreamProvider


class DhanAdapterFactory:
    """Creates all Dhan adapter instances from shared dependencies.

    Usage::

        factory = DhanAdapterFactory(
            http_client=http,
            url_resolver=urls,
            instrument_service=service,
            executors=executors,
            settings=settings,
            token_provider=token_fn,
        )
        adapters = factory.create_all()
        # adapters["order_command"] → DhanOrderCommandAdapter
        # adapters["market_data"]   → DhanMarketDataProvider
        # ...
    """

    def __init__(
        self,
        http_client: DhanAuthenticatedHttpClient,
        url_resolver: DhanApiUrlResolver,
        executors: dict[str, RetryExecutor],
        settings: DhanConnectionSettings,
        token_provider: Callable[[], str],
        instrument_service: InstrumentService,
    ) -> None:
        self._http = http_client
        self._urls = url_resolver
        self._instrument_service = instrument_service
        self._executors = executors
        self._settings = settings
        self._token_provider = token_provider

    def create_all(self) -> dict[str, Any]:
        """Build all adapter instances and return them keyed by capability name."""
        # REST clients
        order_client = DhanRestOrderClient(
            self._http,
            self._settings,
            self._urls,
            self._instrument_service,
            self._executors["orders"],
        )
        market_data_client = DhanMarketDataClient(
            self._http,
            self._settings,
            self._urls,
            self._executors["quotes"],
        )
        portfolio_client = DhanPortfolioClient(
            self._http,
            self._settings,
            self._urls,
            self._executors["data"],
        )
        options_client = DhanOptionsClient(
            self._http,
            self._settings,
            self._urls,
            self._executors["quotes"],
        )
        margin_client = DhanMarginClient(
            self._http,
            self._settings,
            self._urls,
            self._executors["data"],
        )

        # Validator + cache
        validator = DhanOrderValidator(self._instrument_service, self._settings)
        idempotency_cache = InMemoryIdempotencyCache()

        # Capability adapters
        order_command = DhanOrderCommandAdapter(
            order_client,
            self._instrument_service,
            validator,
            idempotency_cache,
        )
        order_query = DhanOrderQueryAdapter(order_client)
        bracket_order = DhanBracketOrderAdapter(order_client)
        cover_order = DhanCoverOrderAdapter()
        gtt_order = DhanGttOrderAdapter(order_client)
        slice_order = DhanSliceOrderAdapter(order_client)
        session_risk = DhanSessionRiskProvider(
            self._http,
            self._urls,
            self._executors["orders"],
        )
        conditional_alert = DhanConditionalAlertProvider(
            self._http,
            self._urls,
            self._instrument_service,
            self._executors["orders"],
        )
        futures = DhanFuturesAdapter(self._instrument_service)

        order_stream = DhanOrderStreamProvider(
            context=DhanAdapterContext(
                settings=self._settings,
                token_provider=self._token_provider,
                timeout_seconds=15,
            ),
        )

        market_data = DhanMarketDataProvider(
            market_data_client,
            options_client,
            order_stream_provider=order_stream,
        )
        portfolio = DhanPortfolioProvider(portfolio_client)
        options = DhanOptionsAdapter(options_client)
        margin = DhanMarginProvider(margin_client)
        market_status = DhanMarketStatusProvider()

        return {
            "order_command": order_command,
            "order_query": order_query,
            "bracket_order": bracket_order,
            "cover_order": cover_order,
            "gtt_order": gtt_order,
            "slice_order": slice_order,
            "session_risk": session_risk,
            "conditional_alert": conditional_alert,
            "futures": futures,
            "order_stream": order_stream,
            "market_data": market_data,
            "portfolio": portfolio,
            "options": options,
            "margin": margin,
            "market_status": market_status,
            "idempotency_cache": idempotency_cache,
            "order_validator": validator,
            # Raw clients (for advanced / direct access)
            "order_client": order_client,
            "market_data_client": market_data_client,
            "portfolio_client": portfolio_client,
            "options_client": options_client,
            "margin_client": margin_client,
        }
