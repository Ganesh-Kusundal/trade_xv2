"""Portfolio check strategy.

Checks positions, holdings, and funds balance.
"""

from __future__ import annotations

from interface.ui.commands.doctor.checks import CheckResult, CheckStrategy
from interface.ui.services.broker_service import BrokerService


class PortfolioCheck(CheckStrategy):
    """Check positions, holdings, and funds balance."""

    def execute(self, broker_service: BrokerService | None) -> list[CheckResult]:
        """Check portfolio API endpoints."""
        results: list[CheckResult] = []

        if broker_service is None:
            results.append(CheckResult("Portfolio", "FAIL", "No broker service available"))
            return results

        from interface.ui.services.active_session import get_active_session
        from interface.ui.services.market_access import refresh_account

        session = get_active_session(broker_service)
        try:
            acct = refresh_account(session)
            positions = acct.positions
            holdings = acct.holdings
            balance = acct.funds
        finally:
            session.close()

        # Positions
        try:
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
