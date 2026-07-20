"""Single kill-switch gate for all OMS order mutations (place/modify/cancel)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from application.oms._internal.risk_manager import RiskManager

MutationAction = Literal["place", "modify", "cancel"]


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    reason: str | None = None


class OrderMutationGuard:
    """Fail-closed kill-switch check for order-mutating OMS operations."""

    def __init__(self, risk_manager: RiskManager | None) -> None:
        self._risk_manager = risk_manager

    def check(self, action: MutationAction) -> GuardResult:
        if self._risk_manager is None:
            return GuardResult(allowed=True)
        if self._risk_manager.is_kill_switch_active():
            return GuardResult(
                allowed=False,
                reason=f"Order blocked: kill switch active ({action})",
            )
        return GuardResult(allowed=True)
