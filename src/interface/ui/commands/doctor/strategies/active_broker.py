"""Active broker identity check strategy.

Reports the active broker's identity and capabilities matrix.
"""

from __future__ import annotations

from interface.ui.commands.doctor.checks import CheckResult, CheckStrategy
from interface.ui.services.broker_service import BrokerService


class ActiveBrokerCheck(CheckStrategy):
    """Report active broker identity and capabilities."""

    def execute(self, broker_service: BrokerService | None) -> list[CheckResult]:
        """Check active broker identity and capabilities."""
        results: list[CheckResult] = []

        if broker_service is None:
            results.append(CheckResult("Active Broker", "FAIL", "No broker service available"))
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
                if hasattr(caps, "supports_live_market_data"):
                    matrix = {
                        "supports_live_market_data": caps.supports_live_market_data,
                        "supports_depth_20_ws": caps.supports_depth_20_ws,
                        "supports_depth_200_ws": caps.supports_depth_200_ws,
                        "supports_super_order": caps.supports_super_order,
                        "order_types": sorted(caps.order_types),
                        "rate_limit_profiles": [
                            {
                                "sustained_rps": p.sustained_rps,
                                "burst_rps": p.burst_rps,
                            }
                            for p in caps.rate_limit_profiles
                        ],
                    }
                elif isinstance(caps, dict):
                    matrix = caps.get("matrix", caps)
                else:
                    matrix = {}
                features = []
                if matrix.get("supports_live_market_data"):
                    features.append("WebSocket")
                if matrix.get("supports_depth_20_ws"):
                    features.append("Depth20")
                if matrix.get("supports_depth_200_ws"):
                    features.append("Depth200")
                if matrix.get("supports_super_order"):
                    features.append("SuperOrders")
                order_types = matrix.get("order_types") or []
                if isinstance(order_types, (list, tuple, frozenset)):
                    order_types = ", ".join(list(order_types)[:4])
                else:
                    order_types = str(order_types)
                results.append(
                    CheckResult(
                        "  Capabilities",
                        "PASS",
                        f"Orders: {order_types or 'n/a'} | Features: {', '.join(features) or 'none'}",
                    )
                )
                profiles = matrix.get("rate_limit_profiles") or []
                rate_detail = "n/a"
                if profiles:
                    p0 = profiles[0] if isinstance(profiles, list) else None
                    if isinstance(p0, dict):
                        rate_detail = f"{p0.get('sustained_rps', '?')}/s burst {p0.get('burst_rps', '?')}"
                results.append(
                    CheckResult(
                        "  Rate Limits",
                        "PASS",
                        rate_detail,
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
