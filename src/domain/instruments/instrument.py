"""Instrument — pure domain object. No wrappers. No shims.

This is what a trader interacts with:

    nifty = Index("NIFTY")
    nifty.ltp
    nifty.subscribe()
    nifty.option_chain().atm.greeks.delta

The broker is never referenced here.
It lives behind the DataProvider/ExecutionProvider ports,
set at the composition root.
"""

from __future__ import annotations

import logging
import threading
import weakref
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable

logger = logging.getLogger(__name__)

from domain.candles.historical import HistoricalSeries, InstrumentRef
from domain.candles.instrument_history import InstrumentHistory
from domain.entities.market import MarketDepth, QuoteSnapshot
from domain.entities.options import FutureChain
from domain.entities.options import OptionChain as OptionChainVO
from domain.enums import OrderType, ProductType, Side
from domain.instruments.composition import (
    ExtensionManager,
    InstrumentIdentity,
    TradingSpec,
)
from domain.instruments.instrument_id import InstrumentId
from domain.orders.placement import build_order_intent, place_via_order_service
from domain.value_objects.state import (
    InstrumentState,
    SubscriptionState,
    SubscriptionStatus,
)

if TYPE_CHECKING:
    from domain.ports.order_service import OrderServicePort
    from domain.ports.protocols import DataProvider, ExecutionProvider, OrderResult, SubscriptionHandle


# ══════════════════════════════════════════════════════════════════════
# Instrument (base)
# ══════════════════════════════════════════════════════════════════════


