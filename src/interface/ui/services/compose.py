"""Composition root — single entry point for wiring the trading runtime.

Owns BrokerService construction (CLI). API bootstrap uses
:mod:`runtime.api_compose` (registered factory below). All paths delegate to
:func:`runtime.factory.build` (ADR-017).
"""

from __future__ import annotations

from pathlib import Path

from runtime.api_compose import build_for_api, register_broker_service_factory
from runtime.factory import build
from runtime.trading_runtime_factory import Runtime


def build_runtime(
    broker: str = "dhan",
    *,
    authorize_risk_fail_open: bool = False,
    env_path: Path | None = None,
    wire_orchestrator: bool = True,
    wire_intelligent_gateway: bool | None = None,
    skip_parity_gate: bool | None = None,
) -> Runtime:
    """Single composition root for the trading runtime (CLI path).

    ``skip_parity_gate`` defaults from ``SKIP_PARITY_GATE`` env (via
    ``runtime.factory.build``). Do not hardcode True — production forbids skip.
    """
    from interface.ui.services.broker_service import BrokerService

    bs = BrokerService(authorize_risk_fail_open=authorize_risk_fail_open)
    kwargs: dict = dict(
        mode="trade",
        broker=broker,
        authorize_risk_fail_open=authorize_risk_fail_open,
        env_path=env_path,
        wire_orchestrator=wire_orchestrator,
        wire_intelligent_gateway=wire_intelligent_gateway,
    )
    if skip_parity_gate is not None:
        kwargs["skip_parity_gate"] = skip_parity_gate
    return build(bs, **kwargs)


# Register BrokerService so runtime.api_compose.build_for_api works without
# runtime importing interface (import-linter).
def _register() -> None:
    from interface.ui.services.broker_service import BrokerService

    register_broker_service_factory(BrokerService)


_register()


__all__ = ["Runtime", "build_runtime", "build_for_api"]
