"""Lifecycle health check strategy.

Checks every ManagedService registered with the LifecycleManager.
"""

from __future__ import annotations

from cli.commands.doctor.checks import CheckResult, CheckStrategy
from cli.services.broker_service import BrokerService


class LifecycleCheck(CheckStrategy):
    """Check every ManagedService registered with the LifecycleManager."""

    def execute(self, broker_service: BrokerService | None) -> list[CheckResult]:
        """Check lifecycle health snapshot."""
        results: list[CheckResult] = []

        if broker_service is None:
            results.append(CheckResult("Lifecycle", "FAIL", "No broker service available"))
            return results

        try:
            snapshot = broker_service.lifecycle.health_snapshot()
        except Exception as exc:
            results.append(CheckResult("Lifecycle", "FAIL", f"Health snapshot failed: {exc}"))
            return results

        if not snapshot:
            results.append(
                CheckResult("Lifecycle", "WARN", "No ManagedServices registered (lifecycle empty)")
            )
            return results

        service_names = list(snapshot.keys())
        failed = [(n, s) for n, s in snapshot.items() if s.get("state") in ("FAILED", "UNHEALTHY")]
        degraded = [(n, s) for n, s in snapshot.items() if s.get("state") in ("DEGRADED",)]

        n_services = len(snapshot)
        n_failed = len(failed)
        n_degraded = len(degraded)

        if n_failed == 0 and n_degraded == 0:
            results.append(
                CheckResult(
                    "Lifecycle",
                    "PASS",
                    f"{n_services} service(s): {', '.join(service_names)}",
                )
            )
        elif n_failed == 0:
            results.append(
                CheckResult(
                    "Lifecycle",
                    "WARN",
                    f"{n_services} service(s), {n_degraded} degraded: "
                    f"{', '.join(n for n, _ in degraded[:3])}",
                )
            )
        else:
            failed_detail = ", ".join(f"{n}({s.get('state', '?')})" for n, s in failed[:5])
            results.append(
                CheckResult(
                    "Lifecycle",
                    "FAIL",
                    f"{n_failed}/{n_services} service(s) failed: {failed_detail}",
                )
            )

        # Detail per service
        for name, info in snapshot.items():
            state = info.get("state", "?")
            detail = info.get("detail", "") or info.get("metrics", {})
            if isinstance(detail, dict):
                detail_str = "; ".join(f"{k}={v}" for k, v in detail.items() if v is not None)
            else:
                detail_str = str(detail) if detail else ""

            if state == "HEALTHY":
                results.append(CheckResult(f"  {name}", "PASS", detail_str or "healthy"))
            elif state in ("DEGRADED",):
                results.append(CheckResult(f"  {name}", "WARN", detail_str or "degraded"))
            elif state in ("FAILED", "UNHEALTHY"):
                results.append(CheckResult(f"  {name}", "FAIL", detail_str or state))
            else:
                results.append(CheckResult(f"  {name}", "INFO", f"state={state}: {detail_str}"))

        return results
