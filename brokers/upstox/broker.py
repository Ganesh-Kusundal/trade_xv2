"""Upstox broker facade — instantiates every adapter from the resolved
``UpstoxConnectionSettings`` + ``UpstoxTokenManager`` and registers the
combined capability set on the ``BrokerConnection``.

Mirrors Trade_J ``UpstoxBrokerConnection`` + ``UpstoxBrokerConnectionFactory``.
"""

from __future__ import annotations

import logging
from typing import Any

from brokers.common.core.connection import BrokerConnection, Capability, ConnectionStatus
from brokers.common.services.historical_data import HistoricalDataService
from brokers.upstox.auth.config import UpstoxConnectionSettings
from brokers.upstox.auth.context import UpstoxAdapterContext
from brokers.upstox.auth.token_manager import UpstoxTokenManager
from brokers.upstox.instruments.loader import UpstoxInstrumentLoader
from brokers.upstox.instruments.resolver import UpstoxInstrumentResolver
from brokers.upstox.instruments.search import UpstoxInstrumentSearch
from brokers.upstox.kill_switch.adapter import UpstoxKillSwitchAdapter
from brokers.upstox.kill_switch.client import UpstoxKillSwitchClient
from brokers.upstox.market_data.client_v2 import UpstoxMarketDataV2Client
from brokers.upstox.market_data.client_v3 import UpstoxMarketDataV3Client
from brokers.upstox.market_data.expired_options import UpstoxExpiredInstrumentsClient
from brokers.upstox.market_data.futures import UpstoxFuturesClient
from brokers.upstox.market_data.futures_adapter import UpstoxFuturesAdapter
from brokers.upstox.market_data.historical_v2 import UpstoxHistoricalV2Client
from brokers.upstox.market_data.historical_v3 import UpstoxHistoricalV3Client
from brokers.upstox.market_data.margin import UpstoxMarginClient
from brokers.upstox.market_data.margin_adapter import UpstoxMarginAdapter
from brokers.upstox.market_data.market_data_adapter import UpstoxMarketDataAdapter
from brokers.upstox.market_data.market_status import UpstoxMarketStatusClient
from brokers.upstox.market_data.market_status_adapter import UpstoxMarketStatusAdapter
from brokers.upstox.market_data.options_adapter import UpstoxOptionsAdapter
from brokers.upstox.market_data.options_client import UpstoxOptionsClient
from brokers.upstox.market_data.portfolio_adapter import UpstoxPortfolioAdapter
from brokers.upstox.market_data.portfolio_client import UpstoxPortfolioClient
from brokers.upstox.market_intelligence.adapter import UpstoxMarketIntelligenceAdapter
from brokers.upstox.market_intelligence.client import UpstoxMarketIntelligenceClient
from brokers.upstox.market_intelligence.snapshot import UpstoxMarketIntelligenceSnapshotBuilder
from brokers.upstox.news.adapter import UpstoxNewsAdapter
from brokers.upstox.news.client import UpstoxNewsClient
from brokers.upstox.orders.alert_adapter import UpstoxAlertAdapter
from brokers.upstox.orders.cover_order_adapter import UpstoxCoverOrderAdapter
from brokers.upstox.orders.gtt_adapter import UpstoxGttAdapter
from brokers.upstox.orders.gtt_client import UpstoxGttClient
from brokers.upstox.orders.idempotency import InMemoryIdempotencyCache
from brokers.upstox.orders.order_client import UpstoxRestOrderClient
from brokers.upstox.orders.order_command_adapter import UpstoxOrderCommandAdapter
from brokers.upstox.orders.order_query_adapter import UpstoxOrderQueryAdapter
from brokers.upstox.orders.slice_adapter import UpstoxSliceAdapter
from brokers.upstox.reconciliation.service import UpstoxReconciliationService
from brokers.upstox.static_ip.adapter import UpstoxStaticIpAdapter
from brokers.upstox.static_ip.client import UpstoxStaticIpClient
from brokers.upstox.websocket.feed_authorizer import UpstoxFeedAuthorizer
from brokers.upstox.websocket.market_data_v3 import UpstoxMarketDataV3Multiplexer
from brokers.upstox.websocket.v3_auto_reconnect import UpstoxAutoReconnect
from brokers.upstox.websocket.v3_decoder import UpstoxV3Decoder
from brokers.upstox.websocket.v3_subscription_manager import UpstoxV3SubscriptionLimits

