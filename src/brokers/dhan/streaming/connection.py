"""DhanConnection — wires all adapters with shared HTTP client + resolver."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from brokers.dhan.api.http_client import DhanHttpClient
from brokers.dhan.config.capabilities import DHAN_DEPTH_200_MAX_INSTRUMENTS_PER_CONNECTION
from brokers.dhan.auth.connection_token_manager import ConnectionTokenManager
from brokers.dhan.auth.edis import EDISAdapter
from brokers.dhan.auth.ip_management import IPManagementAdapter
from brokers.dhan.data.alerts import AlertsAdapter
from brokers.dhan.data.depth_20 import DhanDepth20Feed
from brokers.dhan.data.depth_200 import DhanDepth200Feed
from brokers.dhan.data.futures import FuturesAdapter
from brokers.dhan.data.historical import HistoricalAdapter
from brokers.dhan.data.market_data import MarketDataAdapter
from brokers.dhan.data.options import OptionsAdapter
from brokers.dhan.execution.conditional_triggers import ConditionalTriggersAdapter
from brokers.dhan.execution.exit_all import ExitAllAdapter
from brokers.dhan.execution.forever_orders import ForeverOrdersAdapter
from brokers.dhan.execution.orders import OrdersAdapter
from brokers.dhan.execution.pnl_exit import PnlExitAdapter
from brokers.dhan.execution.super_orders import SuperOrdersAdapter
from brokers.dhan.identity.user_profile import UserProfileAdapter
from brokers.dhan.instruments import DhanInstrumentService
from brokers.dhan.portfolio.ledger import LedgerAdapter
from brokers.dhan.portfolio.margin import MarginAdapter
from brokers.dhan.portfolio.portfolio import PortfolioAdapter
from brokers.dhan.resolver import SymbolResolver
from brokers.dhan.streaming.connection_lifecycle import ConnectionLifecycle
from brokers.dhan.streaming.session_manager import DhanSessionManager
from brokers.dhan.websocket import DhanMarketFeed, DhanOrderStream, PollingMarketFeed
from domain import MarketDepth
from domain.ports.risk_manager import RiskManagerPort
from infrastructure.event_bus.event_bus import EventBus
from infrastructure.lifecycle.lifecycle import LifecycleManager
from infrastructure.resilience.circuit_breaker import CircuitState

logger = logging.getLogger(__name__)

# ── Adapter registry: (attr_name, adapter_class) ──
# Each entry constructs an adapter from (client, instruments).
# Entries are split by whether the adapter's constructor takes the
# instrument resolver as a second positional arg.
_ADAPTERS_WITH_INSTRUMENTS: list[tuple[str, type]] = [
    ("_market_data", MarketDataAdapter),
    ("_historical", HistoricalAdapter),
    ("_portfolio", PortfolioAdapter),
    ("_options", OptionsAdapter),
    ("_futures", FuturesAdapter),
    ("_margin", MarginAdapter),
    ("_alerts", AlertsAdapter),
    ("_super_orders", SuperOrdersAdapter),
    ("_forever_orders", ForeverOrdersAdapter),
    ("_conditional_triggers", ConditionalTriggersAdapter),
]

_ADAPTERS_CLIENT_ONLY: list[tuple[str, type]] = [
    ("_ledger", LedgerAdapter),
    ("_user_profile", UserProfileAdapter),
    ("_ip_management", IPManagementAdapter),
    ("_edis", EDISAdapter),
    ("_exit_all", ExitAllAdapter),
    ("_pnl_exit", PnlExitAdapter),
]


class DhanConnection:
    """Concrete connection wiring all Dhan adapters.

    ponytail: still a large wiring hub; token + WS lifecycle already extracted
    (ConnectionTokenManager, ConnectionLifecycle). Further splits only when a
    change forces a touch — ceiling is adapter-registry growth, upgrade path is
    more helpers not a rewrite.

    Lifecycle ownership (Phase B / B5)
    ---------------------------------
    A :class:`LifecycleManager` may be supplied. When present, every
    ``ManagedService`` produced by this connection (``DhanMarketFeed``,
    ``DhanOrderStream``, ``PollingMarketFeed``) is registered with it
    so the connection's ``close()`` can drain every background thread.

    Previously, the WebSocket services were created lazily and ran as
    bare daemon threads; ``close()`` only called ``disconnect()`` and
    even ``disconnect()`` did not always join — the threads were
    leaked until process exit.
    """

    def __init__(
        self,
        client: DhanHttpClient,
        resolver: SymbolResolver | DhanInstrumentService | None = None,
        event_bus: EventBus | None = None,
        risk_manager: RiskManagerPort | None = None,
        backfill_callback: Callable[[str, datetime, datetime], list[dict]] | None = None,
        reconciliation_service: object | None = None,
        lifecycle: LifecycleManager | None = None,
        allow_live_orders: bool = False,
    ):
        self._client = client
        # Broker-internal instrument service (loader + resolver + identity).
        # Gateways must not derive security_id / segment themselves.
        if isinstance(resolver, DhanInstrumentService):
            self.instruments = resolver
        else:
            self.instruments = DhanInstrumentService(resolver=resolver)
        self.identity = self.instruments.identity
        self._event_bus = event_bus
        # B5: if a lifecycle is provided, lazily-created WebSocket
        # services will be registered with it. close() then drains
        # every thread within bounded timeouts.
        self._lifecycle = lifecycle

        # ── Registry-driven adapter construction ──
        for attr_name, adapter_cls in _ADAPTERS_WITH_INSTRUMENTS:
            setattr(self, attr_name, adapter_cls(client, self.identity))
        for attr_name, adapter_cls in _ADAPTERS_CLIENT_ONLY:
            setattr(self, attr_name, adapter_cls(client))

        # Special case: OrdersAdapter takes extra kwargs
        self._orders = OrdersAdapter(
            client,
            self.identity,
            event_bus=event_bus,
            risk_manager=risk_manager,
            allow_live_orders=allow_live_orders,
        )
        self._token_manager = ConnectionTokenManager()
        self._lifecycle_helper = ConnectionLifecycle(
            client,
            self.instruments.resolver,
            register_token_receiver=self._token_manager.register_receiver,
            connection_owner=self,
            event_bus=event_bus,
            lifecycle=lifecycle,
            backfill_callback=backfill_callback,
        )
        self._backfill_callback = backfill_callback
        self._reconciliation_service = reconciliation_service
        from brokers.dhan.data.subscription_engine import SubscriptionEngine

        self.subscription_engine = SubscriptionEngine(self)
        self._session_manager: DhanSessionManager | None = None

    @property
    def market_data(self) -> MarketDataAdapter:
        return self._market_data

    @property
    def historical(self) -> HistoricalAdapter:
        return self._historical

    @property
    def orders(self) -> OrdersAdapter:
        return self._orders

    @property
    def portfolio(self) -> PortfolioAdapter:
        return self._portfolio

    @property
    def options(self) -> OptionsAdapter:
        return self._options

    @property
    def futures(self) -> FuturesAdapter:
        return self._futures

    @property
    def margin(self) -> MarginAdapter:
        return self._margin

    @property
    def event_bus(self) -> EventBus | None:
        return self._event_bus

    @property
    def alerts(self) -> AlertsAdapter:
        return self._alerts

    @property
    def super_orders(self) -> SuperOrdersAdapter:
        return self._super_orders

    @property
    def forever_orders(self) -> ForeverOrdersAdapter:
        return self._forever_orders

    @property
    def conditional_triggers(self) -> ConditionalTriggersAdapter:
        return self._conditional_triggers

    @property
    def ledger(self) -> LedgerAdapter:
        return self._ledger

    @property
    def user_profile(self) -> UserProfileAdapter:
        return self._user_profile

    @property
    def ip_management(self) -> IPManagementAdapter:
        return self._ip_management

    @property
    def edis(self) -> EDISAdapter:
        return self._edis

    @property
    def exit_all(self) -> ExitAllAdapter:
        return self._exit_all

    @property
    def pnl_exit(self) -> PnlExitAdapter:
        return self._pnl_exit

    @property
    def backfill_callback(self) -> Callable[[str, datetime, datetime], list[dict]] | None:
        """Backfill callback for market feed reconnect gap fill."""
        return self._backfill_callback

    @property
    def reconciliation_service(self) -> object | None:
        """Reconciliation service wired into the trading context."""
        return self._reconciliation_service

    # ── Public accessors (avoid private _client access from gateway) ──

    @property
    def access_token(self) -> str:
        """Current API access token (delegates to HTTP client)."""
        return self._client.access_token

    @property
    def client_id(self) -> str:
        """Broker client ID (delegates to HTTP client)."""
        return self._client.client_id

    @property
    def depth_20_feed(self) -> DhanDepth20Feed | None:
        """Active 20-level depth feed, if created."""
        return self._lifecycle_helper.depth_20_feed

    @depth_20_feed.setter
    def depth_20_feed(self, value: DhanDepth20Feed) -> None:
        self._lifecycle_helper.depth_20_feed = value

    @property
    def depth_200_feed(self) -> DhanDepth200Feed | None:
        """Active 200-level depth feed, if created."""
        return self._lifecycle_helper.depth_200_feed

    @depth_200_feed.setter
    def depth_200_feed(self, value: DhanDepth200Feed) -> None:
        self._lifecycle_helper.depth_200_feed = value

    @property
    def depth_200_pool(self) -> Any:
        """Active depth-200 connection pool for managing multiple instrument connections."""
        return self._lifecycle_helper.depth_200_pool

    @property
    def market_feed(self) -> DhanMarketFeed | None:
        """Real-time market data feed (lazy — None until explicitly created)."""
        return self._lifecycle_helper.market_feed

    @market_feed.setter
    def market_feed(self, value: DhanMarketFeed) -> None:
        self._lifecycle_helper.market_feed = value

    @property
    def order_stream(self) -> DhanOrderStream | None:
        """Real-time order update stream (lazy — None until explicitly created)."""
        return self._lifecycle_helper.order_stream

    @order_stream.setter
    def order_stream(self, value: DhanOrderStream) -> None:
        self._lifecycle_helper.order_stream = value

    @property
    def polling_feed(self) -> PollingMarketFeed | None:
        """Real-time polling market feed."""
        return self._lifecycle_helper.polling_feed

    @polling_feed.setter
    def polling_feed(self, value: PollingMarketFeed) -> None:
        self._lifecycle_helper.polling_feed = value

    @property
    def client(self) -> DhanHttpClient:
        """Public accessor for the underlying HTTP client.

        Callers that need to make raw API calls (e.g. extended capabilities)
        should use this property instead of accessing ``_client`` directly.
        """
        return self._client

    @property
    def token_scheduler(self) -> object | None:
        """Active token-refresh scheduler, if one has been installed."""
        return getattr(self, "_token_scheduler", None)

    @property
    def session_manager(self) -> DhanSessionManager | None:
        """Consolidated auth + connection + subscription session view."""
        return getattr(self, "_session_manager", None)

    @token_scheduler.setter
    def token_scheduler(self, value: object) -> None:
        """Install a token-refresh scheduler on this connection."""
        self._token_scheduler = value

    @property
    def circuit_breaker_states(self) -> dict[str, int]:
        """Return circuit breaker states for observability.

        Maps each breaker category to an int:
        0 = CLOSED, 1 = OPEN, 2 = HALF_OPEN.
        """
        state_map = {
            CircuitState.CLOSED: 0,
            CircuitState.OPEN: 1,
            CircuitState.HALF_OPEN: 2,
        }
        states: dict[str, int] = {}
        for attr, short_name in [
            ("_read_circuit_breaker", "read_cb"),
            ("_write_circuit_breaker", "write_cb"),
            ("_admin_circuit_breaker", "admin_cb"),
        ]:
            cb = getattr(self._client, attr, None)
            if cb is not None:
                try:
                    states[short_name] = state_map.get(cb.state, 0)
                except Exception:
                    states[short_name] = 0
        return states

    @property
    def token_refresh_metrics(self) -> dict[str, int]:
        """Return token refresh metrics for observability."""
        scheduler = getattr(self, "_token_scheduler", None)
        if scheduler is None:
            return {"refresh_count": 0, "error_count": 0}
        try:
            return {
                "refresh_count": getattr(scheduler, "refresh_count", 0),
                "error_count": 1 if getattr(scheduler, "_last_error", None) else 0,
            }
        except Exception:
            return {"refresh_count": 0, "error_count": 0}

    def load_instruments(self, source: str | None = None, use_cache: bool = True) -> None:
        """Load instruments into the broker-internal instrument service."""
        self.instruments.load(source=source, force_refresh=not use_cache)

    def subscribe_stream(
        self,
        symbol: str,
        exchange: str = "NSE",
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any:
        """Subscribe to a live tick stream. Security mapping stays internal."""
        from decimal import Decimal

        from domain import Quote

        ref = self.instruments.resolve_dhan_ref(symbol, exchange)
        segment = ref.exchange_segment
        sid = int(ref.security_id)
        feed = self.market_feed
        if feed is None:
            feed = self.create_market_feed(
                access_token=self.access_token,
                instruments=[(segment, sid, mode)],
                access_token_fn=lambda: self.access_token,
            )
            self.market_feed = feed
        else:
            feed.subscribe([(segment, sid, mode)])
        if on_tick:

            def _wrap(data: dict) -> None:
                try:
                    q = Quote(
                        symbol=data.get("symbol", symbol),
                        ltp=data.get("ltp", Decimal("0")),
                        open=data.get("open", Decimal("0")),
                        high=data.get("high", Decimal("0")),
                        low=data.get("low", Decimal("0")),
                        close=data.get("close", Decimal("0")),
                        volume=int(data.get("volume", 0)),
                        change=data.get("change", Decimal("0")),
                    )
                    on_tick(q)
                except Exception:
                    logger.debug(
                        "Dhan tick→Quote wrap failed; forwarding raw",
                        exc_info=True,
                    )
                    on_tick(data)

            feed.on_quote(_wrap)
        if not feed.is_connected:
            feed.connect()
        return feed

    def subscribe_depth_20(
        self,
        symbol: str,
        exchange: str = "NSE",
        on_depth: Any | None = None,
    ) -> Any:
        """Subscribe to 20-level depth. Security mapping stays internal."""
        if exchange not in ("NSE", "NSE_EQ", "NFO", "NSE_FNO", "IDX_I"):
            raise ValueError(f"Depth 20 only supported for NSE segments, got: {exchange}")

        ref = self.instruments.resolve_dhan_ref(symbol, exchange)
        segment = ref.exchange_segment
        sid_str = ref.security_id_str()
        sid_int = int(sid_str)

        feed = self.depth_20_feed
        if feed is None:
            feed = self.create_depth_20_feed(
                access_token=self.access_token,
                instrument=(segment, sid_str),
            )
        else:
            already = any(s[1] == sid_str for s in feed.subscriptions)
            if not already:
                feed.subscribe([(segment, sid_str)])

        if on_depth is not None:
            feed.on_depth(on_depth)

        if not feed.is_running:
            feed.start()

        cached = feed.latest_depth(sid_int)
        if cached is not None:
            if not cached.bids or not cached.asks:
                rest = self.market_data.get_depth(symbol, exchange)
                bids = cached.bids if cached.bids else rest.bids
                asks = cached.asks if cached.asks else rest.asks
                return MarketDepth(
                    symbol=cached.symbol,
                    bids=bids,
                    asks=asks,
                    depth_type=cached.depth_type,
                    timestamp=cached.timestamp or rest.timestamp,
                )
            return cached
        return self.market_data.get_depth(symbol, exchange)

    def subscribe_depth_200(
        self,
        symbol: str,
        exchange: str = "NSE",
        on_depth: Any | None = None,
    ) -> Any:
        """Subscribe to 200-level depth. Security mapping stays internal."""
        if exchange not in ("NSE", "NSE_EQ", "NFO", "NSE_FNO", "IDX_I"):
            raise ValueError(f"Depth 200 only supported for NSE segments, got: {exchange}")

        ref = self.instruments.resolve_dhan_ref(symbol, exchange)
        segment = ref.exchange_segment
        sid_str = ref.security_id_str()

        feed = self.depth_200_feed
        if feed is None:
            feed = self.create_depth_200_feed(
                access_token=self.access_token,
                instrument=(segment, sid_str),
            )
        else:
            existing = feed.subscriptions[0][1] if feed.subscriptions else None
            if existing and existing != sid_str:
                raise ValueError(
                    f"Depth 200 feed already subscribed to security_id {existing}. "
                    f"Dhan allows only {DHAN_DEPTH_200_MAX_INSTRUMENTS_PER_CONNECTION} "
                    f"instrument per depth-200 connection; create a new gateway "
                    f"connection to stream a different instrument."
                )

        if on_depth is not None:
            feed.on_depth(on_depth)

        if not feed.is_running:
            feed.start()

        cached = feed.latest_depth()
        if cached is not None:
            if not cached.bids or not cached.asks:
                rest = self.market_data.get_depth(symbol, exchange)
                bids = cached.bids if cached.bids else rest.bids
                asks = cached.asks if cached.asks else rest.asks
                return MarketDepth(
                    symbol=cached.symbol,
                    bids=bids,
                    asks=asks,
                    depth_type=cached.depth_type,
                    timestamp=cached.timestamp or rest.timestamp,
                )
            return cached
        return self.market_data.get_depth(symbol, exchange)

    def create_market_feed(
        self,
        access_token: str | None = None,
        instruments: list[tuple] | None = None,
        access_token_fn: Callable[[], str] | None = None,
    ) -> DhanMarketFeed:
        """Create and return a DhanMarketFeed wired with this connection's backfill callback."""
        return self._lifecycle_helper.create_market_feed(
            access_token=access_token,
            instruments=instruments,
            access_token_fn=access_token_fn,
        )

    def create_order_stream(
        self,
        access_token: str | None = None,
        access_token_fn: Callable[[], str] | None = None,
    ) -> DhanOrderStream:
        """Create and return a DhanOrderStream."""
        return self._lifecycle_helper.create_order_stream(
            access_token=access_token,
            access_token_fn=access_token_fn,
        )

    def create_depth_20_feed(
        self,
        access_token: str | None = None,
        instrument: tuple[str, str] | None = None,
    ) -> DhanDepth20Feed:
        """Create and return a DhanDepth20Feed for 20-level depth."""
        return self._lifecycle_helper.create_depth_20_feed(
            access_token=access_token,
            instrument=instrument,
        )

    def create_depth_200_feed(
        self,
        access_token: str | None = None,
        instrument: tuple[str, str] | None = None,
    ) -> DhanDepth200Feed:
        """Create and return a DhanDepth200Feed for 200-level depth."""
        return self._lifecycle_helper.create_depth_200_feed(
            access_token=access_token,
            instrument=instrument,
        )

    def create_polling_feed(
        self,
        instruments: list[tuple],
        interval_seconds: float = 2.0,
    ) -> PollingMarketFeed:
        """Create and return a PollingMarketFeed."""
        return self._lifecycle_helper.create_polling_feed(
            instruments,
            interval_seconds=interval_seconds,
        )

    # ── Token-receiver registry (REF-13) ──────────────────────────────────

    def register_token_receiver(self, receiver: Callable[[str], None]) -> Callable[[str], None]:
        """Register a callable invoked whenever a new access token arrives."""
        return self._token_manager.register_receiver(receiver)

    def broadcast_token(self, new_token: str) -> int:
        """Push ``new_token`` to every registered receiver."""
        count = self._token_manager.broadcast(new_token)
        from brokers.common.auth.lifecycle import publish_token_lifecycle_event

        publish_token_lifecycle_event(
            self._event_bus,
            "TOKEN_REFRESHED",
            broker_id="dhan",
            receivers=count,
        )
        return count

    # ── BrokerStreamGateway surface ─────────────────────────────────────

    def connect(self) -> bool:
        """Establish market-feed transport when available."""
        feed = getattr(self, "market_feed", None)
        if feed is None:
            return True
        if getattr(feed, "is_connected", False):
            return True
        connect_fn = getattr(feed, "connect", None)
        if callable(connect_fn):
            connect_fn()
        return bool(getattr(feed, "is_connected", True))

    def subscribe(self, instruments: list[Any]) -> bool:
        """Subscribe instruments via the shared stream gateway surface."""
        if not instruments:
            return True
        for item in instruments:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                symbol, exchange = str(item[0]), str(item[1])
            elif hasattr(item, "symbol"):
                symbol = str(item.symbol)
                exchange = str(getattr(item, "exchange", "NSE"))
            else:
                symbol, exchange = str(item), "NSE"
            self.subscribe_stream(symbol, exchange)
        return True

    def on_tick(self, callback: Callable[[Any], None]) -> None:
        """Register a default tick callback for subsequent subscriptions."""
        self._stream_tick_callback = callback

    def disconnect(self) -> None:
        """Tear down market feed / streams."""
        feed = getattr(self, "market_feed", None)
        if feed is not None:
            stop = getattr(feed, "disconnect", None) or getattr(feed, "stop", None)
            if callable(stop):
                stop()

    def get_or_create_resolver_refresher(
        self,
        interval_seconds: int = 24 * 3600,
        on_success=None,
        on_error=None,
    ):
        """Return the singleton :class:`ResolverRefresher` for this connection."""
        return self._lifecycle_helper.get_or_create_resolver_refresher(
            interval_seconds=interval_seconds,
            on_success=on_success,
            on_error=on_error,
        )

    def register_resolver_refresher_with_lifecycle(
        self,
        interval_seconds: int = 24 * 3600,
    ):
        """Create the refresher and register it with the lifecycle manager."""
        return self._lifecycle_helper.register_resolver_refresher_with_lifecycle(
            interval_seconds=interval_seconds,
        )

    def close(self) -> None:
        """Close HTTP client, stop token scheduler, and disconnect WebSocket connections.

        B5: every ManagedService is stopped via ``stop(timeout_seconds)``
        which joins the thread. The previous ``disconnect()`` was not
        always called and never joined — the daemon threads leaked on
        process exit.
        """
        # Stop token refresh scheduler (ManagedService)
        scheduler = getattr(self, "_token_scheduler", None)
        if scheduler is not None:
            try:
                scheduler.stop()
            except Exception as exc:
                logger.warning("token_scheduler_stop_failed: %s", exc)
        # PR-C: stop the resolver refresher if one was created.
        self._lifecycle_helper.close(timeout_seconds=5.0)
        self._client.close()
