"""Upstox broker facade — instantiates every adapter from the resolved
``UpstoxConnectionSettings`` + ``UpstoxTokenManager`` and exposes them
as direct attributes.

This is a plain class (no ABC base). The ``UpstoxWireAdapter`` wrapper
implements the ``MarketDataGateway`` contract; this class provides the
adapter wiring.

The construction is delegated to private helpers (``_build_raw_clients``,
``_build_adapters``, ``_build_order_path``) so the god-constructor reads
top-down rather than as a wall of identical ``UpstoxXClient(...)`` calls,
while the public attribute surface is unchanged for backward compatibility.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from brokers.common.idempotency import IdempotencyCache
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
from brokers.upstox.fundamentals.client import UpstoxFundamentalsClient
from brokers.upstox.instruments.search import UpstoxInstrumentSearch
from brokers.upstox.instruments.service import UpstoxInstrumentService
from brokers.upstox.ipo.adapter import UpstoxIpoAdapter
from brokers.upstox.ipo.client import UpstoxIpoClient
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
from brokers.upstox.market_data.trade_pnl import TradePnLCalculator
from brokers.upstox.market_intelligence.adapter import UpstoxMarketIntelligenceAdapter
from brokers.upstox.market_intelligence.client import UpstoxMarketIntelligenceClient
from brokers.upstox.market_intelligence.snapshot import UpstoxMarketIntelligenceSnapshotBuilder
from brokers.upstox.mutual_funds.client import UpstoxMutualFundsClient
from brokers.upstox.news.adapter import UpstoxNewsAdapter
from brokers.upstox.news.client import UpstoxNewsClient
from brokers.upstox.orders.alert_adapter import UpstoxAlertAdapter
from brokers.upstox.orders.cover_order_adapter import UpstoxCoverOrderAdapter
from brokers.upstox.orders.exit_all_adapter import UpstoxExitAllAdapter
from brokers.upstox.orders.gtt_adapter import UpstoxGttAdapter
from brokers.upstox.orders.gtt_client import UpstoxGttClient
from brokers.upstox.orders.order_client import UpstoxRestOrderClient
from brokers.upstox.orders.order_command_adapter import UpstoxOrderCommandAdapter
from brokers.upstox.orders.order_query_adapter import UpstoxOrderQueryAdapter
from brokers.upstox.orders.slice_adapter import UpstoxSliceAdapter
from brokers.upstox.payments.client import UpstoxPaymentsClient
from brokers.upstox.reconciliation.service import UpstoxReconciliationService
from brokers.upstox.static_ip.client import UpstoxStaticIpClient
from brokers.upstox.websocket.feed_authorizer import UpstoxFeedAuthorizer
from brokers.upstox.websocket.market_data_v3 import UpstoxMarketDataV3Multiplexer
from brokers.upstox.websocket.portfolio_stream import UpstoxPortfolioStream
from brokers.upstox.websocket.v3_auto_reconnect import UpstoxAutoReconnect
from brokers.upstox.websocket.v3_decoder import UpstoxV3Decoder
from brokers.upstox.websocket.v3_subscription_manager import UpstoxV3SubscriptionLimits
from domain.capabilities import Capability, ConnectionStatus
from domain.ports.risk_manager import RiskManagerPort
from infrastructure.event_bus import EventBus
from infrastructure.historical_data import HistoricalDataService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _UpstoxCapabilities:
    """Broker capabilities snapshot — constructed once, cached by the broker."""

    market_data: MarketDataCapability
    orders: OrdersCapability
    portfolio: PortfolioCapability
    instruments: InstrumentsCapability
    streaming: StreamingCapability


class UpstoxBroker:
    def __init__(
        self,
        settings: UpstoxConnectionSettings | None = None,
        *,
        token_manager: UpstoxTokenManager | None = None,
        oms: Any = None,
        event_bus: EventBus | None = None,
        risk_manager: RiskManagerPort | None = None,
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
        # Extended (Upstox-specific) adapters are built lazily so the core
        # bootstrap path neither imports those modules nor requires their
        # downstream dependencies. See ``_ensure_extended``.
        self._extended_ready: bool = False
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

        # REF-23: client/adapter construction is delegated to three
        # private helpers. The split is purely structural — the
        # public attribute set (``self.market_data``, ``self.orders``,
        # etc.) is unchanged. The eventual goal is to lift these
        # helpers into standalone ``ClientBundle`` /
        # ``AdapterBundle`` / ``OrderBundle`` objects so the
        # broker can be composed from independently testable
        # bundles. Until that migration lands, the helpers
        # exist so the god-constructor reads top-down rather
        # than as a wall of identical ``UpstoxXClient(...)`` calls.

        # Instruments (shared by every other bundle) — service owns load + mapping
        self.instruments = UpstoxInstrumentService()
        self.instrument_resolver = self.instruments.resolver
        self.instrument_loader = self.instruments.loader
        self.instrument_search = UpstoxInstrumentSearch(self.context.http_client)

        # Raw HTTP clients (v2, v3, GTT, websocket, etc.)
        self._build_raw_clients(settings)

        # Domain adapters (market data, portfolio, options, ...)
        self._build_adapters()

        # Order path (commands, queries, GTT, slices, alerts)
        self._build_order_path(settings)

        # Reconciliation
        if reconciliation_service is not None:
            self.reconciliation_service = reconciliation_service
        else:
            # F4: heal on by default for live; composition roots may inject
            # a service with should_auto_repair() for env override.
            self.reconciliation_service = UpstoxReconciliationService(
                self.order_client, self.portfolio_client, oms=self._oms, auto_repair=True
            )

        # Trade P&L Calculator
        self.trade_pnl_calculator = TradePnLCalculator(self.portfolio_client, self.market_data_v2)

        self._register_all_capabilities()

        # Eagerly construct the capabilities dataclass so the property
        # doesn't rebuild it on every access.
        self._capabilities_obj: Any = None

    # ── REF-23: bundle helpers ──────────────────────────────────────────

    def _build_raw_clients(self, settings: Any) -> None:
        """Construct the raw HTTP clients the broker owns.

        Each client takes ``(http_client, url_resolver)`` from
        :attr:`context`. Grouping them here keeps the constructor
        readable and gives a future refactor a single seam to
        extract a ``RawClientBundle``.
        """
        http = self.context.http_client
        resolver = self.context.url_resolver

        # Market data
        self.market_data_v2 = UpstoxMarketDataV2Client(http, resolver)
        self.market_data_v3 = UpstoxMarketDataV3Client(http, resolver)
        self.historical_v2 = UpstoxHistoricalV2Client(http, resolver)
        self.historical_v3 = UpstoxHistoricalV3Client(http, resolver)

        # Options / portfolio / margin
        self.options_client = UpstoxOptionsClient(http, resolver)
        self.portfolio_client = UpstoxPortfolioClient(http, resolver)
        self.margin_client = UpstoxMarginClient(http, resolver)
        self.market_status_client = UpstoxMarketStatusClient(http, resolver)
        self.futures_client = UpstoxFuturesClient(
            http, resolver, instrument_resolver=self.instrument_resolver
        )
        self.expired_instruments_client = UpstoxExpiredInstrumentsClient(http, resolver)

        # Orders / GTT
        self.order_client = UpstoxRestOrderClient(http, resolver)
        self.gtt_client = UpstoxGttClient(http, resolver)

        # Intelligence / news / kill switch / static IP
        self.news_client = UpstoxNewsClient(http, resolver)
        self.intelligence_client = UpstoxMarketIntelligenceClient(http, resolver)
        self.kill_switch_client = UpstoxKillSwitchClient(http, resolver)
        self.static_ip_client = UpstoxStaticIpClient(http, resolver)

        # Payments / IPO / MF / fundamentals
        self.ipo_client = UpstoxIpoClient(http, resolver)
        self.payments_client = UpstoxPaymentsClient(http, resolver)
        self.mutual_funds_client = UpstoxMutualFundsClient(http, resolver)
        self.fundamentals_client = UpstoxFundamentalsClient(http, resolver)

        # Shared historical service (uses parquet cache)
        self.historical_service = HistoricalDataService(
            self.market_data_v2,
            parquet_cache_path=settings.instrument_cache_path,
        )

    def _build_adapters(self) -> None:
        """Construct the domain adapters over the raw clients."""
        self.market_data = UpstoxMarketDataAdapter(
            self.market_data_v2, self.market_data_v3, self.historical_v2
        )
        self.options = UpstoxOptionsAdapter(
            self.options_client, instrument_resolver=self.instrument_resolver
        )
        self.portfolio = UpstoxPortfolioAdapter(self.portfolio_client)
        self.margin = UpstoxMarginAdapter(self.margin_client)
        self.market_status = UpstoxMarketStatusAdapter(self.market_status_client)
        self.futures = UpstoxFuturesAdapter(self.futures_client)
        self.news = UpstoxNewsAdapter(self.news_client)
        self.intelligence_snapshot = UpstoxMarketIntelligenceSnapshotBuilder(
            self.intelligence_client
        )
        self.kill_switch = self.kill_switch_client
        self.exit_all = UpstoxExitAllAdapter(self.kill_switch_client)
        # ``static_ip``, ``ipo``, ``payments``, ``mutual_funds``,
        # ``fundamentals`` and ``intelligence`` are Upstox-specific "extended"
        # adapters — they are NOT built here. They are wired lazily by
        # ``_ensure_extended`` so the hot constructor path stays lean and
        # ``gateway.extended`` is the only entry point that needs them.

    def _build_order_path(self, settings: Any) -> None:
        """Construct the order-path objects (commands, queries, GTT, ws)."""
        # Idempotency + order command
        self.idempotency_cache = IdempotencyCache()
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
            event_bus=self._event_bus,
            backfill_callback=self._backfill_callback,
        )

        # Order-update / portfolio stream. Wired the same way as the market
        # data feed: it shares the ``feed_authorizer`` (token/connection) and
        # reuses the same auto-reconnect profile. ``gateway.stream_order`` and
        # the factory's ``UpstoxPortfolioStreamService`` depend on this.
        self.portfolio_stream = UpstoxPortfolioStream(
            self.feed_authorizer,
            event_bus=self._event_bus,
            auto_reconnect=UpstoxAutoReconnect(
                enabled=settings.ws_auto_reconnect,
                interval_seconds=settings.ws_reconnect_interval_s,
                max_retries=settings.ws_reconnect_max_retries,
            ),
        )

    # ── Extended (Upstox-specific) lazy surface ──

    def _ensure_extended(self) -> None:
        """Lazily construct the Upstox-specific ("extended") adapters.

        These adapters back :class:`UpstoxExtendedCapabilities` (exposed via
        ``gateway.extended``) and the IPO / payments / mutual-funds /
        fundamentals / market-intelligence / static-IP capabilities. They are
        intentionally *not* built in the hot constructor path so that core
        bootstrap neither imports those modules nor requires their downstream
        dependencies to be present.

        Idempotent — safe to call any number of times.
        """
        if self._extended_ready:
            return

        self.intelligence = UpstoxMarketIntelligenceAdapter(self.intelligence_client)
        self.static_ip = self.static_ip_client
        self.ipo = UpstoxIpoAdapter(self.ipo_client)
        self.payments = self.payments_client
        self.mutual_funds = self.mutual_funds_client
        self.fundamentals = self.fundamentals_client

        self._register_capability(Capability.MARKET_INTELLIGENCE, self.intelligence)
        self._register_capability(Capability.OPTION_GREEKS, self.intelligence)
        self._register_capability(Capability.STATIC_IP, self.static_ip)
        self._register_capability(Capability.IPO, self.ipo)
        self._register_capability(Capability.PAYMENTS, self.payments)
        self._register_capability(Capability.MUTUAL_FUNDS, self.mutual_funds)
        self._register_capability(Capability.FUNDAMENTALS, self.fundamentals)

        self._extended_ready = True

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
        self._register_capability(Capability.KILL_SWITCH, self.kill_switch)
        # ``STATIC_IP``, ``IPO``, ``PAYMENTS``, ``MUTUAL_FUNDS``,
        # ``FUNDAMENTALS`` and ``MARKET_INTELLIGENCE`` (``OPTION_GREEKS``) are
        # registered lazily in ``_ensure_extended`` — they are part of the
        # Upstox-specific "extended" surface and must not be available until
        # ``gateway.extended`` is first accessed.
        self._register_capability(Capability.PORTFOLIO_STREAM, self.portfolio_stream)
        self._register_capability(Capability.WEBHOOKS, self.feed_authorizer)

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

    @property
    def capabilities(self) -> Any:
        if self._capabilities_obj is not None:
            return self._capabilities_obj
        self._ensure_extended()
        self._capabilities_obj = _UpstoxCapabilities(
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
                intelligence=self.intelligence,
                intelligence_snapshot=self.intelligence_snapshot,
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
        return self._capabilities_obj

    @property
    def token_manager(self) -> UpstoxTokenManager:
        return self._token_manager

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
        """Stop market-data and portfolio streams before marking disconnected."""
        import contextlib

        from infrastructure.io.async_compat import run_async_compat

        for name in ("market_data_websocket", "portfolio_stream"):
            ws = getattr(self, name, None)
            if ws is None:
                continue
            stop = getattr(ws, "disconnect", None) or getattr(ws, "stop", None)
            if not callable(stop):
                continue
            with contextlib.suppress(Exception):
                result = stop()
                if result is not None and hasattr(result, "__await__"):
                    run_async_compat(result)
        self._set_status(ConnectionStatus.DISCONNECTED)
        return True

    def reconnect(self) -> bool:
        return self.connect()

    # ── Capability registry ──

    def capability_snapshot(self):
        """Declarative BrokerCapabilities SSOT — same as gateway.capabilities()."""
        from brokers.upstox.capabilities.snapshot import upstox_capabilities

        return upstox_capabilities()

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
