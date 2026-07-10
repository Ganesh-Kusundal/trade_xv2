"""RiskProfile — read-only, public view of pre-trade risk state.

Pure domain object. Projects the same limits and running state the OMS's
RiskManager already enforces (application.oms._internal.risk_manager.RiskConfig)
into something a caller can inspect via ``session.account.risk_profile``
without reaching into application-layer internals.

This is additive and read-only: it changes no risk decision, only exposes
visibility into one that already happens. Built by the application layer
(see domain.ports.risk_view.RiskViewPort) and handed to AccountView at
composition-root time — domain code never imports application code.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class RiskProfile:
    """Snapshot of the active risk limits and how much headroom remains today.

    All percentages are expressed the same way RiskConfig expresses them
    (e.g. ``Decimal("2.5")`` means 2.5%, not 0.025).
    """

    max_daily_loss_pct: Decimal
    max_position_pct: Decimal
    max_gross_exposure_pct: Decimal
    kill_switch: bool
    daily_pnl: Decimal
    capital: Decimal

    def headroom_pct(self) -> Decimal:
        """Fraction of the daily-loss budget still remaining, as 0..1.

        1.0 means no loss recorded today. 0.0 or below means the daily-loss
        limit has been reached or exceeded. Only losses count against the
        budget — a positive daily PnL means full headroom remains.
        """
        if self.capital <= 0 or self.max_daily_loss_pct <= 0:
            return Decimal("0")
        if self.daily_pnl >= 0:
            return Decimal("1")
        loss_budget = self.capital * (self.max_daily_loss_pct / Decimal("100"))
        if loss_budget <= 0:
            return Decimal("0")
        used = abs(self.daily_pnl) / loss_budget
        return max(Decimal("0"), Decimal("1") - used)
