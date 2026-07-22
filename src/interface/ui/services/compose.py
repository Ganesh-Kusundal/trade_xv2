"""Composition root — single entry point for wiring the trading runtime.

Owns BrokerService construction (CLI). API bootstrap uses
:mod:`runtime.api_compose`. All paths delegate to :func:`runtime.factory.build`.
"""

from __future__ import annotations

from pathlib import Path

from runtime.api_compose import build_for_api
from runtime.factory import Runtime, build


def build_runtime(
    broker: str = "dhan",
    *,
    authorize_risk_fail_open: bool = False,
    env_path: Path | None = None,
    wire_orchestrator: bool = True,
    wire_intelligent_gateway: bool | None = None,
    skip_parity_gate: bool | None = None,
) -> Runtime:
    """Single composition root for the trading runtime (CLI path)."""
    from interface.ui.services.broker_service import BrokerService

    bs = BrokerService(authorize_risk_fail_open=authorize_risk_fail_open)
    kwargs: dict = {
        "mode": "trade",
        "broker": broker,
        "authorize_risk_fail_open": authorize_risk_fail_open,
        "env_path": env_path,
        "wire_orchestrator": wire_orchestrator,
        "wire_intelligent_gateway": wire_intelligent_gateway,
    }
    if skip_parity_gate is not None:
        kwargs["skip_parity_gate"] = skip_parity_gate
    return build(bs, **kwargs)


__all__ = ["Runtime", "build_for_api", "build_runtime"]


def _ensure_wired() -> None:
    from runtime.factory import wire_domain_port_sinks
    from runtime.interface_compose import wire_interface_compose

    wire_domain_port_sinks()
    wire_interface_compose()


_ensure_wired()
