"""BrokerSession — the public entry point of the Trading OS broker layer.

Domain-centric public API::

    from brokers import BrokerSession

    session = BrokerSession.connect("paper")  # or "dhan" / "upstox"
    stock = session.stock("RELIANCE")
    stock.refresh()                          # market data on Instrument
    session.gateway.place_order(...)         # broker ops on Gateway
    session.gateway.subscribe([stock])
    session.extension(SomeExtension)         # broker-specific only

Infrastructure (auth, websocket, symbol master) stays inside the selected plugin.
"""

from __future__ import annotations

from datetime import date
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
from domain.market_enums import ExchangeId
from domain.options.option_chain import OptionChain
from domain.universe import Session as DomainSession
from runtime.session_historical import fetch_historical_sync
from runtime.session_opener import get_session_opener


def _ensure_session_opener() -> None:
    """Wire tradex.open_session if composition root has not registered an opener."""
    try:
        get_session_opener()
    except RuntimeError:
        from runtime.session_opener import set_session_opener
        from tradex.session import open_session

        set_session_opener(open_session)


def _ensure_domain_ports_wired() -> None:
    """Wire domain ports (async runner, audit sink, etc.) if standalone.

    ``BrokerSession.connect()`` is a public entrypoint that bypasses
    ``runtime.factory.build()`` — without this, async-backed provider
    features (e.g. Upstox websocket/portfolio streams) silently fail to
    start with "Async runner not wired". ``wire_domain_port_sinks`` is
    idempotent, so this is a no-op when the real composition root already
    ran it.
    """
    from runtime.kernel import ProcessKernel

    ProcessKernel.wire()


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
        _ensure_session_opener()
        _ensure_domain_ports_wired()
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
        if self._probe_session_health():
            self._session_state = transition_state(
                self._session_state, BrokerSessionState.HEALTHY
            )
        else:
            self._session_state = transition_state(
                self._session_state, BrokerSessionState.DEGRADED
            )
        self._runtime = RuntimeBundle(session=self._session)
        self._runtime.record_startup()
        self._gateway: Any | None = None
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
    def gateway(self):
        """Broker operations facade (orders, portfolio, subscribe)."""
        if self._gateway is None:
            from brokers.gateway import BrokerGateway

            self._gateway = BrokerGateway(self._runtime, self._session)
        return self._gateway

    def extension(self, ext_type: type) -> Any:
        """Return a registered broker-specific extension matching ``ext_type``.

        Raises
        ------
        LookupError
            If no matching extension is stamped on this session.
        """
        facade = getattr(self._session.universe, "_broker_facade", None)
        extensions = list(getattr(facade, "extensions", None) or [])
        for ext in extensions:
            if isinstance(ext, ext_type):
                return ext
            if type(ext) is ext_type:
                return ext
        wanted = getattr(ext_type, "name", None) or getattr(ext_type, "__name__", str(ext_type))
        for ext in extensions:
            if getattr(ext, "name", None) == wanted:
                return ext
            if type(ext).__name__ == wanted:
                return ext
        raise LookupError(
            f"Extension {ext_type!r} is not registered for broker {self._broker_id!r}. "
            f"Available: {[type(e).__name__ for e in extensions] or 'none'}"
        )

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

    def _probe_session_health(self) -> bool:
        """Health probe before HEALTHY — auth + transport must be usable."""
        try:
            domain_session = self._session
            provider = getattr(domain_session, "provider", None)
            gateway = getattr(provider, "gateway", None) if provider else None
            if gateway is not None:
                auth = getattr(gateway, "authenticate", None)
                if callable(auth) and not auth():
                    return False
                describe = getattr(gateway, "describe", None)
                if callable(describe):
                    info = describe()
                    if isinstance(info, dict) and not info.get("connected", True):
                        return False
            status = getattr(domain_session, "status", None)
            if status is not None and hasattr(status, "authenticated"):
                if not bool(getattr(status, "authenticated", True)):
                    return False
            return True
        except Exception:
            return False

    @property
    def status(self) -> BrokerSessionStatus:
        """Unified broker session snapshot (FSM + connect readiness)."""
        return build_session_status(
            state=self._session_state,
            connect_status=self._session.status,
            broker_id=self._broker_id,
        )

    # ── Instrument builders (return rich domain objects) ──────────────

    def stock(self, symbol: str, exchange: str = ExchangeId.NSE) -> Equity:
        """Cash equity instrument (e.g. RELIANCE)."""
        return self._session.universe.equity(symbol, exchange)

    # Alias for clarity / parity with the spec's ``session.equity``.
    equity = stock

    def etf(self, symbol: str, exchange: str = ExchangeId.NSE) -> ETF:
        return self._session.universe.etf(symbol, exchange)

    def index(self, name: str, exchange: str = ExchangeId.NSE) -> Index:
        return self._session.universe.index(name, exchange)

    def spot(self, symbol: str, exchange: str = "CDS") -> Spot:
        return self._session.universe.spot(symbol, exchange)

    def currency(self, symbol: str, exchange: str = ExchangeId.NSE) -> Currency:
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
        exchange: str = ExchangeId.NSE,
    ) -> OptionChain:
        """Option chain as a rich aggregate composed of ``Option`` instruments."""
        return self._session.option_chain(underlying, expiry=expiry, exchange=exchange)

    # ── Convenience data actions (delegate to the instrument's behavior) ─

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

    @property
    def account(self) -> Any:
        """Portfolio account (positions, holdings, funds). Prefer ``session.gateway``."""
        return self._session.account

    def instrument_id(self, symbol: str, exchange: str = ExchangeId.NSE) -> str:
        """Resolve symbol to canonical instrument id string."""
        return str(self.stock(symbol, exchange=exchange).id)

    def broker_capabilities(self, symbol: str = "RELIANCE") -> dict[str, Any]:
        """Full broker capability matrix + extension names."""
        from brokers.services.capabilities import format_session_capabilities

        return format_session_capabilities(self, symbol)

    def close(self) -> None:
        from domain.ports.broker_session_state import force_session_state

        self._publish_lifecycle_event("BROKER_DISCONNECTED")
        if self._session_state != BrokerSessionState.SHUTDOWN:
            self._session_state = force_session_state(BrokerSessionState.SHUTDOWN)
        self._session.close()

    def __repr__(self) -> str:
        return f"BrokerSession(broker={self._broker_id!r})"
