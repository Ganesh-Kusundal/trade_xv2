"""OMS RiskManager check strategy.

Validates OMS RiskManager state: kill-switch, daily PnL, resets.
"""

from __future__ import annotations

from interface.ui.commands.doctor.checks import CheckResult, CheckStrategy
from interface.ui.services.broker_service import BrokerService


class OMSRiskManagerCheck(CheckStrategy):
    """Check OMS RiskManager state: kill-switch, daily PnL, resets."""

    def execute(self, broker_service: BrokerService | None) -> list[CheckResult]:
        """Check OMS RiskManager health."""
        results: list[CheckResult] = []

        if broker_service is None:
            results.append(CheckResult("OMS RiskManager", "WARN", "No broker service available"))
            return results

        tc = broker_service.trading_context
        if tc is None:
            results.append(
                CheckResult(
                    "OMS RiskManager",
                    "WARN",
                    "No TradingContext (init failed or mock mode)",
                )
            )
            return results

        try:
            rm = tc.risk_manager
            snap = rm.snapshot()
            ks = "ACTIVE" if snap.get("kill_switch") else "inactive"
            daily_pnl = float(snap.get("daily_pnl", 0))
            resets = int(snap.get("reset_count", 0))
            results.append(
                CheckResult(
                    "OMS RiskManager",
                    "PASS",
                    f"kill_switch={ks} | daily_pnl={daily_pnl:.2f} | resets={resets}",
                )
            )
        except Exception as exc:
            results.append(CheckResult("OMS RiskManager", "FAIL", f"Risk snapshot failed: {exc}"))

        return results
