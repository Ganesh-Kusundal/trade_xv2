"""DhanConnection — wires all adapters with shared HTTP client + resolver."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from brokers.common.event_bus import EventBus
from brokers.common.lifecycle import LifecycleManager
from brokers.common.oms.risk_manager import RiskManager
from brokers.dhan.alerts import AlertsAdapter
from brokers.dhan.depth_20 import DhanDepth20Feed
from brokers.dhan.depth_200 import DhanDepth200Feed
from brokers.dhan.futures import FuturesAdapter
from brokers.dhan.historical import HistoricalAdapter
from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.loader import InstrumentLoader
from brokers.dhan.margin import MarginAdapter
from brokers.dhan.market_data import MarketDataAdapter
from brokers.dhan.options import OptionsAdapter
from brokers.dhan.orders import OrdersAdapter
from brokers.dhan.portfolio import PortfolioAdapter
from brokers.dhan.resolver import SymbolResolver
from brokers.dhan.websocket import DhanMarketFeed, DhanOrderStream, PollingMarketFeed

logger = logging.getLogger(__name__)


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
    ):
        self._client = client
        self.instruments = resolver or SymbolResolver()
        self._event_bus = event_bus
        # B5: if a lifecycle is provided, lazily-created WebSocket
        # services will be registered with it. close() then drains
        # every thread within bounded timeouts.
        self._lifecycle = lifecycle

        self._market_data = MarketDataAdapter(client, self.instruments)
        self._historical = HistoricalAdapter(client, self.instruments)
        self._orders = OrdersAdapter(
            client, self.instruments, event_bus=event_bus, risk_manager=risk_manager
        )
        self._portfolio = PortfolioAdapter(client, self.instruments)
        self._options = OptionsAdapter(client, self.instruments)
        self._futures = FuturesAdapter(client, self.instruments)
        self._margin = MarginAdapter(client, self.instruments)
        self._alerts = AlertsAdapter(client, self.instruments)
        self._market_feed: DhanMarketFeed | None = None
        self._order_stream: DhanOrderStream | None = None
        self._polling_feed: PollingMarketFeed | None = None
        self._depth_20_feed: DhanDepth20Feed | None = None
        self._depth_200_feed: DhanDepth200Feed | None = None
        self._backfill_callback = backfill_callback
        self._reconciliation_service = reconciliation_service

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
    def backfill_callback(self) -> Callable[[str, datetime, datetime], list[dict]] | None:
        """Backfill callback for market feed reconnect gap fill."""
        return self._backfill_callback

    @property
    def reconciliation_service(self) -> object | None:
        """Reconciliation service wired into the trading context."""
        return self._reconciliation_service

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
        """Load instruments into memory resolver."""
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
        self.instruments.load_from_rows(rows)
        memory_time = time.monotonic() - start

        logger.info(
            "instrument_memory_load_completed",
            extra={"count": len(rows), "memory_time_s": round(memory_time, 2)},
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
        """
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
        # Stop the WebSocket services via their ManagedService.stop()
        # method which joins the thread within timeout.
        for svc in (self._market_feed, self._order_stream, self._polling_feed):
            if svc is None:
                continue
            try:
                svc.stop(timeout_seconds=5.0)
            except Exception as exc:
                logger.warning("%s_stop_failed: %s", getattr(svc, "name", svc), exc)
        self._client.close()
