"""Universe & Session — the public entry point into the domain model.

A :class:`Session` is the composition root: it binds a concrete ``DataProvider``
(and optional ``ExecutionProvider`` / ``OrderServicePort`` / ``DomainEventBus``)
once, wires the data provider as the platform default, and exposes a
:class:`Universe` for building instruments.

Institutional order spine::

    session.buy(instrument, qty) → OrderIntent → OrderServicePort (OMS+Risk)
        → ExecutionProvider → exchange

Legacy path (tests only): when ``order_service`` is omitted but
``execution_provider`` is set, Session places via ExecutionProvider directly.

    session = Session(provider, order_service=oms_service)
    reliance = session.universe.equity("RELIANCE")
    result = session.buy(reliance, 10, price=2450)

No broker, REST, WebSocket, or JSON concept appears here.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from domain.constants.market import DEFAULT_EXCHANGE
from domain.enums import OrderType, ProductType, Side
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
from domain.instruments.instrument_id import InstrumentId
from domain.orders.intent import OrderIntent
from domain.orders.placement import build_order_intent, place_via_order_service
from domain.orders.requests import OrderRequest
from domain.ports.provider_registry import get_default_provider, set_default_provider
from domain.ports.session_context import (
    activate_session,
    clear_ambient_session_if_current,
    set_ambient_session,
)

if TYPE_CHECKING:
    from domain.events.bus import DomainEventBus
    from domain.ports.order_service import OrderServicePort
    from domain.ports.protocols import DataProvider, ExecutionProvider, OrderResult


def _as_side(side: str | Side) -> Side:
    if isinstance(side, Side):
        return side
    return Side(str(side).upper())


def _as_order_type(order_type: str | OrderType) -> OrderType:
    if isinstance(order_type, OrderType):
        return order_type
    return OrderType(str(order_type).upper())


def _as_product_type(product_type: str | ProductType) -> ProductType:
    if isinstance(product_type, ProductType):
        return product_type
    return ProductType(str(product_type).upper())


class Universe:
    """Builds domain instruments from symbols. Broker-free by design."""

    def __init__(
        self,
        provider: "DataProvider",
        *,
        event_bus: "DomainEventBus | None" = None,
        execution_provider: "ExecutionProvider | None" = None,
        order_service: "OrderServicePort | None" = None,
    ) -> None:
        self._provider = provider
        self._event_bus = event_bus
        self._execution_provider = execution_provider
        self._order_service = order_service
        self._broker_facade: Any | None = None

    def _stamp(self, instrument: Instrument) -> Instrument:
        """Stamp data/execution/OMS ports + broker facade (KD-12)."""
        instrument._bind_session_ports(
            data_provider=self._provider,
            execution_provider=self._execution_provider,
            order_service=self._order_service,
        )
        if self._broker_facade is not None:
            facade = self._broker_facade
            instrument._extensions.register(facade.broker_id, facade)
            # Also register each extension by capability name (depth_20, …)
            for ext in getattr(facade, "extensions", None) or []:
                name = getattr(ext, "name", None)
                if name:
                    instrument._extensions.register(str(name), ext)
        return instrument

    def equity(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> Equity:
        return self._stamp(
            Equity(
                symbol,
                exchange,
                data_provider=self._provider,
                execution_provider=self._execution_provider,
            )
        )

    def etf(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> ETF:
        return self._stamp(
            ETF(
                symbol,
                exchange,
                data_provider=self._provider,
                execution_provider=self._execution_provider,
            )
        )

    def spot(self, symbol: str, exchange: str = "CDS") -> Spot:
        return self._stamp(
            Spot(
                symbol,
                exchange,
                data_provider=self._provider,
                execution_provider=self._execution_provider,
            )
        )

    def currency(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> Currency:
        return self._stamp(
            Currency(
                symbol,
                exchange,
                data_provider=self._provider,
                execution_provider=self._execution_provider,
            )
        )

    def index(self, name: str, exchange: str = DEFAULT_EXCHANGE) -> Index:
        return self._stamp(
            Index(
                name,
                exchange,
                data_provider=self._provider,
                execution_provider=self._execution_provider,
            )
        )

    def future(self, symbol: str, *, expiry: date, exchange: str = "NFO") -> Future:
        return self._stamp(
            Future(
                symbol,
                exchange,
                expiry=expiry,
                data_provider=self._provider,
                execution_provider=self._execution_provider,
            )
        )

    def commodity(self, symbol: str, *, expiry: date, exchange: str = "MCX") -> Commodity:
        return self._stamp(
            Commodity(
                symbol,
                exchange,
                expiry=expiry,
                data_provider=self._provider,
                execution_provider=self._execution_provider,
            )
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
        iid = InstrumentId.option(exchange, underlying, expiry, strike, right)
        return self._stamp(
            Option(
                iid,
                strike=strike,
                expiry=expiry,
                right=right,
                data_provider=self._provider,
                execution_provider=self._execution_provider,
                leg=leg,
            )
        )

    def get(self, instrument_id: InstrumentId) -> Instrument:
        """Build stamped instrument from id — dispatches to typed factories when kind known."""
        kind = instrument_id.asset_type
        if instrument_id.is_option and instrument_id.expiry and instrument_id.strike is not None:
            return self.option(
                instrument_id.underlying,
                instrument_id.strike,
                instrument_id.right or "CE",
                expiry=instrument_id.expiry,
                exchange=instrument_id.exchange,
            )
        if instrument_id.is_future and instrument_id.expiry:
            if kind == "COMMODITY":
                return self.commodity(
                    instrument_id.underlying,
                    expiry=instrument_id.expiry,
                    exchange=instrument_id.exchange,
                )
            return self.future(
                instrument_id.underlying,
                expiry=instrument_id.expiry,
                exchange=instrument_id.exchange,
            )
        if kind == "INDEX" or instrument_id.is_index:
            return self.index(instrument_id.underlying, instrument_id.exchange)
        if kind == "ETF":
            return self.etf(instrument_id.underlying, instrument_id.exchange)
        if kind == "SPOT":
            return self.spot(instrument_id.underlying, instrument_id.exchange)
        if kind == "CURRENCY":
            return self.currency(instrument_id.underlying, instrument_id.exchange)
        return self._stamp(
            Instrument(
                instrument_id,
                data_provider=self._provider,
                execution_provider=self._execution_provider,
            )
        )


class Session:
    """Composition root. Binds data, optional execution, and order service (OMS)."""

    def __init__(
        self,
        provider: "DataProvider",
        *,
        event_bus: "DomainEventBus | None" = None,
        execution_provider: "ExecutionProvider | None" = None,
        order_service: "OrderServicePort | None" = None,
        status: Any | None = None,
    ) -> None:
        self._provider = provider
        self._event_bus = event_bus
        self._execution_provider = execution_provider
        self._order_service = order_service
        self._status = status
        self._account_view = None
        # Process default + ambient (KD-1): last writer wins for default registry
        set_default_provider(provider)
        set_ambient_session(self)
        self._universe = Universe(
            provider,
            event_bus=event_bus,
            execution_provider=execution_provider,
            order_service=order_service,
        )

    @property
    def universe(self) -> Universe:
        return self._universe

    @property
    def provider(self) -> "DataProvider":
        return self._provider

    @property
    def execution_provider(self) -> "ExecutionProvider | None":
        return self._execution_provider

    @property
    def order_service(self) -> "OrderServicePort | None":
        return self._order_service

    @property
    def event_bus(self) -> "DomainEventBus | None":
        return self._event_bus

    @property
    def status(self) -> Any | None:
        """Connect readiness (mode / phase / orders_enabled). Set by ``tradex.connect``."""
        return self._status

    def attach_status(self, status: Any) -> None:
        """Attach or replace session status (composition root only)."""
        self._status = status

    def describe(self) -> dict[str, Any]:
        """Stable session summary for CLI / logs."""
        if self._status is not None and hasattr(self._status, "describe"):
            return self._status.describe()
        return {
            "orders_enabled": self._order_service is not None,
            "has_execution": self._execution_provider is not None,
        }

    def attach_broker_facade(self, broker_id: str, extensions: list[Any]) -> None:
        """Wire typed broker capabilities onto instruments created from this session."""
        from domain.extensions.facade import BrokerFacade

        self._universe._broker_facade = BrokerFacade(broker_id, extensions)

    def attach_command_dispatcher(self, dispatcher: Any) -> None:
        """Attach the CQRS CommandDispatcher (ADR-012).

        The dispatcher is the single seam for order/subscribe/history intent.
        Strategies and application code route through it rather than calling
        the OMS or brokers directly. The composition root is responsible for
        also wiring ``Session.attach_order_command_fn`` so ``Session.place``
        routes through the dispatcher without ``domain`` importing
        ``runtime.commands`` (keeps the domain layer independent).
        """
        self._command_dispatcher = dispatcher

    def attach_order_command_fn(self, fn: Any) -> None:
        """Attach the order-command closure built by the composition root (ADR-012).

        The closure converts an ``OrderIntent`` into a ``PlaceOrderCommand`` and
        adapts the ``CommandResult`` back to an ``OrderResult``. Keeping it in
        the composition root (``tradex.session``) avoids a ``domain -> runtime``
        dependency.
        """
        self._order_command_fn = fn

    def attach_query_dispatcher(self, dispatcher: Any) -> None:
        """Attach the CQRS QueryDispatcher (ADR-012).

        Read-only queries (portfolio, candles) route through this seam. Handlers
        never mutate state or publish events.
        """
        self._query_dispatcher = dispatcher

    @property
    def command_dispatcher(self) -> Any | None:
        """The CQRS CommandDispatcher, if wired at the composition root."""
        return getattr(self, "_command_dispatcher", None)

    @property
    def query_dispatcher(self) -> Any | None:
        """The CQRS QueryDispatcher, if wired at the composition root."""
        return getattr(self, "_query_dispatcher", None)

    def intent(
        self,
        instrument: Instrument,
        side: str | Side,
        quantity: int,
        price: Decimal | None = None,
        order_type: str | OrderType = OrderType.LIMIT,
        product_type: str | ProductType = ProductType.INTRADAY,
        trigger_price: Decimal | None = None,
        correlation_id: str | None = None,
    ) -> OrderIntent:
        """Build an :class:`OrderIntent` without submitting it."""
        return build_order_intent(
            instrument,
            _as_side(side),
            quantity,
            price=price,
            order_type=_as_order_type(order_type),
            product_type=_as_product_type(product_type),
            trigger_price=trigger_price,
            correlation_id=correlation_id,
        )

    def _assert_orders_enabled(self) -> None:
        if self._status is not None and not getattr(self._status, "orders_enabled", True):
            mode = getattr(self._status, "mode", "market")
            raise RuntimeError(
                "ORDERS_DISABLED: Session is market-data only "
                f"(mode={mode!r}). Reconnect with mode='trade' when ready to trade "
                "(requires process OMS via CLI/API)."
            )

    def place(self, intent: OrderIntent) -> "OrderResult":
        """Submit an intent via the injected order-command fn or OMS (fallback).

        ADR-012: when the composition root attaches an ``order_command_fn``
        (built from the CommandDispatcher), the intent is routed through the
        CQRS seam. The closure keeps ``runtime.commands`` knowledge in the
        composition root, so ``domain`` stays independent. The legacy
        OMS/ExecutionProvider paths remain as a fallback for tests.
        """
        self._assert_orders_enabled()

        fn = getattr(self, "_order_command_fn", None)
        if callable(fn):
            return fn(intent)

        if self._order_service is not None:
            return place_via_order_service(self._order_service, intent)

        if self._execution_provider is not None:
            # LEGACY TEST PATH ONLY — Instrument.buy never uses this
            return self._execution_provider.place_order(
                OrderRequest(
                    symbol=intent.symbol,
                    exchange=intent.exchange,
                    transaction_type=intent.side,
                    quantity=intent.quantity,
                    price=intent.price,
                    order_type=intent.order_type,
                    product_type=intent.product_type,
                    trigger_price=intent.trigger_price,
                    correlation_id=intent.correlation_id,
                )
            )

        raise RuntimeError(
            "No order_service (OMS) or execution_provider configured for this session. "
            "Use tradex.connect(...) which wires OrderIntent → Risk → OMS → Execution."
        )

    def cancel(self, order_id: str) -> "OrderResult":
        """Cancel via OMS OrderServicePort (fail closed in market mode)."""
        self._assert_orders_enabled()
        if self._order_service is None:
            raise RuntimeError(
                "No order_service (OMS) configured. Use tradex.connect(..., mode='sim'|'trade')."
            )
        cancel = getattr(self._order_service, "cancel", None)
        if not callable(cancel):
            raise RuntimeError("OrderServicePort does not implement cancel()")
        return cancel(order_id)

    def modify(
        self,
        order_id: str,
        *,
        quantity: int | None = None,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
        order_type: str | OrderType | None = None,
    ) -> "OrderResult":
        """Modify via OMS OrderServicePort (fail closed in market mode)."""
        from domain.orders.requests import ModifyOrderRequest

        self._assert_orders_enabled()
        if self._order_service is None:
            raise RuntimeError(
                "No order_service (OMS) configured. Use tradex.connect(..., mode='sim'|'trade')."
            )
        modify = getattr(self._order_service, "modify", None)
        if not callable(modify):
            raise RuntimeError("OrderServicePort does not implement modify()")
        ot = None
        if order_type is not None:
            ot = order_type if isinstance(order_type, OrderType) else OrderType(str(order_type).upper())
        return modify(
            ModifyOrderRequest(
                order_id=order_id,
                quantity=quantity,
                price=price,
                trigger_price=trigger_price,
                order_type=ot,
            )
        )

    @property
    def account(self):
        """AccountView — positions / holdings / funds / Portfolio (no gateway)."""
        if not hasattr(self, "_account_view") or self._account_view is None:
            from domain.portfolio.account_view import AccountView

            self._account_view = AccountView(self._execution_provider)
        return self._account_view

    def orders(self) -> list[Any]:
        """Open/working orders from OMS book when available, else EP order book."""
        oms = self._order_service
        if oms is not None:
            mgr = getattr(oms, "order_manager", None)
            if mgr is not None:
                list_fn = getattr(mgr, "get_orders", None) or getattr(mgr, "list_orders", None)
                if callable(list_fn):
                    try:
                        return list(list_fn())
                    except TypeError:
                        return list(list_fn(include_terminal=False))  # type: ignore[call-arg]
                # Fallback: internal book snapshot
                orders_map = getattr(mgr, "_orders", None)
                if isinstance(orders_map, dict):
                    return list(orders_map.values())
        if self._execution_provider is not None:
            try:
                return list(self._execution_provider.get_order_book() or [])
            except Exception:
                return []
        return []

    def _place_order(
        self,
        instrument: Instrument,
        side: str | Side,
        quantity: int,
        price: Decimal | None = None,
        order_type: str | OrderType = OrderType.LIMIT,
        product_type: str | ProductType = ProductType.INTRADAY,
        trigger_price: Decimal | None = None,
    ) -> Any:
        """Build OrderIntent and place through the institutional spine."""
        intent = self.intent(
            instrument,
            side,
            quantity,
            price=price,
            order_type=order_type,
            product_type=product_type,
            trigger_price=trigger_price,
        )
        return self.place(intent)

    def buy(
        self,
        instrument: Instrument,
        quantity: int,
        price: Decimal | None = None,
        order_type: str | OrderType = OrderType.LIMIT,
        product_type: str | ProductType = ProductType.INTRADAY,
    ) -> Any:
        """Place a buy order (OrderIntent → OMS when wired)."""
        return self._place_order(
            instrument, Side.BUY, quantity, price, order_type, product_type
        )

    def sell(
        self,
        instrument: Instrument,
        quantity: int,
        price: Decimal | None = None,
        order_type: str | OrderType = OrderType.LIMIT,
        product_type: str | ProductType = ProductType.INTRADAY,
    ) -> Any:
        """Place a sell order (OrderIntent → OMS when wired)."""
        return self._place_order(
            instrument, Side.SELL, quantity, price, order_type, product_type
        )

    def market(
        self,
        instrument: Instrument,
        quantity: int,
        side: str | Side = Side.BUY,
    ) -> Any:
        """Place a market order for the given instrument."""
        resolved = _as_side(side)
        return self._place_order(
            instrument, resolved, quantity, order_type=OrderType.MARKET
        )

    def limit(
        self,
        instrument: Instrument,
        quantity: int,
        price: Decimal,
        side: str | Side = Side.BUY,
    ) -> Any:
        """Place a limit order for the given instrument."""
        resolved = _as_side(side)
        return self._place_order(
            instrument, resolved, quantity, price=price, order_type=OrderType.LIMIT
        )

    def stop_loss(
        self,
        instrument: Instrument,
        quantity: int,
        trigger_price: Decimal,
        side: str | Side = Side.BUY,
    ) -> Any:
        """Place a stop-loss market order for the given instrument."""
        resolved = _as_side(side)
        return self._place_order(
            instrument,
            resolved,
            quantity,
            order_type=OrderType.STOP_LOSS_MARKET,
            trigger_price=trigger_price,
        )

    def activate(self):
        """Nested-safe ambient activation (notebook multi-session).

        Usage::

            with session.activate():
                Equity("RELIANCE").refresh()
        """
        return activate_session(self)

    # ── Instrument resolution & batch quotes (TH-3; still instrument OOP) ─

    def resolve(
        self,
        name: str,
        *,
        default_exchange: str = DEFAULT_EXCHANGE,
        default_year: int | None = None,
    ) -> Instrument:
        """Resolve a display or canonical name to a stamped :class:`Instrument`.

        Uses :class:`~domain.instruments.resolver.InstrumentResolver` when
        attached, else :func:`parse_display_name` + :meth:`Universe.get`.
        """
        resolver = getattr(self, "_resolver", None)
        if resolver is not None:
            iid = resolver.resolve(
                name, default_exchange=default_exchange, default_year=default_year
            )
        else:
            from domain.instruments.display_names import parse_display_name

            iid = parse_display_name(
                name,
                default_exchange=default_exchange,
                default_year=default_year,
            )
        return self._universe.get(iid)

    def doctor(self, name: str) -> dict:
        """Name-resolution diagnostics (canonical, display, suggestions)."""
        resolver = getattr(self, "_resolver", None)
        if resolver is None:
            from domain.instruments.resolver import InstrumentResolver

            resolver = InstrumentResolver()
        return resolver.doctor(name)

    def instrument(
        self,
        name: str,
        *,
        default_exchange: str = DEFAULT_EXCHANGE,
        default_year: int | None = None,
    ) -> Instrument:
        """Alias for :meth:`resolve` — instrument-first entry by friendly name."""
        return self.resolve(
            name, default_exchange=default_exchange, default_year=default_year
        )

    def quote_many(
        self,
        names: list[str] | tuple[str, ...],
        *,
        default_exchange: str = DEFAULT_EXCHANGE,
    ) -> dict[str, Any]:
        """Refresh quotes for many display names → ``{name: QuoteSnapshot|None}``.

        Prefers ``DataProvider.get_quotes_batch`` when available; otherwise
        resolves each name to an Instrument and calls ``refresh()``.
        """
        instruments: list[tuple[str, Instrument]] = []
        for name in names:
            instruments.append(
                (name, self.resolve(name, default_exchange=default_exchange))
            )

        ids = [inst.id for _, inst in instruments]
        batch_fn = getattr(self._provider, "get_quotes_batch", None)
        out: dict[str, Any] = {}
        if callable(batch_fn) and ids:
            try:
                quotes = list(batch_fn(ids))
                if len(quotes) == len(ids):
                    for (name, _inst), q in zip(instruments, quotes, strict=True):
                        out[name] = q
                    return out
            except Exception:
                pass

        # Fallback: instrument.refresh() (OOP path — always correct)
        for name, inst in instruments:
            try:
                out[name] = inst.refresh()
            except Exception:
                out[name] = None
        return out

    def ltp_many(
        self,
        names: list[str] | tuple[str, ...],
        *,
        default_exchange: str = DEFAULT_EXCHANGE,
    ) -> dict[str, Decimal | None]:
        """Last-traded prices for friendly names → ``{name: Decimal|None}``."""
        quotes = self.quote_many(names, default_exchange=default_exchange)
        result: dict[str, Decimal | None] = {}
        for name, q in quotes.items():
            if q is None:
                result[name] = None
                continue
            ltp = getattr(q, "ltp", None)
            if ltp is None:
                result[name] = None
            else:
                result[name] = ltp if isinstance(ltp, Decimal) else Decimal(str(ltp))
        return result

    def option_chain(
        self,
        underlying: str,
        *,
        expiry: date | int | str | None = None,
        exchange: str = DEFAULT_EXCHANGE,
    ):
        """Convenience: ``universe.index(underlying).option_chain(expiry=…)``.

        Returns the same instrument-based :class:`OptionChain` aggregate.
        """
        return self._universe.index(underlying, exchange=exchange).option_chain(expiry)

    @property
    def dx(self) -> "SessionDx":
        """Thin TradeHull-shaped aliases over this Session (optional DX layer).

        Does **not** replace Instrument OOP — every method resolves to
        ``Instrument`` / ``OptionChain`` / OMS under the hood.
        """
        return SessionDx(self)

    def close(self) -> None:
        """Release default provider and ambient if still owned by this Session.

        Safe multi-session: closing A while B is open must not clear B's
        process default provider.

        Also stops an optional composition-root SessionRecorder if attached
        (``_session_recorder``); failures never raise.
        """
        recorder = getattr(self, "_session_recorder", None)
        if recorder is not None:
            try:
                stop = getattr(recorder, "stop", None)
                if callable(stop):
                    stop()
            except Exception:
                pass
            try:
                self._session_recorder = None  # type: ignore[attr-defined]
            except Exception:
                pass
        if get_default_provider() is self._provider:
            set_default_provider(None)
        clear_ambient_session_if_current(self)


class SessionDx:
    """Optional L1 DX facade — thin aliases, instrument OOP underneath.

    Prefer ``session.universe.equity(...)`` / ``instrument.buy`` for new code.
    This surface exists for TradeHull mental-model parity only.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_ltp_data(
        self, names: str | list[str] | tuple[str, ...]
    ) -> dict[str, Decimal | None]:
        if isinstance(names, str):
            names = [names]
        return self._session.ltp_many(list(names))

    def get_quote_data(
        self, names: str | list[str] | tuple[str, ...]
    ) -> dict[str, Any]:
        if isinstance(names, str):
            names = [names]
        return self._session.quote_many(list(names))

    def atm_strikes(self, underlying: str, expiry: int | date | str = 0):
        """Return ``(ce, pe, strike)`` Option instruments at ATM."""
        chain = self._session.option_chain(underlying, expiry=expiry)
        sel = chain.select_strikes("ATM")
        return sel.ce, sel.pe, sel.strike

    def otm_strikes(
        self, underlying: str, expiry: int | date | str = 0, steps: int = 1
    ):
        """Return ``(ce, pe, ce_strike, pe_strike)`` OTM Option instruments."""
        chain = self._session.option_chain(underlying, expiry=expiry)
        sel = chain.select_strikes("OTM", steps=steps)
        return sel.ce, sel.pe, sel.ce_strike, sel.pe_strike

    def itm_strikes(
        self, underlying: str, expiry: int | date | str = 0, steps: int = 1
    ):
        chain = self._session.option_chain(underlying, expiry=expiry)
        sel = chain.select_strikes("ITM", steps=steps)
        return sel.ce, sel.pe, sel.ce_strike, sel.pe_strike

    def resolve(self, name: str) -> Instrument:
        return self._session.resolve(name)
