"""RiskManager — pre-trade gate + kill switch; fail closed on exception."""

from __future__ import annotations

from application.risk.context import RiskCheckResult, RiskContext
from application.risk.rules import RiskRule, RiskRulesEngine
from domain.commands import PlaceOrderCommand


class RiskManager:
    """ponytail: plain class (no Component lifecycle until bus wiring needed)."""

    def __init__(self, rules: list[RiskRule] | None = None) -> None:
        self._engine = RiskRulesEngine(rules or [])
        self._kill_switch = False
        self._kill_reason = ""

    def check_order(
        self, command: PlaceOrderCommand, context: RiskContext
    ) -> RiskCheckResult:
        try:
            if self._kill_switch:
                reason = self._kill_reason or "kill switch active"
                return RiskCheckResult(approved=False, reason=f"Kill switch: {reason}")
            return self._engine.check(command, context)
        except Exception as exc:  # fail closed — deny on any check failure
            return RiskCheckResult(approved=False, reason=f"risk check failed: {exc}")

    def activate_kill_switch(self, reason: str = "") -> None:
        self._kill_switch = True
        self._kill_reason = reason

    def reset_kill_switch(self) -> None:
        self._kill_switch = False
        self._kill_reason = ""

    @property
    def is_kill_switch_active(self) -> bool:
        return self._kill_switch
