"""Order API check strategy.

Validates order book and trade book API endpoints.
"""

from __future__ import annotations

from cli.commands.doctor.checks import CheckResult, CheckStrategy
from cli.services.broker_service import BrokerService


class OrderAPICheck(CheckStrategy):
    """Check order book and trade book API endpoints."""

    def execute(self, broker_service: BrokerService | None) -> list[CheckResult]:
        """Check order and trade book reachability."""
        results: list[CheckResult] = []

        if broker_service is None:
            results.append(CheckResult("Order API", "FAIL", "No broker service available"))
            return results

        gw = broker_service.active_broker

        # Order book
        try:
            orders = gw.get_orderbook()
            results.append(
                CheckResult(
                    "Order Book",
                    "PASS",
                    f"{len(orders)} order(s) retrieved",
                )
            )
        except Exception as exc:
            results.append(CheckResult("Order Book", "FAIL", f"Order book failed: {exc}"))

        # Trade book
        try:
            trades = gw.get_trade_book()
            results.append(
                CheckResult(
                    "Trade Book",
                    "PASS",
                    f"{len(trades)} trade(s) retrieved",
                )
            )
        except Exception as exc:
            results.append(CheckResult("Trade Book", "FAIL", f"Trade book failed: {exc}"))

        return results
