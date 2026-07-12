"""Gateway creation smoke test strategy.

Tests that ``bootstrap_gateway()`` can instantiate a gateway for each
registered broker.
"""

from __future__ import annotations

from domain.ports.bootstrap import BootstrapStatus
from interface.ui.commands.doctor.checks import CheckResult, CheckStrategy
from interface.ui.services.broker_registry import bootstrap_gateway, list_available_brokers
from interface.ui.services.broker_service import BrokerService


class GatewayCreationCheck(CheckStrategy):
    """Smoke-test gateway bootstrap via ``bootstrap_gateway()`` for each broker.

    This is a lightweight check — it validates the factory can create
    a gateway without full initialization (load_instruments=False).
    """

    def execute(self, broker_service: BrokerService | None) -> list[CheckResult]:
        """Attempt gateway creation for each registered broker."""
        results: list[CheckResult] = []
        brokers = list_available_brokers()

        for b in brokers:
            name = b["name"]

            if b["env_file"] is None:
                results.append(
                    CheckResult(
                        f"  {name.title()}",
                        "INFO",
                        "No gateway creation needed (paper broker)",
                    )
                )
                continue

            try:
                result = bootstrap_gateway(name, load_instruments=False)
                if result.ok:
                    detail = f"Gateway ready ({result.status.value})"
                    if result.probe_name:
                        detail += f", probe={result.probe_name}"
                    results.append(
                        CheckResult(
                            f"  {name.title()}",
                            "PASS",
                            detail,
                        )
                    )
                elif result.status == BootstrapStatus.REAUTH_REQUIRED:
                    results.append(
                        CheckResult(
                            f"  {name.title()}",
                            "FAIL",
                            f"Reauth required: {result.error or 'token rejected'}",
                        )
                    )
                elif result.status == BootstrapStatus.DEGRADED:
                    results.append(
                        CheckResult(
                            f"  {name.title()}",
                            "WARN",
                            f"Degraded: {result.error or 'structural probe failed'}",
                        )
                    )
                else:
                    results.append(
                        CheckResult(
                            f"  {name.title()}",
                            "FAIL",
                            result.error or f"bootstrap failed: {result.status.value}",
                        )
                    )
            except Exception as exc:
                results.append(
                    CheckResult(
                        f"  {name.title()}",
                        "FAIL",
                        f"bootstrap_gateway('{name}') raised: {exc}",
                    )
                )

        return results
