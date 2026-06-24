"""Doctor authenticated readiness — use cached bootstrap, no re-probe."""

from __future__ import annotations

from cli.commands.doctor.checks import CheckResult, CheckStrategy
from cli.services.broker_registry import list_available_brokers
from cli.services.broker_service import BrokerService


class AuthenticatedReadinessCheck(CheckStrategy):
    """Report authenticated readiness from startup bootstrap cache.

    Does not re-run ``bootstrap_gateway`` to avoid TOTP rate limits on
    routine ``doctor`` invocations.
    """

    def execute(self, broker_service: BrokerService | None) -> list[CheckResult]:
        results: list[CheckResult] = []

        for entry in list_available_brokers():
            name = entry["name"]
            if name == "paper":
                results.append(
                    CheckResult(
                        f"  {name.title()} Auth Probe",
                        "INFO",
                        "Paper broker — no authenticated probe required",
                    )
                )
                continue

            if not entry.get("available"):
                results.append(
                    CheckResult(
                        f"  {name.title()} Auth Probe",
                        "WARN",
                        "Credentials incomplete — run bootstrap at startup to probe",
                    )
                )
                continue

            if broker_service is None:
                results.append(
                    CheckResult(
                        f"  {name.title()} Auth Probe",
                        "WARN",
                        "BrokerService not initialized — probe status unknown",
                    )
                )
                continue

            attr = "_dhan_bootstrap" if name == "dhan" else "_upstox_bootstrap"
            bootstrap = getattr(broker_service, attr, None)
            if bootstrap is None:
                results.append(
                    CheckResult(
                        f"  {name.title()} Auth Probe",
                        "WARN",
                        "No startup bootstrap recorded",
                    )
                )
                continue

            label = f"  {name.title()} Startup Bootstrap"
            if bootstrap.live_ready:
                detail = f"probe={bootstrap.probe_name or 'ok'}"
                if bootstrap.refreshed_token:
                    detail += " (token refreshed during probe)"
                results.append(CheckResult(label, "PASS", detail))
            elif bootstrap.probe_passed and not bootstrap.authenticated:
                status = "FAIL" if bootstrap.status.value == "reauth_required" else "WARN"
                detail = bootstrap.error or bootstrap.status.value
                if bootstrap.refreshed_token:
                    detail += " (refresh attempted)"
                results.append(CheckResult(label, status, detail))
            else:
                results.append(
                    CheckResult(
                        label,
                        "FAIL",
                        bootstrap.error or "structural or authenticated probe failed",
                    )
                )

        return results
