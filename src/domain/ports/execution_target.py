"""ExecutionTarget — capability seam for order fulfillment.

Constitution: ``docs/constitution/04-component-contracts.md``
All execution modes (Replay, Backtest, Paper, Live) implement this port.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from domain.entities.order import Order


class ExecutionTargetKind(str, Enum):
    """Kernel execution capability — sole enum for mode selection at runtime."""

    REPLAY = "replay"
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"

    @classmethod
    def from_str(cls, raw: str) -> ExecutionTargetKind:
        """Parse user/config string; raises ValueError if unknown."""
        normalized = raw.strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        raise ValueError(
            f"Unknown execution target: {raw!r}. "
            f"Expected one of: {', '.join(m.value for m in cls)}"
        )


@runtime_checkable
class ExecutionTarget(Protocol):
    """Fulfill orders — the only mode-specific piece of the execution pipeline."""

    @property
    def kind(self) -> ExecutionTargetKind:
        """Active capability (Replay, Backtest, Paper, Live)."""
        ...

    def submit_fn(self) -> Callable[..., Order]:
        """Return submit_fn for OrderManager.place_order."""
        ...


__all__ = ["ExecutionTarget", "ExecutionTargetKind"]
