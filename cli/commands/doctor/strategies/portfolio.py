"""Portfolio check strategy.

Checks positions, holdings, and funds balance.
"""

from __future__ import annotations

from cli.commands.doctor.checks import CheckResult, CheckStrategy
from cli.services.broker_service import BrokerService


class PortfolioCheck(CheckStrategy):
    """Check positions, holdings, and funds balance."""

    def execute(self, broker_service: BrokerService | None) -> list[CheckResult]:
        """Check portfolio API endpoints."""
        results: list[CheckResult] = []

        if broker_service is None:
            results.append(CheckResult("Portfolio", "FAIL", "No broker service available"))
            return results

        gw = broker_service.active_broker

        # Positions
        try:
            positions = gw.positions()
            results.append(
                CheckResult(
                    "Positions",
                    "PASS",
                    f"{len(positions)} open position(s)",
                )
            )
        except Exception as exc:
            results.append(CheckResult("Positions", "FAIL", f"Positions failed: {exc}"))

        # Holdings
        try:
            holdings = gw.holdings()
            results.append(
                CheckResult(
                    "Holdings",
                    "PASS",
                    f"{len(holdings)} holding(s)",
                )
            )
        except Exception as exc:
            results.append(CheckResult("Holdings", "FAIL", f"Holdings failed: {exc}"))

        # Balance / Funds
        try:
            balance = gw.funds()
            available = getattr(balance, "available_balance", None)
            sod = getattr(balance, "sod_limit", None)
            if available is not None:
                results.append(
                    CheckResult(
                        "Funds",
                        "PASS",
                        f"Available: Rs. {available:,.2f}"
                        + (f" | SOD Limit: Rs. {sod:,.2f}" if sod else ""),
                    )
                )
            else:
                results.append(
                    CheckResult(
                        "Funds",
                        "WARN",
                        "Balance returned but available_balance is None",
                    )
                )
        except Exception as exc:
            results.append(CheckResult("Funds", "FAIL", f"Funds failed: {exc}"))

        return results
