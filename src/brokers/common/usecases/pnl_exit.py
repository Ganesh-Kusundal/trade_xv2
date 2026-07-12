"""PnL-based exit use case — broker-agnostic orchestration."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol


class PnlExitStrategy(Protocol):
    def exit_on_pnl(self, transport: Any, *, threshold: Decimal, **kwargs: Any) -> list[str]:
        ...


def exit_on_pnl(
    transport: Any,
    *,
    threshold: Decimal,
    strategy: PnlExitStrategy | None = None,
    **kwargs: Any,
) -> list[str]:
    """Close positions when unrealized PnL crosses *threshold*."""
    ext = getattr(transport, "extended", None)
    if ext is not None and hasattr(ext, "exit_on_pnl"):
        return ext.exit_on_pnl(threshold=threshold, **kwargs)
    if strategy is not None:
        return strategy.exit_on_pnl(transport, threshold=threshold, **kwargs)
    raise NotImplementedError("transport has no pnl exit capability")
