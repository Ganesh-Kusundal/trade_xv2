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

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

from brokers.runtime import RuntimeBundle
from domain.candles.historical import HistoricalSeries
from domain.ports.broker_session_state import (
    BrokerSessionState,
    BrokerSessionStatus,
    build_session_status,
    transition_state,
)
from domain.instruments.instrument import (
    ETF,
    Commodity,
    Currency,
    Equity,
    Future,
    Index,
    Instrument,
    Option,
    Spot,
)
from domain.options.option_chain import OptionChain
from domain.universe import Session as DomainSession
from runtime.session_historical import fetch_historical_sync
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
        self._session_state = BrokerSessionState.CREATED
        self._session_state = transition_state(self._session_state, BrokerSessionState.INITIALIZING)
        self._session: DomainSession = get_session_opener()(
            self._broker_id,
            mode=mode,
            event_bus=event_bus,
            env_path=env_path,
            load_instruments=load_instruments,
            run_selftest=run_selftest,
            **kwargs,
        )
        self._session_state = transition_state(
            self._session_state, BrokerSessionState.AUTHENTICATING
        )
        self._session_state = transition_state(self._session_state, BrokerSessionState.CONNECTED)
        self._session_state = transition_state(self._session_state, BrokerSessionState.HEALTHY)
        self._runtime = RuntimeBundle(session=self._session)
        self._runtime.record_startup()
        self._publish_lifecycle_event("BROKER_CONNECTED")

    @classmethod
    def connect(cls, broker: str = "paper", **kwargs: Any) -> BrokerSession:
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
    def session_state(self) -> BrokerSessionState:
        """Unified broker session FSM state."""
        return self._session_state

    def _publish_lifecycle_event(self, event_name: str, **payload: Any) -> None:
        bus = self._session.event_bus
        if bus is None:
            return
        from domain.events.types import DomainEvent, EventType

        try:
            event_type = EventType[event_name]
        except KeyError:
            return
        event = DomainEvent.now(
            event_type=event_type.value,
            payload={"broker_id": self._broker_id, **payload},
            source=self._broker_id,
        )
        bus.publish(event)

    def _set_session_state(self, target: BrokerSessionState) -> None:
        self._session_state = transition_state(self._session_state, target)

    @property
    def status(self) -> BrokerSessionStatus:
        """Unified broker session snapshot (FSM + connect readiness)."""
        return build_session_status(
            state=self._session_state,
            connect_status=self._session.status,
            broker_id=self._broker_id,
        )

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

    def future(self, symbol: str, *, expiry: date, exchange: str = "NFO") -> Future:
        return self._session.universe.future(symbol, expiry=expiry, exchange=exchange)

    def commodity(self, symbol: str, *, expiry: date, exchange: str = "MCX") -> Commodity:
        return self._session.universe.commodity(symbol, expiry=expiry, exchange=exchange)

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
        return self._session.option_chain(underlying, expiry=expiry, exchange=exchange)

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
        return fetch_historical_sync(
            self._session,
            symbol=instrument.symbol,
            exchange=instrument.exchange,
            timeframe=timeframe,
            days=days,
        )

    def history_batch(
        self,
        instruments: list[Instrument],
        timeframe: str = "1D",
        days: int = 120,
    ) -> dict[str, HistoricalSeries]:
        """Fetch history for multiple instruments via the federated coordinator.

        Returns a dict mapping each symbol to its ``HistoricalSeries``. Each
        instrument keeps its own exchange; all share one coordinator instance
        (and therefore one rate limiter / quota scheduler).
        """
        if not instruments:
            return {}
        result_map: dict[str, HistoricalSeries] = {}
        for inst in instruments:
            series = fetch_historical_sync(
                self._session,
                symbol=inst.symbol,
                exchange=inst.exchange,
                timeframe=timeframe,
                days=days,
            )
            result_map[inst.symbol] = series
        return result_map

    def _build_historical_coordinator(self):
        """Return a session-scoped historical coordinator via composition root."""
        from runtime.session_historical import build_historical_coordinator

        return build_historical_coordinator(self._session)

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
        from domain.ports.broker_session_state import force_session_state

        self._publish_lifecycle_event("BROKER_DISCONNECTED")
        if self._session_state != BrokerSessionState.SHUTDOWN:
            self._session_state = force_session_state(BrokerSessionState.SHUTDOWN)
        self._session.close()

    def __repr__(self) -> str:
        return f"BrokerSession(broker={self._broker_id!r})"