class Instrument:
    """Pure domain object. Users work with this directly.

    Owns:
        - Identity (InstrumentId)
        - State (InstrumentState) — replaced atomically

    Delegates to:
        - DataProvider for market data
        - ExecutionProvider for orders

    Does NOT own:
        - Broker connection (provider does)
        - WebSocket management (provider does)
        - Historical storage (provider does)
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        *,
        data_provider: DataProvider | None = None,
        execution_provider: ExecutionProvider | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._identity = InstrumentIdentity(instrument_id)
        self._id = instrument_id  # ponytail: keep _id alias for existing call sites
        self._provider = data_provider
        self._executor = execution_provider
        self._metadata = metadata or {}
        self._trading = TradingSpec.from_metadata(self._metadata)
        self._state = InstrumentState()
        self._subscription: SubscriptionHandle | None = None
        self._callbacks: dict[str, list[Callable]] = {
            "tick": [],
            "quote": [],
            "depth": [],
            "disconnect": [],
            "reconnect": [],
        }
        self._extensions = ExtensionManager()
        self._lock = threading.RLock()  # Thread-safety for state mutations
        self._order_service_ref: weakref.ref | None = None
        self._history = InstrumentHistory(self)

    def _bind_session_ports(
        self,
        *,
        data_provider: "DataProvider | None" = None,
        execution_provider: "ExecutionProvider | None" = None,
        order_service: "OrderServicePort | None" = None,
    ) -> None:
        """Stamp ports from Universe / composition root (KD-12)."""
        if data_provider is not None:
            self._provider = data_provider
        if execution_provider is not None:
            self._executor = execution_provider
        if order_service is not None:
            self._order_service_ref = weakref.ref(order_service)

    # ── Identity ──────────────────────────────────────────────────────

    @property
    def id(self) -> InstrumentId:
        return self._identity.instrument_id

    @property
    def symbol(self) -> str:
        return self._identity.symbol

    @property
    def exchange(self) -> str:
        return self._identity.exchange

    @property
    def asset_type(self) -> str:
        return self._identity.asset_type

    @property
    def lot_size(self) -> int:
        return self._trading.lot_size

    @property
    def tick_size(self) -> Decimal:
        return self._trading.tick_size

    # ── Live State ────────────────────────────────────────────────────

    @property
    def quote(self) -> QuoteSnapshot | None:
        return self._state.quote

    @property
    def ltp(self) -> Decimal | None:
        q = self._state.quote
        return q.ltp if q else None

    @property
    def bid(self) -> Decimal | None:
        q = self._state.quote
        return q.bid if q else None

    @property
    def ask(self) -> Decimal | None:
        q = self._state.quote
        return q.ask if q else None

    @property
    def volume(self) -> int:
        q = self._state.quote
        return q.volume if q else 0

    @property
    def market_depth(self) -> MarketDepth | None:
        return self._state.depth

    @property
    def order_book(self) -> MarketDepth | None:
        return self._state.depth

    @property
    def is_live(self) -> bool:
        return self._state.is_subscribed

    @property
    def last_tick(self) -> QuoteSnapshot | None:
        # ponytail: last_tick aliases quote; VO tracks last_update instead
        return self._state.quote

    # ── Provider resolution (KD-1) ────────────────────────────────────

    def _resolve_provider(self) -> "DataProvider":
        """Resolve DataProvider: explicit → ambient Session → default registry.

        Raises
        ------
        NotConfiguredError
            When no provider is available — call ``tradex.connect(...)``.
        """
        if self._provider is not None:
            return self._provider
        try:
            from domain.ports.session_context import get_ambient_session

            ambient = get_ambient_session()
            if ambient is not None:
                prov = getattr(ambient, "provider", None)
                if prov is not None:
                    return prov
        except Exception:
            pass
        from domain.ports.provider_registry import get_default_provider

        default = get_default_provider()
        if default is not None:
            return default
        from domain.errors import NotConfiguredError

        raise NotConfiguredError(
            "Instrument has no DataProvider; use tradex.connect() to wire a session "
            "or session.universe.equity(...)"
        )

    def _resolve_order_service(self) -> "OrderServicePort | None":
        """OMS only: stamped weakref → ambient Session.order_service. Never EP."""
        if self._order_service_ref is not None:
            osvc = self._order_service_ref()
            if osvc is not None:
                return osvc
        try:
            from domain.ports.session_context import get_ambient_session

            ambient = get_ambient_session()
            if ambient is not None:
                osvc = getattr(ambient, "order_service", None)
                if osvc is not None:
                    logger.warning(
                        "orders_via_ambient_session symbol=%s — prefer session.universe.* stamps",
                        self.symbol,
                    )
                    return osvc
        except Exception:
            pass
        return None

    # ── Behaviors ─────────────────────────────────────────────────────

    def refresh(self) -> QuoteSnapshot | None:
        """Pull latest quote into state."""
        provider = self._resolve_provider()
        quote = provider.get_quote(self._id)
        if quote is not None:
            with self._lock:
                self._state = self._state.with_quote(quote)
        return quote

    @property
    def history(self) -> InstrumentHistory:
        """History facade — call as ``inst.history(timeframe=..., days=...)``."""
        return self._history

    def depth(self) -> MarketDepth | None:
        """Fetch market depth into owned state and return it."""
        provider = self._resolve_provider()
        d = provider.get_depth(self._id)
        if d is not None:
            with self._lock:
                self._state = self._state.with_depth(d)
        return d

    def spread(self) -> Decimal | None:
        if self.bid is not None and self.ask is not None:
            return self.ask - self.bid
        return None

    def mid_price(self) -> Decimal | None:
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return None

    def statistics(self) -> dict:
        """Return current statistics snapshot."""
        q = self._state.quote
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "asset_type": self.asset_type,
            "ltp": q.ltp if q else None,
            "bid": q.bid if q else None,
            "ask": q.ask if q else None,
            "volume": q.volume if q else 0,
            "high": q.high if q else None,
            "low": q.low if q else None,
            "open": q.open_ if q else None,
            "close": q.close if q else None,
            "spread": self.spread(),
            "mid_price": self.mid_price(),
        }

    def snapshot(self) -> dict:
        """Return full state snapshot."""
        return {
            "id": str(self._id),
            "state": {
                "quote": self._state.quote.__dict__ if self._state.quote else None,
                "depth": self._state.depth.__dict__ if self._state.depth else None,
                "is_subscribed": self._state.is_subscribed,
                "error": self._state.error,
            },
        }

    def serialize(self) -> dict:
        """JSON-serializable representation."""
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "asset_type": self.asset_type,
            "lot_size": self.lot_size,
            "tick_size": str(self.tick_size),
        }

    def clone(self) -> Instrument:
        """Deep copy of this instrument (ports stamped; history cache not copied)."""
        inst = Instrument(
            self._id,
            data_provider=self._provider,
            execution_provider=self._executor,
            metadata=self._metadata.copy(),
        )
        if self._order_service_ref is not None:
            osvc = self._order_service_ref()
            if osvc is not None:
                inst._order_service_ref = weakref.ref(osvc)
        return inst

    # ── Live Data ─────────────────────────────────────────────────────

    def subscribe(
        self,
        callback: Callable[[InstrumentId, Any], None] | None = None,
        *,
        depth: bool = False,
    ) -> SubscriptionHandle | None:
        """Subscribe to live data."""
        provider = self._resolve_provider()

        def _wrapped(iid: InstrumentId, payload: Any) -> None:
            # Update state atomically
            with self._lock:
                if isinstance(payload, MarketDepth):
                    self._state = self._state.with_depth(payload)
                elif isinstance(payload, QuoteSnapshot):
                    self._state = self._state.with_quote(payload)
                sub = self._state.subscription
                if not sub.is_active:
                    self._state = self._state.with_subscription(
                        SubscriptionState(
                            status=SubscriptionStatus.SUBSCRIBED,
                            symbol=self.symbol,
                            exchange=self.exchange,
                            started_at=sub.started_at or datetime.now(timezone.utc),
                        )
                    )
            # Invoke registered callbacks (outside lock to avoid deadlock)
            # Snapshot the list under lock to avoid race conditions
            with self._lock:
                tick_callbacks = list(self._callbacks.get("tick", []))
            for cb in tick_callbacks:
                try:
                    cb(payload)
                except Exception:
                    logger.exception("tick callback %r failed for %s", cb, self._id)
            # Invoke user callback
            if callback is not None:
                callback(iid, payload)

        handle = provider.subscribe(self._id, _wrapped, depth=depth)
        self._subscription = handle
        with self._lock:
            self._state = self._state.with_subscription(
                SubscriptionState(
                    status=SubscriptionStatus.SUBSCRIBED,
                    symbol=self.symbol,
                    exchange=self.exchange,
                    started_at=datetime.now(timezone.utc),
                )
            )
        return handle

    def unsubscribe(self) -> None:
        """Tear down live subscription."""
        if self._subscription is not None:
            self._subscription.unsubscribe()
            self._subscription = None
        with self._lock:
            self._state = self._state.with_unsubscribed()

    def on_tick(self, callback: Callable) -> None:
        """Register tick callback."""
        with self._lock:
            self._callbacks["tick"] = self._callbacks["tick"] + [callback]

    def on_quote(self, callback: Callable) -> None:
        """Register quote callback."""
        with self._lock:
            self._callbacks["quote"] = self._callbacks["quote"] + [callback]

    def on_depth(self, callback: Callable) -> None:
        """Register depth callback."""
        with self._lock:
            self._callbacks["depth"] = self._callbacks["depth"] + [callback]

    def on_disconnect(self, callback: Callable) -> None:
        """Register disconnect callback."""
        with self._lock:
            self._callbacks["disconnect"] = self._callbacks["disconnect"] + [callback]

    def on_reconnect(self, callback: Callable) -> None:
        """Register reconnect callback."""
        with self._lock:
            self._callbacks["reconnect"] = self._callbacks["reconnect"] + [callback]

    # ── Chains ────────────────────────────────────────────────────────

    def option_chain(self, expiry: date | int | str | None = None):
        """Return option chain as a rich domain object.

        Parameters
        ----------
        expiry:
            Concrete ``date`` / ``YYYY-MM-DD`` string, or **integer offset**
            (TradeHull-style: ``0`` = nearest, ``1`` = next, …). Offset uses
            the chain's expiry calendar when the provider exposes multiple
            expiries; otherwise only ``0`` is reliable for a single snapshot.
        """
        provider = self._resolve_provider()
        from domain.options.option_chain import OptionChain

        offset: int | None = None
        resolved_expiry: date | None = None
        if isinstance(expiry, int):
            offset = expiry
            resolved_expiry = None
        elif isinstance(expiry, str):
            resolved_expiry = OptionChain._parse_expiry(expiry)
        else:
            resolved_expiry = expiry

        chain_vo = provider.get_option_chain(self._id, expiry=resolved_expiry)
        # Optional multi-expiry calendar from provider
        available = None
        list_fn = getattr(provider, "list_option_expiries", None)
        if callable(list_fn):
            try:
                available = list_fn(self._id)
            except Exception:
                available = None

        chain = OptionChain(
            chain_vo,
            provider=provider,
            order_service=self._resolve_order_service(),
            available_expiries=available,
        )
        if offset is not None:
            return chain.chain_at_offset(offset)
        return chain

    def future_chain(self):
        """Return futures chain as a rich aggregate of :class:`Future` instruments."""
        provider = self._resolve_provider()
        vo = provider.get_future_chain(self._id)
        from domain.futures.future_chain import FutureChain as FutureChainAgg

        # Normalize dict / VO
        from domain.entities.options import FutureChain as FutureChainVO

        if not isinstance(vo, FutureChainVO):
            if isinstance(vo, dict):
                vo = FutureChainVO.from_dict(vo)
            else:
                vo = FutureChainVO(
                    underlying=self.symbol,
                    exchange=self.exchange,
                )
        return FutureChainAgg(
            vo,
            provider=provider,
            order_service=self._resolve_order_service(),
        )

    # ── Extensions (composition — broker capabilities without gateways) ─

    @property
    def broker(self):
        """Instrument-bound broker capabilities (depth20/200/30, news, …).

        Returns a :class:`~domain.extensions.facade.BoundBrokerFacade` when the
        session stamped a catalog, else ``None``. Never exposes a gateway.
        """
        facade = None
        # Prefer facade registered under provider name or any BrokerFacade
        try:
            provider = self._resolve_provider()
            broker_id = getattr(provider, "name", None)
            if broker_id:
                facade = self._extensions.get(broker_id)
        except Exception:
            facade = None
        if facade is None:
            for ext in self._extensions.values():
                if type(ext).__name__ == "BrokerFacade" or hasattr(ext, "for_instrument"):
                    facade = ext
                    break
        if facade is None:
            return None
        bind = getattr(facade, "for_instrument", None)
        if callable(bind):
            return bind(self)
        return facade

    @property
    def extensions(self):
        """Named extension objects stamped on this instrument."""
        return list(self._extensions.values())

    def has_extension(self, name: str) -> bool:
        if name in self._extensions:
            return True
        b = self.broker
        return bool(b is not None and getattr(b, "has", lambda _n: False)(name))

    def get_extension(self, name: str):
        """Return extension by name (``depth_20``, broker id, …), instrument-bound when possible."""
        ext = self._extensions.get(name)
        if ext is not None:
            # Session catalog → bind to this instrument
            if type(ext).__name__ == "BrokerFacade":
                return ext.for_instrument(self)
            bind = getattr(ext, "for_instrument", None)
            if callable(bind):
                try:
                    return bind(self.symbol, self.exchange)
                except TypeError:
                    return bind(self)
            return ext
        b = self.broker
        catalog = getattr(b, "_catalog", None) if b is not None else None
        if catalog is not None:
            found = catalog.get_extension(name)
            if found is not None:
                bind = getattr(found, "for_instrument", None)
                if callable(bind):
                    return bind(self.symbol, self.exchange)
                return found
        return None

    def capabilities(self) -> list[str]:
        """Capability names available via ``instrument.broker`` for this session."""
        b = self.broker
        if b is None:
            return []
        caps = getattr(b, "capabilities", None)
        if callable(caps):
            return list(caps())
        if caps is not None:
            return list(caps)
        list_fn = getattr(b, "list_capabilities", None)
        if callable(list_fn):
            return list(list_fn())
        return []

    # ── Orders (OMS-only — KD-9) ──────────────────────────────────────

    def buy(
        self,
        quantity: int,
        price: Decimal | None = None,
        order_type: OrderType | str = OrderType.LIMIT,
        product_type: ProductType | str = ProductType.INTRADAY,
        *,
        correlation_id: str | None = None,
    ) -> "OrderResult":
        """Place a buy via OrderServicePort only (never ExecutionProvider)."""
        return self._place(Side.BUY, quantity, price, order_type, product_type, correlation_id)

    def sell(
        self,
        quantity: int,
        price: Decimal | None = None,
        order_type: OrderType | str = OrderType.LIMIT,
        product_type: ProductType | str = ProductType.INTRADAY,
        *,
        correlation_id: str | None = None,
    ) -> "OrderResult":
        """Place a sell via OrderServicePort only (never ExecutionProvider)."""
        return self._place(Side.SELL, quantity, price, order_type, product_type, correlation_id)

    def market(
        self,
        quantity: int,
        side: Side | str = Side.BUY,
        *,
        product_type: ProductType | str = ProductType.INTRADAY,
        correlation_id: str | None = None,
    ) -> "OrderResult":
        """Place a market order via OMS only."""
        s = side if isinstance(side, Side) else Side(str(side).upper())
        return self._place(
            s, quantity, None, OrderType.MARKET, product_type, correlation_id
        )

    def limit(
        self,
        quantity: int,
        price: Decimal,
        side: Side | str = Side.BUY,
        *,
        product_type: ProductType | str = ProductType.INTRADAY,
        correlation_id: str | None = None,
    ) -> "OrderResult":
        """Place a limit order via OMS only."""
        s = side if isinstance(side, Side) else Side(str(side).upper())
        return self._place(
            s, quantity, price, OrderType.LIMIT, product_type, correlation_id
        )

    def stop_loss(
        self,
        quantity: int,
        trigger_price: Decimal,
        side: Side | str = Side.BUY,
        *,
        product_type: ProductType | str = ProductType.INTRADAY,
        correlation_id: str | None = None,
    ) -> "OrderResult":
        """Place a stop-loss market order via OMS only."""
        s = side if isinstance(side, Side) else Side(str(side).upper())
        return self._place(
            s,
            quantity,
            None,
            OrderType.STOP_LOSS_MARKET,
            product_type,
            correlation_id,
            trigger_price=trigger_price,
        )

    def cancel(self, order_id: str) -> "OrderResult":
        """Cancel an open order via OrderServicePort (OMS), never ExecutionProvider."""
        from domain.errors import NotConfiguredError

        osvc = self._require_order_service()
        cancel = getattr(osvc, "cancel", None)
        if not callable(cancel):
            raise NotConfiguredError(
                "OrderServicePort does not implement cancel(); upgrade OMS wiring."
            )
        return cancel(order_id)

    def modify(
        self,
        order_id: str,
        *,
        quantity: int | None = None,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
        order_type: OrderType | str | None = None,
    ) -> "OrderResult":
        """Modify an open order via OrderServicePort (OMS)."""
        from domain.errors import NotConfiguredError
        from domain.orders.requests import ModifyOrderRequest

        osvc = self._require_order_service()
        modify = getattr(osvc, "modify", None)
        if not callable(modify):
            raise NotConfiguredError(
                "OrderServicePort does not implement modify(); upgrade OMS wiring."
            )
        ot = None
        if order_type is not None:
            ot = (
                order_type
                if isinstance(order_type, OrderType)
                else OrderType(str(order_type).upper())
            )
        return modify(
            ModifyOrderRequest(
                order_id=order_id,
                quantity=quantity,
                price=price,
                trigger_price=trigger_price,
                order_type=ot,
            )
        )

    def _require_order_service(self) -> "OrderServicePort":
        """Resolve OMS or raise ORDERS_DISABLED / NotConfiguredError."""
        from domain.errors import NotConfiguredError

        osvc = self._resolve_order_service()
        if osvc is not None:
            # Market-mode ambient: still refuse even if something stamped OMS
            try:
                from domain.ports.session_context import get_ambient_session

                ambient = get_ambient_session()
                st = getattr(ambient, "status", None) if ambient is not None else None
                if st is not None and not getattr(st, "orders_enabled", True):
                    raise NotConfiguredError(
                        "ORDERS_DISABLED: Session is market-data only "
                        f"(mode={getattr(st, 'mode', 'market')!r}). "
                        "Reconnect with mode='trade' when ready to trade."
                    )
            except NotConfiguredError:
                raise
            except Exception:
                pass
            return osvc
        try:
            from domain.ports.session_context import get_ambient_session

            ambient = get_ambient_session()
            st = getattr(ambient, "status", None) if ambient is not None else None
            if st is not None and not getattr(st, "orders_enabled", True):
                raise NotConfiguredError(
                    "ORDERS_DISABLED: Session is market-data only "
                    f"(mode={getattr(st, 'mode', 'market')!r}). "
                    "Reconnect with mode='trade' when ready to trade."
                )
        except NotConfiguredError:
            raise
        except Exception:
            pass
        raise NotConfiguredError(
            "Instrument has no OrderServicePort (OMS). "
            "Use tradex.connect(..., mode='sim'|'trade')."
        )

    def _place(
        self,
        side: Side,
        quantity: int,
        price: Decimal | None,
        order_type: OrderType | str,
        product_type: ProductType | str,
        correlation_id: str | None,
        *,
        trigger_price: Decimal | None = None,
    ) -> "OrderResult":
        from domain.errors import NotConfiguredError

        ot = order_type if isinstance(order_type, OrderType) else OrderType(str(order_type).upper())
        pt = (
            product_type
            if isinstance(product_type, ProductType)
            else ProductType(str(product_type).upper())
        )
        osvc = self._require_order_service()
        intent = build_order_intent(
            self,
            side,
            quantity,
            price=price,
            order_type=ot,
            product_type=pt,
            trigger_price=trigger_price,
            correlation_id=correlation_id,
        )
        return place_via_order_service(osvc, intent)

    # ── Representation ────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._id})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Instrument):
            return NotImplemented
        return self._id == other._id

    def __hash__(self) -> int:
        return hash(self._id)


# ══════════════════════════════════════════════════════════════════════
# Specialized Instruments
# ══════════════════════════════════════════════════════════════════════


class Equity(Instrument):
    """Equity instrument. ``Equity("RELIANCE")``."""

    def __init__(
        self,
        symbol: str,
        exchange: str = "NSE",
        **kwargs: Any,
    ) -> None:
        super().__init__(InstrumentId.equity(exchange, symbol), **kwargs)


class ETF(Equity):
    """Exchange-traded fund — cash-like with AssetKind.ETF."""

    def __init__(
        self,
        symbol: str,
        exchange: str = "NSE",
        **kwargs: Any,
    ) -> None:
        Instrument.__init__(self, InstrumentId.etf(exchange, symbol), **kwargs)


class Spot(Instrument):
    """Spot instrument (FX / commodity spot when provider supports it)."""

    def __init__(
        self,
        symbol: str,
        exchange: str = "NSE",
        **kwargs: Any,
    ) -> None:
        super().__init__(InstrumentId.spot(exchange, symbol), **kwargs)


class Currency(Instrument):
    """Currency pair / currency underlying (cash form)."""

    def __init__(
        self,
        symbol: str,
        exchange: str = "NSE",
        **kwargs: Any,
    ) -> None:
        super().__init__(InstrumentId.currency(exchange, symbol), **kwargs)


class Index(Instrument):
    """Index instrument. ``Index("NIFTY")``."""

    def __init__(
        self,
        name: str,
        exchange: str = "NSE",
        **kwargs: Any,
    ) -> None:
        super().__init__(InstrumentId.index(exchange, name), **kwargs)


class Future(Instrument):
    """Futures instrument. ``Future("NIFTY", expiry=date(...))``."""

    def __init__(
        self,
        symbol: str,
        exchange: str = "NFO",
        *,
        expiry: date,
        kind: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            InstrumentId.future(exchange, symbol, expiry, kind=kind),
            **kwargs,
        )
        self._expiry = expiry


class Commodity(Future):
    """Commodity future (typically MCX)."""

    def __init__(
        self,
        symbol: str,
        exchange: str = "MCX",
        *,
        expiry: date,
        **kwargs: Any,
    ) -> None:
        Future.__init__(
            self, symbol, exchange, expiry=expiry, kind="COMMODITY", **kwargs
        )

    @property
    def expiry(self) -> date:
        return self._expiry

    def _spot_ltp(self, spot: Decimal | None = None) -> Decimal | None:
        if spot is not None:
            return spot
        from domain.instruments.derivatives_math import map_underlying_cash_exchange

        try:
            provider = self._resolve_provider()
        except Exception:
            return None
        cash_ex = map_underlying_cash_exchange(self.exchange)
        und_id = InstrumentId.equity(cash_ex, self.symbol)
        # Indices use index factory shape — try equity then index
        q = provider.get_quote(und_id)
        if q is None:
            und_id = InstrumentId.index(cash_ex, self.symbol)
            q = provider.get_quote(und_id)
        return q.ltp if q is not None else None

    def _futures_ltp(self) -> Decimal | None:
        if self.ltp is not None:
            return self.ltp
        try:
            q = self.refresh()
            return q.ltp if q is not None else None
        except Exception:
            return None

    def basis(self, spot: Decimal | None = None) -> Decimal | None:
        """F - S (normative). None if either leg missing."""
        from domain.instruments.derivatives_math import future_basis

        return future_basis(self._futures_ltp(), self._spot_ltp(spot))

    def cost_of_carry(self, rate: Decimal | None = None) -> Decimal | None:
        """Implied continuous rate if rate is None; else F - S*e^{rT}."""
        from domain.instruments.derivatives_math import cost_of_carry_basis, year_fraction

        return cost_of_carry_basis(
            self._futures_ltp(),
            self._spot_ltp(),
            year_fraction(self._expiry),
            rate,
        )

    def rollover(self) -> Future | None:
        """Next expiry Future on same underlying; stamps same ports."""
        try:
            provider = self._resolve_provider()
        except Exception:
            return None
        try:
            chain = provider.get_future_chain(self._id)
        except Exception:
            return None
        contracts = getattr(chain, "contracts", None) or getattr(chain, "futures", None) or []
        next_exp: date | None = None
        for c in contracts:
            exp = getattr(c, "expiry", None)
            if isinstance(exp, str):
                for fmt in ("%Y-%m-%d", "%Y%m%d"):
                    try:
                        from datetime import datetime as _dt

                        exp = _dt.strptime(exp, fmt).date()
                        break
                    except ValueError:
                        continue
            if isinstance(exp, date) and exp > self._expiry:
                if next_exp is None or exp < next_exp:
                    next_exp = exp
        if next_exp is None:
            return None
        fut = Future(
            self.symbol,
            self.exchange,
            expiry=next_exp,
            data_provider=self._provider,
            execution_provider=self._executor,
        )
        osvc = self._resolve_order_service()
        if osvc is not None or self._provider is not None:
            fut._bind_session_ports(
                data_provider=self._provider,
                execution_provider=self._executor,
                order_service=osvc,
            )
        return fut

    def continuous(self) -> HistoricalSeries:
        """v1: empty DERIVED continuous series (no provider continuous support)."""
        from domain.provenance import DataProvenance, ProvenanceConfidence, SourceIdentity

        return HistoricalSeries(
            bars=[],
            coverage=None,
            instrument=InstrumentRef(symbol=self.symbol, exchange=self.exchange),
            timeframe="1D",
            merge_manifest=None,
        )


class Option(Instrument):
    """Option instrument. Usually built from a chain leg.

    ``Option.from_leg(...)`` constructs one carrying its greeks/IV.
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        *,
        strike: Decimal,
        expiry: date | None,
        right: str,
        leg: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(instrument_id, **kwargs)
        self._strike = Decimal(str(strike))
        self._expiry = expiry
        self._right = right
        self._leg = leg

    @property
    def strike(self) -> Decimal:
        return self._strike

    @property
    def expiry(self) -> date | None:
        return self._expiry

    @property
    def right(self) -> str:
        return self._right

    @property
    def is_call(self) -> bool:
        return self._right == "CE"

    @property
    def is_put(self) -> bool:
        return self._right == "PE"

    @property
    def greeks(self):
        from domain.options.greeks import Greeks

        leg_greeks = getattr(self._leg, "greeks", None)
        return Greeks.from_dict(leg_greeks) if leg_greeks else Greeks.zero()

    @property
    def iv(self):
        return getattr(self._leg, "iv", None)

    @property
    def delta(self) -> Decimal:
        """First-order greek, read from the option's greeks surface.

        Thin accessor over ``Option.greeks`` — no analytics/IO imported.
        """
        return self.greeks.delta

    def black_scholes(
        self,
        spot: Decimal,
        rate: Decimal | None = None,
        vol: Decimal | None = None,
        *,
        t: Decimal | None = None,
        dividend_yield: Decimal | None = None,
    ) -> Decimal | None:
        """European BS price (pure domain)."""
        from domain.instruments.derivatives_math import black_scholes_price, year_fraction

        sigma = vol if vol is not None else self.iv
        if sigma is None:
            return None
        if not isinstance(sigma, Decimal):
            sigma = Decimal(str(sigma))
        tau = t if t is not None else year_fraction(self._expiry)
        if tau is None:
            return None
        r = rate if rate is not None else Decimal("0")
        q = dividend_yield if dividend_yield is not None else Decimal("0")
        return black_scholes_price(
            Decimal(str(spot)),
            self._strike,
            tau,
            r,
            sigma,
            is_call=self.is_call,
            dividend_yield=q,
        )

    def payoff(self, spot: Decimal) -> Decimal:
        from domain.instruments.derivatives_math import option_payoff

        return option_payoff(Decimal(str(spot)), self._strike, is_call=self.is_call)

    def intrinsic_value(self, spot: Decimal) -> Decimal:
        return self.payoff(spot)

    def extrinsic_value(self, spot: Decimal) -> Decimal | None:
        mkt = self.ltp
        if mkt is None and self._leg is not None:
            mkt = getattr(self._leg, "ltp", None)
        if mkt is None:
            return None
        return Decimal(str(mkt)) - self.intrinsic_value(spot)

    def moneyness(self, spot: Decimal) -> str:
        from domain.instruments.derivatives_math import moneyness_label

        return moneyness_label(
            Decimal(str(spot)),
            self._strike,
            is_call=self.is_call,
            tick_size=self.tick_size or Decimal("0.05"),
        )

    def implied_volatility(
        self,
        market_price: Decimal,
        spot: Decimal | None = None,
        rate: Decimal | None = None,
        *,
        t: Decimal | None = None,
    ) -> Decimal | None:
        from domain.instruments.derivatives_math import implied_volatility, year_fraction

        s = spot
        if s is None:
            s = self.ltp
        if s is None:
            return None
        tau = t if t is not None else year_fraction(self._expiry)
        if tau is None or tau <= 0:
            return None
        r = rate if rate is not None else Decimal("0")
        return implied_volatility(
            Decimal(str(market_price)),
            Decimal(str(s)),
            self._strike,
            tau,
            r,
            is_call=self.is_call,
        )

    @classmethod
    def from_leg(
        cls,
        underlying: str,
        exchange: str,
        expiry: date | str | None,
        strike: Decimal,
        right: str,
        leg: Any,
        **kwargs: Any,
    ) -> Option:
        """Construct Option from a chain leg (optional order_service stamp)."""
        order_service = kwargs.pop("order_service", None)
        if isinstance(expiry, str):
            from datetime import datetime

            for fmt in ("%Y-%m-%d", "%Y%m%d"):
                try:
                    expiry = datetime.strptime(expiry, fmt).date()
                    break
                except ValueError:
                    continue
        iid = InstrumentId.option(exchange, underlying, expiry, strike, right)
        opt = cls(iid, strike=strike, expiry=expiry, right=right, leg=leg, **kwargs)
        if order_service is not None:
            opt._bind_session_ports(
                data_provider=kwargs.get("data_provider"),
                execution_provider=kwargs.get("execution_provider"),
                order_service=order_service,
            )
        return opt
