"""TradingState — ACTIVE/REDUCING/HALTED FSM for risk gating.

Modeled after Nautilus RiskEngine trading state:
- ACTIVE: normal trading, all orders allowed
- REDUCING: only risk-reducing orders allowed (e.g., sell to close)
- HALTED: no new orders allowed
"""

from __future__ import annotations

from enum import Enum


class TradingStateEnum(str, Enum):
    ACTIVE = "ACTIVE"
    REDUCING = "REDUCING"
    HALTED = "HALTED"


class TradingState:
    """FSM for trading state with order gating."""

    def __init__(self) -> None:
        self._state = TradingStateEnum.ACTIVE

    @property
    def state(self) -> TradingStateEnum:
        return self._state

    def set_state(self, state: TradingStateEnum) -> None:
        self._state = state

    def allows_new_order(self, *, side: str = "", current_qty: int = 0, new_qty: int = 0) -> bool:
        """Check if a new order is allowed in the current state."""
        if self._state == TradingStateEnum.HALTED:
            return False
        if self._state == TradingStateEnum.ACTIVE:
            return True
        # REDUCING: only allow orders that reduce position
        if self._state == TradingStateEnum.REDUCING:
            if current_qty == 0:
                return False
            if side == "SELL" and current_qty > 0 and new_qty <= current_qty:
                return True
            return bool(side == "BUY" and current_qty < 0 and new_qty >= abs(current_qty))
        return False
