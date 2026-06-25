"""HTTP observability check strategy.

Checks the HTTP observability server (/healthz, /readyz, /metrics).
"""

from __future__ import annotations

from cli.commands.doctor.checks import CheckResult, CheckStrategy
from cli.services.broker_service import BrokerService


class HTTPObservabilityCheck(CheckStrategy):
    """Check the HTTP observability server (/healthz, /readyz, /metrics)."""

    def execute(self, broker_service: BrokerService | None) -> list[CheckResult]:
        """Check HTTP observability server health."""
        results: list[CheckResult] = []

        if broker_service is None:
            results.append(CheckResult("HTTP Observability", "WARN", "No broker service available"))
            return results

        server = broker_service.http_observability
        if server is None:
            results.append(
                CheckResult(
                    "HTTP Observability",
                    "WARN",
                    "Server not started (bind may have failed or init incomplete)",
                )
            )
            return results

        try:
            h = server.health()
            port = h.metrics.get("port", 0)
            state = h.state.value
            if state == "HEALTHY":
                results.append(
                    CheckResult(
                        "HTTP Observability",
                        "PASS",
                        f"Listening on 127.0.0.1:{port} (state={state})",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        "HTTP Observability",
                        "WARN",
                        f"Listening on 127.0.0.1:{port} (state={state})",
                    )
                )
        except Exception as exc:
            results.append(
                CheckResult(
                    "HTTP Observability",
                    "FAIL",
                    f"Health check failed: {exc}",
                )
            )

        return results
