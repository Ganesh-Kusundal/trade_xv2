"""Market depth subscription use case — broker-agnostic orchestration."""

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


def subscribe_depth(
    transport: Any,
    symbol: str,
    exchange: str = "NSE",
    *,
    levels: int = 20,
    on_depth: Callable[[MarketDepth], None] | None = None,
    strategy: DepthStrategy | None = None,
) -> MarketDepth:
    """Subscribe to market depth via transport or injected strategy."""
    if levels >= 200 and hasattr(transport, "depth_200"):
        return transport.depth_200(symbol, exchange, on_depth=on_depth)
    if levels >= 20 and hasattr(transport, "depth_20"):
        return transport.depth_20(symbol, exchange, on_depth=on_depth)
    if hasattr(transport, "stream_depth"):
        depth_type = "DEPTH_30" if levels >= 30 else "DEPTH_5"
        return transport.stream_depth(symbol, exchange, depth_type=depth_type, on_depth=on_depth)
    if strategy is not None:
        return strategy.subscribe_depth(
            transport, symbol, exchange, levels=levels, on_depth=on_depth
        )
    return transport.depth(symbol, exchange)
