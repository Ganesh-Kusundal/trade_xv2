"""Live auth probe for doctor — read-only by default; optional force refresh.

Never mints TOTP unless:
  * probe fails with token rejection **and** ``force_refresh=True``, or
  * ``authenticated_readiness_probe`` decides refresh after rejection
    (only when force_refresh=True for doctor auth mode).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from interface.ui.commands.doctor.checks import CheckResult, CheckStrategy
from interface.ui.services.broker_registry import list_available_brokers
from interface.ui.services.broker_service import BrokerService
from infrastructure.connection.authenticated_readiness import (
    AuthProbeResult,
    authenticated_readiness_probe,
    execute_read_only_probe,
)


class AuthLiveProbeCheck(CheckStrategy):
    """Probe broker APIs with existing credentials (no mint unless force)."""

    def __init__(
        self,
        *,
        force_refresh: bool = False,
        broker: str | None = None,
        env_path: str | Path | None = None,
    ) -> None:
        self.force_refresh = force_refresh
        self.broker = broker.lower().strip() if broker else None
        self.env_path = env_path

    def execute(self, broker_service: BrokerService | None) -> list[CheckResult]:
        results: list[CheckResult] = []
        for entry in list_available_brokers():
            name = entry["name"]
            if self.broker and name != self.broker:
                continue
            if name == "paper":
                results.append(
                    CheckResult(
                        f"  {name.title()} Live Auth",
                        "INFO",
                        "Paper broker — no auth probe",
                    )
                )
                continue
            if not entry.get("available"):
                results.append(
                    CheckResult(
                        f"  {name.title()} Live Auth",
                        "WARN",
                        "Env/credentials incomplete — cannot probe",
                    )
                )
                continue

            results.extend(self._probe_broker(name, broker_service))
        return results

    def _probe_broker(
        self, name: str, broker_service: BrokerService | None
    ) -> list[CheckResult]:
        label = f"  {name.title()} Live Auth"
        try:
            gateway = self._get_gateway(name, broker_service)
        except Exception as exc:
            return [CheckResult(label, "FAIL", f"gateway create failed: {exc}")]

        if gateway is None:
            return [CheckResult(label, "FAIL", "gateway is None")]

        if self.force_refresh:
            probe = authenticated_readiness_probe(
                gateway, name, env_path=self.env_path
            )
            return [self._to_result(label, probe, forced=True)]

        # Probe-only: never call force refresh / TOTP.
        probe = execute_read_only_probe(gateway, name)
        return [self._to_result(label, probe, forced=False)]

    def _get_gateway(
        self, name: str, broker_service: BrokerService | None
    ) -> Any | None:
        # Prefer service gateways when available
        if broker_service is not None:
            # G1: use public active_broker_name instead of getattr(_active_name)
            active_name = broker_service.active_broker_name
            if name == "dhan":
                gw = broker_service.dhan_gateway
                if gw is not None:
                    return gw
            if name == "upstox":
                gw = broker_service.upstox_gateway
                if gw is not None:
                    return gw
            # Fall back to active broker if names match
            if active_name and str(active_name).lower() == name:
                try:
                    return broker_service.active_broker
                except Exception:
                    pass

        from interface.ui.services.connect import connect_analytics
        from interface.ui.services.broker_registry import resolve_env_path

        env = self.env_path or resolve_env_path(name)
        result = connect_analytics(name, env_path=env, load_instruments=False)
        return result.gateway if result.ok else None

    @staticmethod
    def _to_result(
        label: str, probe: AuthProbeResult, *, forced: bool
    ) -> CheckResult:
        mode = "force-refresh" if forced else "probe-only"
        if probe.ok:
            detail = f"{mode} ok probe={probe.probe_name or 'ok'}"
            if probe.refreshed_token:
                detail += " (token refreshed)"
            return CheckResult(label, "PASS", detail)

        status = "FAIL" if probe.token_rejected else "WARN"
        detail = f"{mode}: {probe.error or 'probe failed'}"
        if probe.token_rejected and not forced:
            detail += " — re-run with --force-refresh to mint once under cooldown"
        if probe.refreshed_token:
            detail += " (refresh attempted)"
        return CheckResult(label, status, detail)
