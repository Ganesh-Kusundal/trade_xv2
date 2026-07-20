"""Single composition-root resolver for execution capabilities.

Constitution: only this module may branch on ExecutionTargetKind / mode strings
when wiring the kernel (P12, ``02a-runtime-execution-model.md`` §5).
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from domain.ports.execution_target import ExecutionTarget, ExecutionTargetKind

if TYPE_CHECKING:
    from application.oms.context import TradingContext


def resolve_execution_target(
    kind: ExecutionTargetKind | str,
    *,
    gateway: Any | None = None,
    order_id_prefix: str | None = None,
    quote_fn: Callable[[str, str], Decimal] | None = None,
) -> ExecutionTarget:
    """Wire the active ExecutionTarget for the session.

    Args:
        kind: Capability enum or config string (replay/backtest/paper/live).
        gateway: Required for LIVE — broker order gateway.
        order_id_prefix: Override sim order id prefix (paper/bt).
        quote_fn: Optional LTP resolver for PAPER fills.

    Returns:
        ExecutionTarget satisfying domain port (FillSource adapters implement it).
    """
    if isinstance(kind, str):
        kind = ExecutionTargetKind.from_str(kind)

    if kind is ExecutionTargetKind.LIVE:
        if gateway is None:
            raise ValueError("Live execution target requires a broker gateway")
        from application.execution.fill_source import BrokerFillSource

        return BrokerFillSource(gateway, kind=ExecutionTargetKind.LIVE)

    if kind is ExecutionTargetKind.PAPER:
        from application.execution.fill_source import PaperFillSource

        prefix = order_id_prefix or _default_prefix(kind)
        return PaperFillSource(
            quote_fn=quote_fn,
            order_id_prefix=prefix,
            kind=kind,
        )

    from application.execution.fill_source import SimulatedFillSource

    prefix = order_id_prefix or _default_prefix(kind)
    return SimulatedFillSource(order_id_prefix=prefix, kind=kind)


def resolve_simulated_oms_adapter(
    kind: ExecutionTargetKind | str,
    trading_context: TradingContext,
) -> Any:
    """Legacy backtest/replay adapter — delegates target resolution to this module."""
    from application.execution.oms_backtest_adapter import SimulatedOMSAdapter

    if isinstance(kind, str):
        kind = ExecutionTargetKind.from_str(kind)

    if kind is ExecutionTargetKind.LIVE:
        raise ValueError(
            "Live mode must use ExecutionEngine with BrokerFillSource, "
            "not SimulatedOMSAdapter"
        )

    prefix = _default_prefix(kind)
    return SimulatedOMSAdapter(trading_context, order_id_prefix=prefix, kind=kind)


def build_execution_engine(
    trading_context: TradingContext,
    kind: ExecutionTargetKind | str,
    *,
    gateway: Any | None = None,
    order_id_prefix: str | None = None,
) -> Any:
    """Build ExecutionEngine with constitution-resolved target."""
    from application.execution.execution_engine import ExecutionEngine

    target = resolve_execution_target(
        kind,
        gateway=gateway,
        order_id_prefix=order_id_prefix,
    )
    return ExecutionEngine(target, trading_context)


def _default_prefix(kind: ExecutionTargetKind) -> str:
    if kind is ExecutionTargetKind.PAPER:
        return "paper"
    return "bt"


__all__ = [
    "build_execution_engine",
    "resolve_execution_target",
    "resolve_simulated_oms_adapter",
]
