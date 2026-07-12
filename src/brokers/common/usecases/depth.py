"""Market depth subscription use case — broker-agnostic orchestration.

Depth is a *broker-specific extension*, discovered by its canonical level
name (``depth_200`` / ``depth_30`` / ``depth_20`` / ``depth``) — never via
raw transport method names like ``depth_20`` / ``stream_depth``. Common code
resolves the extension through the bundle so Dhan's 20/200-level WebSocket
feeds and Upstox's 30-level ``full_d30`` feed are reached the same way, and a
broker that lacks a level fails cleanly instead of AttributeError.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol

from domain import MarketDepth


class DepthStrategy(Protocol):
    def subscribe_depth(
        self,
        transport: Any,
        symbol: str,
        exchange: str,
        *,
        levels: int = 20,
        on_depth: Callable[[MarketDepth], None] | None = None,
    ) -> MarketDepth:
        ...


# Canonical extension name per requested depth level, most-specific first.
_DEPTH_EXTENSION_BY_LEVELS: list[tuple[int, str]] = [
    (200, "depth_200"),
    (30, "depth_30"),
    (20, "depth_20"),
]


def _resolve_depth_extension(transport: Any, levels: int) -> Any | None:
    """Return the depth extension object for *levels*, or None.

    Looks up ``transport.get_extension(name)`` for the most specific level the
    broker supports at or above *levels*. Returns None when no depth extension
    is registered (caller falls back to the 5-level ``depth`` snapshot).
    """
    for threshold, ext_name in _DEPTH_EXTENSION_BY_LEVELS:
        if levels >= threshold:
            getter = getattr(transport, "get_extension", None)
            if callable(getter):
                ext = getter(ext_name)
                if ext is not None:
                    return ext
    return None


def subscribe_depth(
    transport: Any,
    symbol: str,
    exchange: str = "NSE",
    *,
    levels: int = 20,
    on_depth: Callable[[MarketDepth], None] | None = None,
    strategy: DepthStrategy | None = None,
) -> MarketDepth:
    """Subscribe to market depth via the broker's depth extension.

    ``transport`` is expected to be an object exposing ``get_extension(name)``
    (e.g. an Instrument); the canonical depth extension name is resolved by
    *levels* and ``get_extension`` already binds it to the instrument, so the
    only remaining call is ``full_depth(on_depth=...)``.
    """
    ext = _resolve_depth_extension(transport, levels)
    if ext is not None:
        full = getattr(ext, "full_depth", None)
        if callable(full):
            return full(on_depth=on_depth)
    if strategy is not None:
        return strategy.subscribe_depth(
            transport, symbol, exchange, levels=levels, on_depth=on_depth
        )
    return transport.depth(symbol, exchange)
