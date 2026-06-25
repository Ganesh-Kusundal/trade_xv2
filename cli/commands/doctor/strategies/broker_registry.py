"""Broker registry check strategy.

Validates that brokers are registered and their environment files exist.
"""

from __future__ import annotations

from cli.commands.doctor.checks import CheckResult, CheckStrategy
from cli.services.broker_registry import list_available_brokers, resolve_env_path
from cli.services.broker_service import BrokerService


class BrokerRegistryCheck(CheckStrategy):
    """Validates broker registry and environment file status.

    This check does not require a broker_service instance — it queries
    the registry directly.
    """

    def execute(self, broker_service: BrokerService | None) -> list[CheckResult]:
        """Check all registered brokers and their env file status."""
        results: list[CheckResult] = []
        brokers = list_available_brokers()

        if not brokers:
            results.append(CheckResult("Registered Brokers", "FAIL", "No brokers registered!"))
            return results

        results.append(
            CheckResult(
                "Registered Brokers",
                "PASS",
                f"{len(brokers)} broker(s): {', '.join(b['name'] for b in brokers)}",
            )
        )

        for b in brokers:
            name = b["name"]
            env_file = b["env_file"]
            available = b["available"]

            if env_file is None:
                results.append(
                    CheckResult(
                        f"  {name.title()}",
                        "INFO",
                        "No env file needed (paper broker).",
                    )
                )
            elif available:
                resolved = resolve_env_path(name)
                size = resolved.stat().st_size if resolved and resolved.exists() else 0
                results.append(
                    CheckResult(
                        f"  {name.title()}",
                        "PASS",
                        f"Env file found: {resolved} ({size:,} bytes)",
                    )
                )
            else:
                resolved = resolve_env_path(name)
                results.append(
                    CheckResult(
                        f"  {name.title()}",
                        "WARN",
                        f"Env file missing: {resolved}",
                    )
                )

        return results
