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
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

from domain.candles.instrument_history import InstrumentHistory
from domain.instruments.composition import (
    ExtensionManager,
    InstrumentIdentity,
    TradingSpec,
)
from domain.instruments.instrument_id import InstrumentId
from domain.value_objects.state import InstrumentState

if TYPE_CHECKING:
    from domain.ports.order_service import OrderServicePort
    from domain.ports.protocols import DataProvider, ExecutionProvider


__all__ = [
    "Instrument",
    "Equity",
    "ETF",
    "Spot",
    "Currency",
    "Index",
    "Future",
    "Commodity",
    "Option",
]

# Lazy re-exports to avoid circular import with _specialized/_derivatives.
_LAZY_IMPORTS = {
    "Equity": "domain.instruments._specialized",
    "ETF": "domain.instruments._specialized",
    "Spot": "domain.instruments._specialized",
    "Currency": "domain.instruments._specialized",
    "Index": "domain.instruments._specialized",
    "Future": "domain.instruments._derivatives",
    "Commodity": "domain.instruments._derivatives",
    "Option": "domain.instruments._derivatives",
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        import importlib

        mod = importlib.import_module(_LAZY_IMPORTS[name])
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
        self._subscription: Any = None
        self._callbacks: dict[str, list[Any]] = {
            "tick": [],
            "quote": [],
            "depth": [],
            "disconnect": [],
            "reconnect": [],
        }
        self._extensions = ExtensionManager()
        self._lock = threading.RLock()
        self._order_service_ref: weakref.ref | None = None
        self._history = InstrumentHistory(self)

    def _bind_session_ports(
        self,
        *,
        data_provider: DataProvider | None = None,
        execution_provider: ExecutionProvider | None = None,
        order_service: OrderServicePort | None = None,
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

    # ── Provider resolution (KD-1) ────────────────────────────────────

    def _resolve_provider(self) -> DataProvider:
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

    def _resolve_order_service(self) -> OrderServicePort | None:
        if self._order_service_ref is not None:
            osvc = self._order_service_ref()
            if osvc is not None:
                return osvc
        return None

    # ── Behaviors ─────────────────────────────────────────────────────

    @property
    def history(self) -> InstrumentHistory:
        """History facade — call as ``inst.history(timeframe=..., days=...)``."""
        return self._history

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

    # ── Chains ────────────────────────────────────────────────────────

    def option_chain(self, expiry: date | int | str | None = None):
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
        provider = self._resolve_provider()
        vo = provider.get_future_chain(self._id)
        from domain.futures.future_chain import FutureChain as FutureChainAgg
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

    # ── Extensions ────────────────────────────────────────────────────

    @property
    def broker(self):
        facade = None
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
        return list(self._extensions.values())

    def has_extension(self, name: str) -> bool:
        if name in self._extensions:
            return True
        b = self.broker
        return bool(b is not None and getattr(b, "has", lambda _n: False)(name))

    def get_extension(self, name: str):
        ext = self._extensions.get(name)
        if ext is not None:
            if type(ext).__name__ == "BrokerFacade":
                return ext.for_instrument(self)
            bind = getattr(ext, "for_instrument", None)
            if callable(bind):
                if getattr(ext, "_symbol", None) == self.symbol and getattr(ext, "_exchange", None) == self.exchange:
                    return ext
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

    # ── Representation ────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._id})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Instrument):
            return NotImplemented
        return self._id == other._id

    def __hash__(self) -> int:
        return hash(self._id)
