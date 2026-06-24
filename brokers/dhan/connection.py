"""DhanConnection — wires all adapters with shared HTTP client + resolver."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from infrastructure.event_bus import EventBus
from infrastructure.lifecycle import LifecycleManager
from application.oms.risk_manager import RiskManager
from brokers.dhan.alerts import AlertsAdapter
from brokers.dhan.conditional_triggers import ConditionalTriggersAdapter
from brokers.dhan.depth_20 import DhanDepth20Feed
from brokers.dhan.depth_200 import DhanDepth200Feed
from brokers.dhan.edis import EDISAdapter
from brokers.dhan.exit_all import ExitAllAdapter
from brokers.dhan.forever_orders import ForeverOrdersAdapter
from brokers.dhan.futures import FuturesAdapter
from brokers.dhan.historical import HistoricalAdapter
from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.identity import DhanIdentityProvider
from brokers.dhan.ip_management import IPManagementAdapter
from brokers.dhan.ledger import LedgerAdapter
from brokers.dhan.loader import InstrumentLoader
from brokers.dhan.margin import MarginAdapter
from brokers.dhan.market_data import MarketDataAdapter
from brokers.dhan.options import OptionsAdapter
from brokers.dhan.orders import OrdersAdapter
from brokers.dhan.portfolio import PortfolioAdapter
from brokers.dhan.resolver import SymbolResolver
from brokers.dhan.resolver_refresher import ResolverRefresher
from brokers.dhan.super_orders import SuperOrdersAdapter
from brokers.dhan.user_profile import UserProfileAdapter
from brokers.dhan.websocket import DhanMarketFeed, DhanOrderStream, PollingMarketFeed

logger = logging.getLogger(__name__)

# ── Adapter registry: (attr_name, adapter_class) ──
# Each entry constructs an adapter from (client, instruments).
# Entries are split by whether the adapter's constructor takes the
# instrument resolver as a second positional arg.
_ADAPTERS_WITH_INSTRUMENTS: list[tuple[str, type]] = [
    ("_market_data",            MarketDataAdapter),
    ("_historical",             HistoricalAdapter),
    ("_portfolio",              PortfolioAdapter),
    ("_options",                OptionsAdapter),
    ("_futures",                FuturesAdapter),
    ("_margin",                 MarginAdapter),
    ("_alerts",                 AlertsAdapter),
    ("_super_orders",           SuperOrdersAdapter),
    ("_forever_orders",         ForeverOrdersAdapter),
    ("_conditional_triggers",   ConditionalTriggersAdapter),
]

_ADAPTERS_CLIENT_ONLY: list[tuple[str, type]] = [
    ("_ledger",         LedgerAdapter),
    ("_user_profile",   UserProfileAdapter),
    ("_ip_management",  IPManagementAdapter),
    ("_edis",           EDISAdapter),
    ("_exit_all",       ExitAllAdapter),
]


class DhanConnection:
    """Concrete connection wiring all Dhan adapters.

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
        resolver: SymbolResolver | None = None,
        event_bus: EventBus | None = None,
        risk_manager: RiskManager | None = None,
        backfill_callback: Callable[[str, datetime, datetime], list[dict]] | None = None,
        reconciliation_service: object | None = None,
        lifecycle: LifecycleManager | None = None,
        allow_live_orders: bool = False,
    ):
        self._client = client
        self.instruments = resolver or SymbolResolver()
        # PR-A: single source of truth for symbol→security_id resolution.
        # All adapters that build Dhan HTTP payloads MUST go through
        # this provider rather than calling self.instruments.resolve(...)
        # directly.
        self.identity = DhanIdentityProvider(self.instruments)
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
        self._market_feed: DhanMarketFeed | None = None
        self._order_stream: DhanOrderStream | None = None
        self._polling_feed: PollingMarketFeed | None = None
        self._depth_20_feed: DhanDepth20Feed | None = None
        self._depth_200_feed: DhanDepth200Feed | None = None
        self._backfill_callback = backfill_callback
        self._reconciliation_service = reconciliation_service
        # REF-13: token-receiver registry. Any service that holds a
        # broker token (HTTP client, market feed, order stream, depth
        # feeds) registers itself here so the TokenRefreshScheduler's
        # callback can push fresh tokens to all of them in one pass.
        # The previous design hard-coded the market feed only; the
        # order stream and depth feeds silently continued with the
        # stale token until their next reconnect — that was the
        # documented DH-906-incident failure mode.
        self._token_receivers: list[Callable[[str], None]] = []
        # PR-C: ResolverRefresher. The refresher is created on first
        # registration and reused on subsequent calls. The actual
        # background thread is started by ``start_resolver_refresher``
        # (or by the LifecycleManager that owns this connection).
        self._resolver_refresher: ResolverRefresher | None = None

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
        return self._depth_20_feed

    @depth_20_feed.setter
    def depth_20_feed(self, value: DhanDepth20Feed) -> None:
        self._depth_20_feed = value

    @property
    def depth_200_feed(self) -> DhanDepth200Feed | None:
        """Active 200-level depth feed, if created."""
        return self._depth_200_feed

    @depth_200_feed.setter
    def depth_200_feed(self, value: DhanDepth200Feed) -> None:
        self._depth_200_feed = value

    @property
    def market_feed(self) -> DhanMarketFeed | None:
        """Real-time market data feed (lazy — None until explicitly created)."""
        return self._market_feed

    @market_feed.setter
    def market_feed(self, value: DhanMarketFeed) -> None:
        self._market_feed = value

    @property
    def order_stream(self) -> DhanOrderStream | None:
        """Real-time order update stream (lazy — None until explicitly created)."""
        return self._order_stream

    @order_stream.setter
    def order_stream(self, value: DhanOrderStream) -> None:
        self._order_stream = value

    def load_instruments(self, source: str | None = None, use_cache: bool = True) -> None:
        """Load instruments into memory resolver.

        PR-C: the *skipped* count returned by
        :meth:`brokers.dhan.resolver.SymbolResolver.load_from_rows` is
        logged at WARNING level when it exceeds 1% of the total row
        count. This closes the silent-failure hotspot where a partially
        broken CSV would leave the resolver incomplete without any
        operator-visible signal.
        """
        import time

        start = time.monotonic()
        if source is not None:
            if source.startswith(("http://", "https://")):
                rows = InstrumentLoader.load_from_url(source)
            else:
                rows = InstrumentLoader.load_from_file(source)
        elif use_cache:
            rows = InstrumentLoader.load_cached()
        else:
            rows = InstrumentLoader.load_cached(force_refresh=True)
        load_time = time.monotonic() - start

        logger.info(
            "instrument_load_completed",
            extra={"count": len(rows), "load_time_s": round(load_time, 2), "source": source or "cached"},
        )

        start = time.monotonic()
        stats = self.instruments.load_from_rows(rows)
        memory_time = time.monotonic() - start

        skipped = int(stats.get("skipped", 0))
        total = int(stats.get("total", len(rows)))
        if total > 0 and skipped / total > 0.01:
            logger.warning(
                "instrument_load_skipped_high",
                extra={
                    "skipped": skipped,
                    "total": total,
                    "skip_rate": round(skipped / total, 4),
                    "threshold": 0.01,
                },
            )

        logger.info(
            "instrument_memory_load_completed",
            extra={"count": len(rows), "skipped": skipped, "memory_time_s": round(memory_time, 2)},
        )

    def create_market_feed(
        self,
        access_token: str | None = None,
        instruments: list[tuple] | None = None,
        access_token_fn: Callable[[], str] | None = None,
    ) -> DhanMarketFeed:
        """Create and return a DhanMarketFeed wired with this connection's backfill callback.

        If a :class:`LifecycleManager` was supplied to the connection,
        the new feed is registered with it. The feed's start() / stop()
        / health() are then driven by the lifecycle.

        If an existing market feed is running, it is stopped first to
        prevent orphaned WebSocket threads and duplicate tick processing.
        """
        # Stop existing feed to prevent dual WebSocket connections
        if self._market_feed is not None:
            try:
                self._market_feed.stop(timeout_seconds=5.0)
            except Exception as exc:
                logger.debug("old_market_feed_stop_failed: %s", exc)

        feed = DhanMarketFeed(
            client_id=self._client.client_id,
            access_token=access_token,
            instruments=instruments or [],
            resolver=self.instruments,
            access_token_fn=access_token_fn,
            event_bus=self._event_bus,
            backfill_callback=self._backfill_callback,
        )
        self._market_feed = feed
        # REF-13: self-register as a token receiver so the scheduler
        # can push fresh tokens to the feed.
        self.register_token_receiver(feed.update_token)
        if self._lifecycle is not None and feed.name not in self._lifecycle.service_names():
            try:
                self._lifecycle.register(feed)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("lifecycle_register_failed: %s", exc)
        return feed

    def create_order_stream(
        self,
        access_token: str | None = None,
        access_token_fn: Callable[[], str] | None = None,
    ) -> DhanOrderStream:
        """Create and return a DhanOrderStream.

        If a :class:`LifecycleManager` was supplied, the new stream is
        registered with it.
        """
        stream = DhanOrderStream(
            client_id=self._client.client_id,
            access_token=access_token,
            access_token_fn=access_token_fn,
            event_bus=self._event_bus,
        )
        self._order_stream = stream
        # REF-13: order stream also receives refreshed tokens.
        self.register_token_receiver(stream.update_token)
        if self._lifecycle is not None and stream.name not in self._lifecycle.service_names():
            try:
                self._lifecycle.register(stream)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("lifecycle_register_failed: %s", exc)
        return stream

    def create_depth_20_feed(
        self,
        access_token: str | None = None,
        instrument: tuple[str, str] | None = None,
    ) -> DhanDepth20Feed:
        """Create and return a DhanDepth20Feed for 20-level depth.

        NSE Equity and Derivatives only. Max 50 instruments per connection.
        """
        feed = DhanDepth20Feed(
            client_id=self._client.client_id,
            access_token=access_token or self._client.access_token,
            instruments=[instrument] if instrument else [],
            event_bus=self._event_bus,
        )
        self._depth_20_feed = feed
        # REF-13: depth feeds receive refreshed tokens too. The feed
        # must define an update_token() method.
        if hasattr(feed, "update_token"):
            self.register_token_receiver(feed.update_token)
        if self._lifecycle is not None and feed.name not in self._lifecycle.service_names():
            try:
                self._lifecycle.register(feed)
            except Exception as exc:
                logger.debug("lifecycle_register_failed: %s", exc)
        return feed

    def create_depth_200_feed(
        self,
        access_token: str | None = None,
        instrument: tuple[str, str] | None = None,
    ) -> DhanDepth200Feed:
        """Create and return a DhanDepth200Feed for 200-level depth.

        NSE Equity and Derivatives only. Max 1 instrument per connection.
        """
        feed = DhanDepth200Feed(
            client_id=self._client.client_id,
            access_token=access_token or self._client.access_token,
            instrument=instrument,
            event_bus=self._event_bus,
        )
        self._depth_200_feed = feed
        if hasattr(feed, "update_token"):
            self.register_token_receiver(feed.update_token)
        if self._lifecycle is not None and feed.name not in self._lifecycle.service_names():
            try:
                self._lifecycle.register(feed)
            except Exception as exc:
                logger.debug("lifecycle_register_failed: %s", exc)
        return feed

    def create_polling_feed(
        self,
        instruments: list[tuple],
        interval_seconds: float = 2.0,
    ) -> PollingMarketFeed:
        """Create and return a PollingMarketFeed.

        If a :class:`LifecycleManager` was supplied, the new feed is
        registered with it.
        """
        feed = PollingMarketFeed(
            http_client=self._client,
            resolver=self.instruments,
            instruments=instruments,
            interval_seconds=interval_seconds,
        )
        self._polling_feed = feed
        if self._lifecycle is not None and feed.name not in self._lifecycle.service_names():
            try:
                self._lifecycle.register(feed)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("lifecycle_register_failed: %s", exc)
        return feed

    # ── Token-receiver registry (REF-13) ──────────────────────────────────

    def register_token_receiver(
        self, receiver: Callable[[str], None]
    ) -> Callable[[str], None]:
        """Register a callable invoked whenever a new access token arrives.

        Used by the :class:`TokenRefreshScheduler`'s ``on_refresh``
        callback to push fresh tokens to the HTTP client and every
        WebSocket / depth service. The previous design hard-coded only
        the market feed, so the order stream and depth feeds silently
        kept using the stale token until their next reconnect cycle.

        Idempotent: registering the same callable twice is a no-op.
        Returns the receiver unchanged so the call site can be used in
        an expression.
        """
        if receiver is not None and receiver not in self._token_receivers:
            self._token_receivers.append(receiver)
        return receiver

    def broadcast_token(self, new_token: str) -> int:
        """Push ``new_token`` to every registered receiver.

        Returns the number of receivers notified. Failures in any one
        receiver are logged and isolated so a single broken subscriber
        cannot block the others.
        """
        if not new_token:
            return 0
        delivered = 0
        for receiver in list(self._token_receivers):
            try:
                receiver(new_token)
                delivered += 1
            except Exception as exc:  # pragma: no cover - defensive
                receiver_name = getattr(
                    receiver, "__qualname__", repr(receiver)
                )
                logger.warning(
                    "token_receiver_failed",
                    extra={"receiver": receiver_name, "error": str(exc)},
                )
        return delivered

    # ── ResolverRefresher wiring (PR-C) ─────────────────────────────────

    def get_or_create_resolver_refresher(
        self,
        interval_seconds: int = 24 * 3600,
        on_success=None,
        on_error=None,
    ) -> ResolverRefresher:
        """Return the singleton :class:`ResolverRefresher` for this connection.

        The refresher is created lazily so unit tests that build a
        connection without ever wanting the background thread do not
        pay the cost. The lifecycle manager (if any) should call
        :meth:`register_resolver_refresher_with_lifecycle` to attach
        the refresher as a :class:`ManagedService`.
        """
        if self._resolver_refresher is None:
            self._resolver_refresher = ResolverRefresher(
                connection=self,
                interval_seconds=interval_seconds,
                on_success=on_success,
                on_error=on_error,
            )
        return self._resolver_refresher

    def register_resolver_refresher_with_lifecycle(
        self,
        interval_seconds: int = 24 * 3600,
    ) -> ResolverRefresher:
        """Create the refresher and register it with the lifecycle manager.

        No-op (returns ``None``) if the connection was constructed
        without a :class:`LifecycleManager`. Otherwise the refresher's
        start/stop/health are driven by the lifecycle and the process
        can drain it deterministically on shutdown.
        """
        if self._lifecycle is None:
            logger.debug(
                "resolver_refresher_not_registered: connection has no lifecycle manager"
            )
            return None
        refresher = self.get_or_create_resolver_refresher(
            interval_seconds=interval_seconds,
        )
        if refresher.name not in self._lifecycle.service_names():
            try:
                self._lifecycle.register(refresher)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("resolver_refresher_register_failed: %s", exc)
        return refresher

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
        # PR-C: stop the resolver refresher if one was created. The
        # lifecycle manager (when present) handles this for us, but
        # we explicitly call stop() to be safe for callers that did
        # not register the refresher with a lifecycle.
        if self._resolver_refresher is not None:
            try:
                self._resolver_refresher.stop(timeout_seconds=5.0)
            except Exception as exc:
                logger.warning("resolver_refresher_stop_failed: %s", exc)
        # Stop the WebSocket services via their ManagedService.stop()
        # method which joins the thread within timeout.
        for svc in (self._market_feed, self._order_stream, self._polling_feed,
                     self._depth_20_feed, self._depth_200_feed):
            if svc is None:
                continue
            try:
                svc.stop(timeout_seconds=5.0)
            except Exception as exc:
                logger.warning("%s_stop_failed: %s", getattr(svc, "name", svc), exc)
        self._client.close()
