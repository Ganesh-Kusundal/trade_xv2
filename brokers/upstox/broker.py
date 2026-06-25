"""Upstox broker facade — instantiates every adapter from the resolved
``UpstoxConnectionSettings`` + ``UpstoxTokenManager`` and exposes them
as direct attributes.

This is a plain class (no ABC base). The ``UpstoxBrokerGateway`` wrapper
implements the ``MarketDataGateway`` contract; this class provides the
adapter wiring.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from application.oms.risk_manager import RiskManager
from brokers.common.services.historical_data import HistoricalDataService
from brokers.upstox.auth.config import UpstoxConnectionSettings
from brokers.upstox.auth.context import UpstoxAdapterContext
from brokers.upstox.auth.token_manager import UpstoxTokenManager
from brokers.upstox.capabilities import (
    InstrumentsCapability,
    MarketDataCapability,
    OrdersCapability,
    PortfolioCapability,
    StreamingCapability,
)
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
from brokers.upstox.orders.alert_adapter import UpstoxAlertAdapter
from brokers.upstox.orders.cover_order_adapter import UpstoxCoverOrderAdapter
from brokers.upstox.orders.exit_all_adapter import UpstoxExitAllAdapter
from brokers.upstox.orders.gtt_adapter import UpstoxGttAdapter
from brokers.upstox.orders.gtt_client import UpstoxGttClient
from brokers.upstox.orders.idempotency import InMemoryIdempotencyCache
from brokers.upstox.orders.order_client import UpstoxRestOrderClient
from brokers.upstox.orders.order_command_adapter import UpstoxOrderCommandAdapter
from brokers.upstox.orders.order_query_adapter import UpstoxOrderQueryAdapter
from brokers.upstox.orders.slice_adapter import UpstoxSliceAdapter
from brokers.upstox.reconciliation.service import UpstoxReconciliationService
from brokers.upstox.websocket.feed_authorizer import UpstoxFeedAuthorizer
from brokers.upstox.websocket.market_data_v3 import UpstoxMarketDataV3Multiplexer
from brokers.upstox.websocket.portfolio_stream import UpstoxPortfolioStream
from brokers.upstox.websocket.v3_auto_reconnect import UpstoxAutoReconnect
from brokers.upstox.websocket.v3_decoder import UpstoxV3Decoder
from brokers.upstox.websocket.v3_subscription_manager import UpstoxV3SubscriptionLimits
from domain import Capability, ConnectionStatus
from infrastructure.event_bus import EventBus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _UpstoxCapabilities:
    market_data: MarketDataCapability
    orders: OrdersCapability
    portfolio: PortfolioCapability
    instruments: InstrumentsCapability
    streaming: StreamingCapability


# Core adapters required for orders, market data, and portfolio paths.
_CORE_ADAPTER_REGISTRY: list[tuple[str, type, type, Capability | None]] = [
    ("portfolio", UpstoxPortfolioClient, UpstoxPortfolioAdapter, Capability.PORTFOLIO),
    ("margin", UpstoxMarginClient, UpstoxMarginAdapter, Capability.MARGIN),
    ("options", UpstoxOptionsClient, UpstoxOptionsAdapter, Capability.OPTIONS_CHAIN),
    ("futures", UpstoxFuturesClient, UpstoxFuturesAdapter, Capability.FUTURES),
    (
        "market_status",
        UpstoxMarketStatusClient,
        UpstoxMarketStatusAdapter,
        Capability.MARKET_STATUS,
    ),
    ("kill_switch", UpstoxKillSwitchClient, UpstoxKillSwitchAdapter, Capability.KILL_SWITCH),
    ("gtt", UpstoxGttClient, UpstoxGttAdapter, Capability.GTT_ORDER),
]

# Extended adapters — loaded lazily via :meth:`_ensure_extended`.
_EXTENDED_ADAPTER_REGISTRY: list[tuple[str, str, str, Capability | None]] = [
    (
        "ipo",
        "brokers.upstox.ipo.client",
        "UpstoxIpoClient",
        "brokers.upstox.ipo.adapter",
        "UpstoxIpoAdapter",
        Capability.IPO,
    ),
    (
        "payments",
        "brokers.upstox.payments.client",
        "UpstoxPaymentsClient",
        "brokers.upstox.payments.adapter",
        "UpstoxPaymentsAdapter",
        Capability.PAYMENTS,
    ),
    (
        "mutual_funds",
        "brokers.upstox.mutual_funds.client",
        "UpstoxMutualFundsClient",
        "brokers.upstox.mutual_funds.adapter",
        "UpstoxMutualFundsAdapter",
        Capability.MUTUAL_FUNDS,
    ),
    (
        "fundamentals",
        "brokers.upstox.fundamentals.client",
        "UpstoxFundamentalsClient",
        "brokers.upstox.fundamentals.adapter",
        "UpstoxFundamentalsAdapter",
        Capability.FUNDAMENTALS,
    ),
    (
        "news",
        "brokers.upstox.news.client",
        "UpstoxNewsClient",
        "brokers.upstox.news.adapter",
        "UpstoxNewsAdapter",
        Capability.NEWS,
    ),
    (
        "intelligence",
        "brokers.upstox.market_intelligence.client",
        "UpstoxMarketIntelligenceClient",
        "brokers.upstox.market_intelligence.adapter",
        "UpstoxMarketIntelligenceAdapter",
        Capability.MARKET_INTELLIGENCE,
    ),
    (
        "static_ip",
        "brokers.upstox.static_ip.client",
        "UpstoxStaticIpClient",
        "brokers.upstox.static_ip.adapter",
        "UpstoxStaticIpAdapter",
        Capability.STATIC_IP,
    ),
]


class UpstoxBroker:
    def __init__(
        self,
        settings: UpstoxConnectionSettings | None = None,
        *,
        token_manager: UpstoxTokenManager | None = None,
        oms: Any = None,
        event_bus: EventBus | None = None,
        risk_manager: RiskManager | None = None,
        backfill_callback: Any | None = None,
        reconciliation_service: Any | None = None,
    ) -> None:
        if settings is None:
            settings = UpstoxConnectionSettings(client_id="placeholder")
        self._name = "upstox"
        self._broker_id = settings.client_id
        self._capabilities: set[Capability] = set()
        self._capability_map: dict[Capability, Any] = {}
        self._status: ConnectionStatus = ConnectionStatus.DISCONNECTED
        self.settings = settings
        self._token_manager = token_manager or UpstoxTokenManager(settings=settings)
        self.context = UpstoxAdapterContext(
            settings=settings,
            token_provider=self._token_manager.bearer_token,
            token_manager=self._token_manager,
        )
        self._oms = oms
        self._event_bus = event_bus
        self._risk_manager = risk_manager
        self._backfill_callback = backfill_callback
        self._reconciliation_service = reconciliation_service
        self._extended_ready = False

        self.instrument_resolver = UpstoxInstrumentResolver()
        self.instrument_loader = UpstoxInstrumentLoader()
        self.instrument_search = UpstoxInstrumentSearch(self.context.http_client)

        # ── Standalone clients (no corresponding adapter from registry) ──
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
            self.context.http_client, url_resolver=self.context.url_resolver
        )
        self.order_client = UpstoxRestOrderClient(
            self.context.http_client, self.context.url_resolver
        )
        self.expired_instruments_client = UpstoxExpiredInstrumentsClient(
            self.context.http_client, self.context.url_resolver
        )

        # ── Core registry-driven client + adapter pairs ──
        for name, client_cls, adapter_cls, capability in _CORE_ADAPTER_REGISTRY:
            client = client_cls(self.context.http_client, self.context.url_resolver)
            setattr(self, f"{name}_client", client)

            if name == "options":
                adapter = adapter_cls(client, self.instrument_resolver)
            elif name == "futures":
                futures_client = UpstoxFuturesClient(
                    self.context.http_client,
                    self.context.url_resolver,
                    self.instrument_resolver,
                )
                self.futures_client = futures_client
                adapter = adapter_cls(futures_client)
            else:
                adapter = adapter_cls(client)

            setattr(self, name, adapter)
            if capability is not None:
                self._register_capability(capability, adapter)

        # ── Adapters with non-standard constructors ──
        self.market_data = UpstoxMarketDataAdapter(
            self.market_data_v2, self.market_data_v3, self.historical_v2
        )

        # Orders
        self.idempotency_cache = InMemoryIdempotencyCache()
        self.order_command = UpstoxOrderCommandAdapter(
            self.order_client,
            self.instrument_resolver,
            self.idempotency_cache,
            use_v3=True,
            algo_name=settings.algo_name or None,
            market_protection_default=settings.market_protection_default,
            event_bus=self._event_bus,
            risk_manager=self._risk_manager,
        )
        self.order_query = UpstoxOrderQueryAdapter(self.order_client, self.instrument_resolver)
        # self.gtt created by _CORE_ADAPTER_REGISTRY loop above
        self.slice = UpstoxSliceAdapter(self.order_client, self.instrument_resolver)
        self.cover = UpstoxCoverOrderAdapter(self.order_client)
        self.alert = UpstoxAlertAdapter(self.gtt)
        self.exit_all = UpstoxExitAllAdapter(self.kill_switch_client)

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
            event_bus=self._event_bus,
            backfill_callback=self._backfill_callback,
        )
        self.portfolio_stream = UpstoxPortfolioStream(
            authorizer=self.feed_authorizer,
            event_bus=self._event_bus,
        )

        # Shared historical data service (V2 historical client)
        self.historical_service = HistoricalDataService(
            self.historical_v2,
            parquet_cache_path=settings.instrument_cache_path,
        )

        # Reconciliation
        if reconciliation_service is not None:
            self.reconciliation_service = reconciliation_service
        else:
            self.reconciliation_service = UpstoxReconciliationService(
                self.order_client, self.portfolio_client, oms=self._oms, auto_repair=False
            )

        self.capabilities = _UpstoxCapabilities(
            market_data=MarketDataCapability(
                market_data=self.market_data,
                market_data_v2=self.market_data_v2,
                market_data_v3=self.market_data_v3,
                historical_v2=self.historical_v2,
                historical_v3=self.historical_v3,
                options=self.options,
                futures=self.futures,
                expired_instruments_client=self.expired_instruments_client,
                market_status=self.market_status,
                intelligence=None,
                intelligence_snapshot=None,
            ),
            orders=OrdersCapability(
                order_command=self.order_command,
                order_query=self.order_query,
                slice=self.slice,
                cover=self.cover,
                gtt=self.gtt,
                alert=self.alert,
                exit_all=self.exit_all,
                order_client=self.order_client,
            ),
            portfolio=PortfolioCapability(
                portfolio=self.portfolio,
                margin=self.margin,
                portfolio_client=self.portfolio_client,
                margin_client=self.margin_client,
            ),
            instruments=InstrumentsCapability(
                instrument_resolver=self.instrument_resolver,
                instrument_loader=self.instrument_loader,
                instrument_search=self.instrument_search,
            ),
            streaming=StreamingCapability(
                feed_authorizer=self.feed_authorizer,
                market_data_websocket=self.market_data_websocket,
            ),
        )

        self._register_all_capabilities()

    def _ensure_extended(self) -> None:
        """Load extended adapters on first access (IPO, payments, fundamentals, etc.)."""
        if self._extended_ready:
            return

        import importlib

        for (
            name,
            client_mod,
            client_cls_name,
            adapter_mod,
            adapter_cls_name,
            capability,
        ) in _EXTENDED_ADAPTER_REGISTRY:
            client_cls = getattr(importlib.import_module(client_mod), client_cls_name)
            adapter_cls = getattr(importlib.import_module(adapter_mod), adapter_cls_name)
            client = client_cls(self.context.http_client, self.context.url_resolver)
            setattr(self, f"{name}_client", client)
            adapter = adapter_cls(client)
            setattr(self, name, adapter)
            if capability is not None:
                self._register_capability(capability, adapter)

        snapshot_mod = importlib.import_module("brokers.upstox.market_intelligence.snapshot")
        self.intelligence_snapshot = snapshot_mod.UpstoxMarketIntelligenceSnapshotBuilder(
            self.intelligence_client
        )
        trade_pnl_mod = importlib.import_module("brokers.upstox.market_data.trade_pnl")
        self.trade_pnl_calculator = trade_pnl_mod.TradePnLCalculator(
            self.portfolio_client,
            self.market_data_v2,
        )
        self.capabilities.market_data.intelligence = self.intelligence
        self.capabilities.market_data.intelligence_snapshot = self.intelligence_snapshot
        self._register_capability(Capability.OPTION_GREEKS, self.intelligence)
        self._register_capability(Capability.OI_PCR_MAXPAIN, self.intelligence)
        self._register_capability(Capability.SMARTLIST, self.intelligence)
        self._register_capability(Capability.FII_DII, self.intelligence)
        self._extended_ready = True

    def _register_all_capabilities(self) -> None:
        # Capabilities registered by the _CORE_ADAPTER_REGISTRY loop in __init__:
        #   PORTFOLIO, MARGIN, OPTIONS_CHAIN, FUTURES, MARKET_STATUS,
        #   KILL_SWITCH, GTT_ORDER
        #
        # Extended capabilities (IPO, PAYMENTS, etc.) register in _ensure_extended().
        self._register_capability(Capability.MARKET_DATA, self.market_data)
        self._register_capability(Capability.DEPTH, self.market_data)
        self._register_capability(Capability.HISTORICAL_DATA, self.market_data)
        self._register_capability(Capability.ORDER_COMMAND, self.order_command)
        self._register_capability(Capability.ORDER_QUERY, self.order_query)
        self._register_capability(Capability.INSTRUMENTS, self.instrument_resolver)
        self._register_capability(Capability.SLICE_ORDER, self.slice)
        self._register_capability(Capability.ORDER_SLICING, self.slice)
        self._register_capability(Capability.COVER_ORDER, self.cover)
        self._register_capability(Capability.ALERTS, self.alert)
        self._register_capability(Capability.WEBSOCKET, self.market_data_websocket)
        self._register_capability(Capability.PORTFOLIO_STREAM, self.portfolio_stream)
        self._register_capability(Capability.IDEMPOTENCY, self.idempotency_cache)
        self._register_capability(Capability.WEBHOOKS, self.feed_authorizer)
        self._register_capability(Capability.MULTI_ORDER, self.order_client)
        self._register_capability(Capability.AMO_ORDER, self.order_command)
        self._register_capability(Capability.EXIT_ALL, self.exit_all)
        if self._risk_manager is not None:
            self._register_capability(Capability.SESSION_RISK, self._risk_manager)

    # ── Connection lifecycle ──

    @property
    def name(self) -> str:
        return self._name

    @property
    def broker_id(self) -> str:
        return self._broker_id

    @property
    def status(self) -> ConnectionStatus:
        return self._status

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

    # ── Capability registry ──

    def _register_capability(self, capability: Capability, provider: Any) -> None:
        self._capabilities.add(capability)
        self._capability_map[capability] = provider

    def has_capability(self, capability: Capability) -> bool:
        return capability in self._capabilities

    def get_capability(self, capability: Capability) -> Any:
        return self._capability_map.get(capability)

    def _set_status(self, status: ConnectionStatus) -> None:
        self._status = status

    def __enter__(self) -> UpstoxBroker:
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.disconnect()
