"""Authenticated readiness probe diagnostics."""

from __future__ import annotations

from cli.commands.doctor.checks import CheckResult, CheckStrategy
from cli.services.broker_registry import bootstrap_gateway, list_available_brokers
from cli.services.broker_service import BrokerService


class AuthenticatedReadinessCheck(CheckStrategy):
    """Verify live brokers pass authenticated API readiness probes."""

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
                        "Credentials incomplete — probe skipped",
                    )
                )
                continue

            bootstrap = bootstrap_gateway(name, load_instruments=False)
            if bootstrap.live_ready:
                detail = f"probe={bootstrap.probe_name or 'ok'}"
                if bootstrap.refreshed_token:
                    detail += " (token refreshed during probe)"
                results.append(
                    CheckResult(
                        f"  {name.title()} Auth Probe",
                        "PASS",
                        detail,
                    )
                )
            elif bootstrap.probe_passed and not bootstrap.authenticated:
                status = "FAIL" if bootstrap.status.value == "reauth_required" else "WARN"
                detail = bootstrap.error or bootstrap.status.value
                if bootstrap.refreshed_token:
                    detail += " (refresh attempted)"
                results.append(
                    CheckResult(
                        f"  {name.title()} Auth Probe",
                        status,
                        detail,
                    )
                )
            else:
                results.append(
                    CheckResult(
                        f"  {name.title()} Auth Probe",
                        "FAIL",
                        bootstrap.error or "structural or authenticated probe failed",
                    )
                )

        if broker_service is not None:
            dhan_bs = getattr(broker_service, "_dhan_bootstrap", None)
            if dhan_bs is not None:
                results.append(
                    CheckResult(
                        "  Dhan Startup Bootstrap",
                        "PASS" if dhan_bs.live_ready else "FAIL",
                        (
                            f"authenticated={dhan_bs.authenticated} "
                            f"probe={dhan_bs.probe_name or '-'} "
                            f"refreshed={dhan_bs.refreshed_token}"
                        ),
                    )
                )
            upstox_bs = getattr(broker_service, "_upstox_bootstrap", None)
            if upstox_bs is not None:
                results.append(
                    CheckResult(
                        "  Upstox Startup Bootstrap",
                        "PASS" if upstox_bs.live_ready else "WARN",
                        (
                            f"authenticated={upstox_bs.authenticated} "
                            f"probe={upstox_bs.probe_name or '-'} "
                            f"refreshed={upstox_bs.refreshed_token}"
                        ),
                    )
                )

        return results
