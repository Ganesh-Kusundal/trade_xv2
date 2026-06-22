"""Active broker identity check strategy.

Reports the active broker's identity and capabilities matrix.
"""

from __future__ import annotations

from cli.commands.doctor.checks import CheckResult, CheckStrategy
from cli.services.broker_service import BrokerService


class ActiveBrokerCheck(CheckStrategy):
    """Report active broker identity and capabilities."""

    def execute(self, broker_service: BrokerService | None) -> list[CheckResult]:
        """Check active broker identity and capabilities."""
        results: list[CheckResult] = []

        if broker_service is None:
            results.append(
                CheckResult("Active Broker", "FAIL", "No broker service available")
            )
            return results

        try:
            name = broker_service.active_broker_name
            gw = broker_service.active_broker
            desc = gw.describe() if hasattr(gw, "describe") else {}
            caps = gw.capabilities() if hasattr(gw, "capabilities") else None

            conn_type = desc.get("type", "live")
            results.append(
                CheckResult(
                    "Active Broker",
                    "PASS",
                    f"{name.title()} ({conn_type}) — {desc.get('name', name)} v{desc.get('version', '?')}",
                )
            )

            if caps:
                features = []
                if caps.websocket:
                    features.append("WebSocket")
                if caps.depth_20:
                    features.append("Depth20")
                if caps.depth_200:
                    features.append("Depth200")
                if caps.super_orders:
                    features.append("SuperOrders")
                order_types = ", ".join(caps.order_types[:4])
                results.append(
                    CheckResult(
                        "  Capabilities",
                        "PASS",
                        f"Orders: {order_types} | Features: {', '.join(features) or 'none'}",
                    )
                )
                results.append(
                    CheckResult(
                        "  Rate Limits",
                        "PASS",
                        f"{caps.rate_limit_per_second}/s, {caps.rate_limit_per_minute}/min",
                    )
                )
        except Exception as exc:
            results.append(
                CheckResult(
                    "Active Broker",
                    "FAIL",
                    f"Cannot determine active broker: {exc}",
                )
            )

        return results
