"""BrokerSession — the public entry point of the Trading OS broker layer.

A ``BrokerSession`` is a thin, broker-agnostic facade over the composition-root
``Session`` (``tradex.connect``). It exposes the flat, object-first API the
platform is designed around::

    from brokers.session import BrokerSession

    session = BrokerSession("paper")                 # or "dhan" / "upstox"
    stock = session.stock("RELIANCE")                # -> Equity (rich domain object)
    stock.refresh()
    chain = session.option_chain("NIFTY")            # -> OptionChain (composed Options)
    ce = chain.atm                                   # -> Option

No gateway, adapter, or client type is exposed here. Market behavior lives on
the returned ``Instrument`` objects; broker-specific superpowers live behind
``instrument.broker.*``. Infrastructure (auth, websocket, symbol master) is
hidden inside the broker plugin selected by ``BrokerSession``.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Callable

from brokers.runtime import RuntimeBundle
from domain.instruments.instrument import (
    Commodity,
    Currency,
    Equity,
    ETF,
    Future,
    Index,
    Instrument,
    Option,
    Spot,
)
from domain.options.option_chain import OptionChain
from domain.universe import Session as DomainSession
from domain.candles.historical import HistoricalSeries, InstrumentRef
from application.data.historical_coordinator import HistoricalQuery
from runtime.session_opener import get_session_opener


class BrokerSession:
    """Public, broker-agnostic market-access session (Trading OS).

    Wraps a composition-root ``Session`` and returns rich domain objects.
    Adding a broker requires only a new plugin package that self-registers —
    no central switch statement is touched here.
    """

    def __init__(
        self,
        broker: str = "paper",
        *,
        mode: str | None = None,
        event_bus: Any | None = None,
        env_path: str | None = None,
        load_instruments: bool = True,
        run_selftest: bool = False,
        **kwargs: Any,
    ) -> None:
        self._broker_id = (broker or "paper").lower().strip()
        self._session: DomainSession = get_session_opener()(
            self._broker_id,
            mode=mode,
            event_bus=event_bus,
            env_path=env_path,
            load_instruments=load_instruments,
            run_selftest=run_selftest,
            **kwargs,
        )
        self._runtime = RuntimeBundle(session=self._session)
        self._runtime.record_startup()

    @classmethod
    def connect(cls, broker: str = "paper", **kwargs: Any) -> "BrokerSession":
        """Trading OS startup entry: load plugin → auth → symbols → caps → ready.

        Equivalent to ``BrokerSession(broker, ...)``; named ``connect`` to match
        the documented startup flow and ``tradex.connect`` mental model.
        """
        return cls(broker, **kwargs)

    # ── Identity ──────────────────────────────────────────────────────

    @property
    def runtime(self) -> RuntimeBundle:
        """Session-scoped runtime coordinators (subscribe/history/quote/execute)."""
        return self._runtime

    @property
    def broker_id(self) -> str:
        return self._broker_id

    @property
    def session(self) -> DomainSession:
        """Underlying composition-root session (escape hatch; prefer objects)."""
        return self._session

    @property
    def universe(self):
        return self._session.universe

    @property
    def provider(self):
        return self._session.provider

    @property
    def status(self) -> Any | None:
        return self._session.status

    # ── Instrument builders (return rich domain objects) ──────────────

    def stock(self, symbol: str, exchange: str = "NSE") -> Equity:
        """Cash equity instrument (e.g. RELIANCE)."""
        return self._session.universe.equity(symbol, exchange)

    # Alias for clarity / parity with the spec's ``session.equity``.
    equity = stock

    def etf(self, symbol: str, exchange: str = "NSE") -> ETF:
        return self._session.universe.etf(symbol, exchange)

    def index(self, name: str, exchange: str = "NSE") -> Index:
        return self._session.universe.index(name, exchange)

    def spot(self, symbol: str, exchange: str = "CDS") -> Spot:
        return self._session.universe.spot(symbol, exchange)

    def currency(self, symbol: str, exchange: str = "NSE") -> Currency:
        return self._session.universe.currency(symbol, exchange)

    def future(
        self, symbol: str, *, expiry: date, exchange: str = "NFO"
    ) -> Future:
        return self._session.universe.future(symbol, expiry=expiry, exchange=exchange)

    def commodity(
        self, symbol: str, *, expiry: date, exchange: str = "MCX"
    ) -> Commodity:
        return self._session.universe.commodity(
            symbol, expiry=expiry, exchange=exchange
        )

    def option(
        self,
        underlying: str,
        strike: Any,
        right: str,
        *,
        expiry: date,
        exchange: str = "NFO",
        leg: Any | None = None,
    ) -> Option:
        return self._session.universe.option(
            underlying, strike, right, expiry=expiry, exchange=exchange, leg=leg
        )

    def option_chain(
        self,
        underlying: str,
        *,
        expiry: date | int | str | None = None,
        exchange: str = "NSE",
    ) -> OptionChain:
        """Option chain as a rich aggregate composed of ``Option`` instruments."""
        return self._session.option_chain(
            underlying, expiry=expiry, exchange=exchange
        )

    # ── Convenience data actions (delegate to the instrument's behavior) ─

    def quote(self, instrument: Instrument):
        """Refresh and return the instrument's latest quote."""
        return self._runtime.quotes.quote(instrument)

    def history(
        self,
        instrument: Instrument,
        timeframe: str = "1D",
        days: int = 120,
    ):
        """Return a ``HistoricalSeries`` for the instrument.

        Routes through the single federated path — ``HistoricalDataCoordinator``
        — the same engine the live API uses, so ``BrokerSession`` and the API
        share identical chunking, conflict resolution, gap detection and
        provenance (zero-parity). The coordinator returns a degraded series
        (with explicit ``gaps``) on partial failure rather than raising, so
        callers can inspect ``series.is_degraded``.
        """
        coordinator = self._build_historical_coordinator()
        today = date.today()
        query = HistoricalQuery(
            instrument=InstrumentRef(symbol=instrument.symbol, exchange=instrument.exchange),
            timeframe=timeframe,
            from_date=today - timedelta(days=days),
            to_date=today,
        )
        series, _ = coordinator.fetch_sync(query)
        return series

    def history_batch(
        self,
        instruments: list[Instrument],
        timeframe: str = "1D",
        days: int = 120,
    ) -> dict[str, "HistoricalSeries"]:
        """Fetch history for multiple instruments via the federated coordinator.

        Returns a dict mapping each symbol to its ``HistoricalSeries``. Each
        instrument keeps its own exchange; all share one coordinator instance
        (and therefore one rate limiter / quota scheduler).
        """
        if not instruments:
            return {}
        coordinator = self._build_historical_coordinator()
        today = date.today()
        result_map: dict[str, HistoricalSeries] = {}
        for inst in instruments:
            query = HistoricalQuery(
                instrument=InstrumentRef(symbol=inst.symbol, exchange=inst.exchange),
                timeframe=timeframe,
                from_date=today - timedelta(days=days),
                to_date=today,
            )
            series, _ = coordinator.fetch_sync(query)
            result_map[inst.symbol] = series
        return result_map

    def _build_historical_coordinator(self):
        """Construct a single-broker ``HistoricalDataCoordinator`` for this session.

        Wraps this session's wire adapter (``provider._gw``) in the
        ``CommonBrokerGateway`` adapter and registers it with a fresh
        registry/router/quota scheduler. This is the 3-line coordinator
        construction (registry + router + quota_fn) inlined — no new module.
        """
        from application.composer.registry import BrokerRegistry
        from application.composer.router import BrokerRouter
        from application.data.historical_coordinator import (
            HistoricalDataCoordinator,
        )
        from application.scheduling.quota_scheduler import QuotaScheduler, PriorityClass
        from domain.policies.source_selection import auto_dual_broker_policy
        from infrastructure.adapters.market_data_gateway_adapter import (
            MarketDataGatewayAdapter,
        )

        provider = self._session.provider
        gw = getattr(provider, "_gw", None)
        if gw is None:
            raise RuntimeError(
                f"broker {self._broker_id!r} has no wire adapter (provider._gw is None)"
            )

        caps_fn = getattr(gw, "capabilities", None)
        if not callable(caps_fn):
            raise RuntimeError(
                f"broker {self._broker_id!r} wire adapter has no capabilities()"
            )
        caps = caps_fn()
        if caps is None or not getattr(caps, "supports_historical_data", False):
            raise RuntimeError(
                f"broker {self._broker_id!r} does not support historical data"
            )

        adapter = MarketDataGatewayAdapter(gw, broker_id=self._broker_id, capabilities=caps)
        registry = BrokerRegistry()
        registry.register(adapter)
        scheduler = QuotaScheduler()
        for profile in caps.rate_limit_profiles:
            scheduler.register_profile(self._broker_id, profile)
        router = BrokerRouter(
            registry,
            auto_dual_broker_policy(),
            quota_headroom_fn=scheduler.headroom_for,
        )
        return HistoricalDataCoordinator(
            registry=registry,
            router=router,
            quota_fn=lambda bid, ep, pri: scheduler.acquire(
                bid, ep, PriorityClass[pri]
            ),
        )

    def subscribe(
        self,
        instrument: Instrument,
        callback: Callable | None = None,
        *,
        depth: bool = False,
    ):
        """Subscribe an instrument to live data; returns a subscription handle."""
        return self._runtime.subscriptions.subscribe(instrument, callback, depth=depth)

    def unsubscribe(self, instrument: Instrument) -> None:
        self._runtime.subscriptions.unsubscribe(instrument)

    # ── Trading (delegates to the institutional OMS spine) ────────────

    def buy(
        self,
        instrument: Instrument,
        quantity: int,
        price: Decimal | None = None,
        order_type: str = "LIMIT",
        product_type: str = "INTRADAY",
    ):
        return self._runtime.execution.buy(
            instrument, quantity, price, order_type=order_type, product_type=product_type
        )

    def sell(
        self,
        instrument: Instrument,
        quantity: int,
        price: Decimal | None = None,
        order_type: str = "LIMIT",
        product_type: str = "INTRADAY",
    ):
        return self._runtime.execution.sell(
            instrument, quantity, price, order_type=order_type, product_type=product_type
        )

    @property
    def account(self) -> Any:
        """Portfolio account (positions, holdings, funds)."""
        return self._session.account

    def orders(self) -> list[Any]:
        """Open and recent orders from the session OMS spine."""
        return self._runtime.execution.orders()

    def cancel(self, order_id: str) -> Any:
        """Cancel an order by id."""
        return self._session.cancel(order_id)

    def modify(self, order_id: str, **changes: Any) -> Any:
        """Modify an existing order."""
        return self._session.modify(order_id, **changes)

    def instrument_id(self, symbol: str, exchange: str = "NSE") -> str:
        """Resolve symbol to canonical instrument id string."""
        return str(self.stock(symbol, exchange=exchange).id)

    def broker_capabilities(self, symbol: str = "RELIANCE") -> dict[str, Any]:
        """Full broker capability matrix + extension names."""
        from brokers.services.core import format_session_capabilities

        return format_session_capabilities(self, symbol)

    def close(self) -> None:
        self._session.close()

    def __repr__(self) -> str:
        return f"BrokerSession(broker={self._broker_id!r})"