logger = logging.getLogger(__name__)


class UpstoxBroker(BrokerConnection):
    def __init__(
        self,
        settings: UpstoxConnectionSettings | None = None,
        *,
        token_manager: UpstoxTokenManager | None = None,
        oms: Any = None,
    ) -> None:
        if settings is None:
            settings = UpstoxConnectionSettings(client_id="placeholder")
        super().__init__(name="upstox", broker_id=settings.client_id)
        self.settings = settings
        self._token_manager = token_manager or UpstoxTokenManager(settings=settings)
        self.context = UpstoxAdapterContext(
            settings=settings,
            token_provider=self._token_manager.bearer_token,
            token_manager=self._token_manager,
        )
        self._oms = oms

        self.instrument_resolver = UpstoxInstrumentResolver()
        self.instrument_loader = UpstoxInstrumentLoader()
        self.instrument_search = UpstoxInstrumentSearch(self.context.http_client)

        self.market_data_v2 = UpstoxMarketDataV2Client(
            self.context.http_client, self.context.url_resolver
        )
        self.market_data_v3 = UpstoxMarketDataV3Client(
            self.context.http_client, self.context.url_resolver
        )
        self.historical_v2 = UpstoxHistoricalV2Client(
            self.context.http_client, self.context.url_resolver
        )
        self.historical_v3 = UpstoxHistoricalV3Client(
            self.context.http_client, self.context.url_resolver
        )
        self.options_client = UpstoxOptionsClient(
            self.context.http_client, self.context.url_resolver
        )
        self.portfolio_client = UpstoxPortfolioClient(
            self.context.http_client, self.context.url_resolver
        )
        self.margin_client = UpstoxMarginClient(self.context.http_client, self.context.url_resolver)
        self.market_status_client = UpstoxMarketStatusClient(
            self.context.http_client, self.context.url_resolver
        )
        self.futures_client = UpstoxFuturesClient(
            self.context.http_client, self.context.url_resolver
        )
        self.expired_instruments_client = UpstoxExpiredInstrumentsClient(
            self.context.http_client, self.context.url_resolver
        )
        self.gtt_client = UpstoxGttClient(self.context.http_client, self.context.url_resolver)
        self.news_client = UpstoxNewsClient(self.context.http_client, self.context.url_resolver)
        self.intelligence_client = UpstoxMarketIntelligenceClient(
            self.context.http_client, self.context.url_resolver
        )
        self.kill_switch_client = UpstoxKillSwitchClient(
            self.context.http_client, self.context.url_resolver
        )
        self.static_ip_client = UpstoxStaticIpClient(
            self.context.http_client, self.context.url_resolver
        )
        self.order_client = UpstoxRestOrderClient(
            self.context.http_client, self.context.url_resolver
        )

        # Adapters
        self.market_data = UpstoxMarketDataAdapter(
            self.market_data_v2, self.market_data_v3, self.historical_v2
        )
        self.market_data_v3_adapter = self.market_data  # alias
        self.options = UpstoxOptionsAdapter(self.options_client)
        self.portfolio = UpstoxPortfolioAdapter(self.portfolio_client)
        self.margin = UpstoxMarginAdapter(self.margin_client)
        self.market_status = UpstoxMarketStatusAdapter(self.market_status_client)
        self.futures = UpstoxFuturesAdapter(self.futures_client)
        self.news = UpstoxNewsAdapter(self.news_client)
        self.intelligence = UpstoxMarketIntelligenceAdapter(self.intelligence_client)
        self.intelligence_snapshot = UpstoxMarketIntelligenceSnapshotBuilder(
            self.intelligence_client
        )
        self.kill_switch = UpstoxKillSwitchAdapter(self.kill_switch_client)
        self.static_ip = UpstoxStaticIpAdapter(self.static_ip_client)

        # Orders
        self.idempotency_cache = InMemoryIdempotencyCache()
        self.order_command = UpstoxOrderCommandAdapter(
            self.order_client,
            self.instrument_resolver,
            self.idempotency_cache,
            use_v3=True,
            algo_name=settings.algo_name or None,
            market_protection_default=settings.market_protection_default,
        )
        self.order_query = UpstoxOrderQueryAdapter(self.order_client, self.instrument_resolver)
        self.gtt = UpstoxGttAdapter(self.gtt_client)
        self.slice = UpstoxSliceAdapter(self.order_client, self.instrument_resolver)
        self.cover = UpstoxCoverOrderAdapter(self.order_client)
        self.alert = UpstoxAlertAdapter(self.gtt)

        # WebSocket
        self.feed_authorizer = UpstoxFeedAuthorizer(
            self.context.http_client, self.context.url_resolver
        )
        ws_limits = (
            UpstoxV3SubscriptionLimits.for_plus_plan()
            if settings.ws_plus_plan
            else UpstoxV3SubscriptionLimits()
        )
        self.market_data_websocket = UpstoxMarketDataV3Multiplexer(
            authorizer=self.feed_authorizer,
            decoder=UpstoxV3Decoder(),
            limits=ws_limits,
            auto_reconnect=UpstoxAutoReconnect(
                enabled=settings.ws_auto_reconnect,
                interval_seconds=settings.ws_reconnect_interval_s,
                max_retries=settings.ws_reconnect_max_retries,
            ),
        )

        # Shared historical data service
        self.historical_service = HistoricalDataService(
            self.market_data_v2,
            parquet_cache_path=settings.instrument_cache_path,
        )

        # Reconciliation
        self.reconciliation_service = UpstoxReconciliationService(
            self.order_client, self.portfolio_client, oms=self._oms, auto_repair=False
        )

        self._register_all_capabilities()

    def _register_all_capabilities(self) -> None:
        self._register_capability(Capability.MARKET_DATA, self.market_data)
        self._register_capability(Capability.DEPTH, self.market_data)
        self._register_capability(Capability.ORDER_COMMAND, self.order_command)
        self._register_capability(Capability.ORDER_QUERY, self.order_query)
        self._register_capability(Capability.PORTFOLIO, self.portfolio)
        self._register_capability(Capability.OPTIONS_CHAIN, self.options)
        self._register_capability(Capability.FUTURES, self.futures)
        self._register_capability(Capability.HISTORICAL_DATA, self.market_data)
        self._register_capability(Capability.MARGIN, self.margin)
        self._register_capability(Capability.INSTRUMENTS, self.instrument_resolver)
        self._register_capability(Capability.MARKET_STATUS, self.market_status)
        self._register_capability(Capability.GTT_ORDER, self.gtt)
        self._register_capability(Capability.SLICE_ORDER, self.slice)
        self._register_capability(Capability.ORDER_SLICING, self.slice)
        self._register_capability(Capability.COVER_ORDER, self.cover)
        self._register_capability(Capability.ALERTS, self.alert)
        self._register_capability(Capability.WEBSOCKET, self.market_data_websocket)
        self._register_capability(Capability.IDEMPOTENCY, self.idempotency_cache)
        self._register_capability(Capability.NEWS, self.news)
        self._register_capability(Capability.MARKET_INTELLIGENCE, self.intelligence)
        self._register_capability(Capability.KILL_SWITCH, self.kill_switch)
        self._register_capability(Capability.STATIC_IP, self.static_ip)
        self._register_capability(Capability.PORTFOLIO_STREAM, self.market_data_websocket)
        self._register_capability(Capability.WEBHOOKS, self.feed_authorizer)
        self._register_capability(Capability.OPTION_GREEKS, self.intelligence)

    def connect(self) -> bool:
        try:
            self._token_manager.bootstrap()
            self._set_status(ConnectionStatus.CONNECTED)
            return True
        except Exception as exc:
            logger.warning("Upstox connect failed: %s", exc)
            self._set_status(ConnectionStatus.DISCONNECTED)
            return False

    def disconnect(self) -> bool:
        self._set_status(ConnectionStatus.DISCONNECTED)
        return True

    def reconnect(self) -> bool:
        return self.connect()
