"""Broker capability facade — exposes broker-specific methods on an Instrument.

``Instrument.broker`` returns a bound facade. It aggregates every extension
registered for the session broker and forwards capability access so::

    instrument.broker.depth20()    # Dhan 20-level depth
    instrument.broker.depth200()   # Dhan 200-level depth
    instrument.broker.depth30()    # Upstox 30-level depth
    instrument.broker.capabilities  # list of capability names

The domain layer (and user code) never imports broker-specific types; it only
calls capability-named methods through this facade. Transport stays inside
extensions constructed at ``tradex.connect`` time.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any

# Public aliases → extension.name / method used by product code
_CAPABILITY_ALIASES: dict[str, tuple[str, ...]] = {
    "depth20": ("depth_20", "depth20", "full_depth"),
    "depth_20": ("depth_20", "depth20"),
    "depth200": ("depth_200", "depth200", "full_depth"),
    "depth_200": ("depth_200", "depth200"),
    "depth30": ("depth_30", "depth30", "full_depth"),
    "depth_30": ("depth_30", "depth30"),
    "news": ("news",),
    "super_order": ("super_order",),
    "superorder": ("super_order",),
    "forever_order": ("forever_order",),
    "forever": ("forever_order",),
    "slice_order": ("slice_order", "native_slice_order"),
}


def _capability_label(cap: Any) -> str | None:
    """Normalize a capability token to a shell-filterable name (prefer enum value)."""
    if isinstance(cap, str):
        return cap
    if isinstance(cap, Enum):
        return str(cap.value)
    value = getattr(cap, "value", None)
    if value is not None:
        return str(value)
    name = getattr(cap, "name", None)
    return str(name) if name else None


class BrokerFacade:
    """Session-level catalog of broker extensions (unbound to a single instrument)."""

    def __init__(self, broker_id: str, extensions: list[Any]) -> None:
        object.__setattr__(self, "_broker_id", broker_id)
        object.__setattr__(self, "_exts", list(extensions))

    @property
    def broker_id(self) -> str:
        return self._broker_id

    @property
    def extensions(self) -> list[Any]:
        return list(self._exts)

    def capability_names(self) -> list[str]:
        names: list[str] = []
        for ext in self._exts:
            try:
                n = getattr(ext, "name", None)
                if n:
                    names.append(str(n))
                caps = getattr(ext, "capabilities", ())
                if callable(caps):
                    caps = caps()
                for cap in caps or ():
                    cname = _capability_label(cap)
                    if cname and cname not in names:
                        names.append(cname)
            except Exception:
                continue
        return names

    def get_extension(self, name: str) -> Any | None:
        key = name.lower().replace("-", "_")
        for ext in self._exts:
            en = str(getattr(ext, "name", "") or "").lower()
            if en == key or en.replace("_", "") == key.replace("_", ""):
                return ext
        return None

    def for_instrument(self, instrument: Any) -> BoundBrokerFacade:
        """Bind this catalog to a concrete instrument (symbol/exchange)."""
        return BoundBrokerFacade(self, instrument)

    def _resolve(self, name: str) -> Any:
        for ext in self._exts:
            if hasattr(ext, name):
                return getattr(ext, name)
        raise AttributeError(
            f"broker {self._broker_id!r} has no capability named {name!r}. "
            f"Available: {self.capability_names()}"
        )

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return object.__getattribute__(self, "_resolve")(name)

    def __repr__(self) -> str:
        names = [getattr(e, "name", type(e).__name__) for e in self._exts]
        return f"BrokerFacade(broker={self._broker_id!r}, extensions={names})"


class BoundBrokerFacade:
    """Instrument-bound view — depth/news/etc. use this instrument's identity."""

    def __init__(self, catalog: BrokerFacade, instrument: Any) -> None:
        self._catalog = catalog
        self._instrument = instrument

    @property
    def broker_id(self) -> str:
        return self._catalog.broker_id

    @property
    def catalog(self) -> BrokerFacade:
        """Public accessor for the underlying BrokerFacade catalog."""
        return self._catalog

    @property
    def capabilities(self) -> list[str]:
        return self._catalog.capability_names()

    def list_capabilities(self) -> list[str]:
        return self.capabilities

    def has(self, name: str) -> bool:
        return self._find_extension(name) is not None

    def _symbol_exchange(self) -> tuple[str, str]:
        inst = self._instrument
        return (
            str(getattr(inst, "symbol", "") or ""),
            str(getattr(inst, "exchange", "NSE") or "NSE"),
        )

    def _find_extension(self, name: str) -> Any | None:
        aliases = _CAPABILITY_ALIASES.get(name, (name,))
        for alias in aliases:
            ext = self._catalog.get_extension(alias)
            if ext is not None:
                return ext
        # fallback: any extension exposing the attribute
        for ext in self._catalog.extensions:
            if hasattr(ext, name):
                return ext
        return None

    def _bound_extension(self, name: str) -> Any:
        ext = self._find_extension(name)
        if ext is None:
            raise AttributeError(
                f"broker {self.broker_id!r} has no capability {name!r}. "
                f"Available: {self.capabilities}"
            )
        symbol, exchange = self._symbol_exchange()
        bind = getattr(ext, "for_instrument", None)
        if callable(bind):
            return bind(symbol, exchange)
        # Attach symbol/exchange in place when no factory
        try:
            ext._symbol = symbol  # type: ignore[attr-defined]
            ext._exchange = exchange  # type: ignore[attr-defined]
        except Exception:
            pass
        return ext

    def depth20(self, on_depth: Callable | None = None) -> Any:
        """Dhan-style 20-level depth for this instrument."""
        return self._bound_extension("depth_20").full_depth(on_depth=on_depth)

    def depth200(self, on_depth: Callable | None = None) -> Any:
        """Dhan-style 200-level depth for this instrument."""
        return self._bound_extension("depth_200").full_depth(on_depth=on_depth)

    def depth30(self, on_depth: Callable | None = None) -> Any:
        """Upstox-style 30-level depth for this instrument."""
        return self._bound_extension("depth_30").full_depth(on_depth=on_depth)

    # snake_case aliases
    def depth_20(self, on_depth: Callable | None = None) -> Any:
        return self.depth20(on_depth=on_depth)

    def depth_200(self, on_depth: Callable | None = None) -> Any:
        return self.depth200(on_depth=on_depth)

    def depth_30(self, on_depth: Callable | None = None) -> Any:
        return self.depth30(on_depth=on_depth)

    def news(self, *, limit: int = 20, **kwargs: Any) -> Any:
        """Upstox (and others) news for this instrument."""
        ext = self._bound_extension("news")
        fetch = getattr(ext, "fetch", None) or getattr(ext, "full_depth", None)
        if not callable(fetch):
            raise AttributeError(f"broker {self.broker_id!r} news has no fetch()")
        try:
            return fetch(limit=limit, **kwargs)
        except TypeError:
            return fetch()

    def super_order(self, **kwargs: Any) -> Any:
        """Dhan super/bracket order for this instrument."""
        ext = self._bound_extension("super_order")
        place = getattr(ext, "place", None)
        if not callable(place):
            raise AttributeError(f"broker {self.broker_id!r} super_order has no place()")
        return place(**kwargs)

    def forever_order(self, **kwargs: Any) -> Any:
        """Dhan forever order for this instrument."""
        ext = self._bound_extension("forever_order")
        place = getattr(ext, "place", None)
        if not callable(place):
            raise AttributeError(f"broker {self.broker_id!r} forever_order has no place()")
        return place(**kwargs)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        # Generic: bind extension and return attribute/method
        try:
            bound = self._bound_extension(name)
        except AttributeError:
            # method might live on extension under different name
            raise
        attr = getattr(bound, name, None)
        if attr is not None:
            return attr
        # capability entry point often named full_depth / fetch / etc.
        for fallback in ("full_depth", "get", "fetch", name):
            if hasattr(bound, fallback):
                return getattr(bound, fallback)
        raise AttributeError(
            f"broker {self.broker_id!r} capability {name!r} has no callable surface"
        )

    def __repr__(self) -> str:
        sym, ex = self._symbol_exchange()
        return (
            f"BoundBrokerFacade(broker={self.broker_id!r}, "
            f"instrument={ex}:{sym}, capabilities={self.capabilities})"
        )
