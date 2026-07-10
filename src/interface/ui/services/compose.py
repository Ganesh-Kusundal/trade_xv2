"""Composition root — single entry point for wiring the trading runtime.

Owns BrokerService construction (CLI + API). Runtime package wires an
already-built broker service via :meth:`TradingRuntimeFactory.build_from_broker_service`.
"""

from __future__ import annotations

from pathlib import Path

from runtime.trading_runtime_factory import Runtime, TradingRuntimeFactory


def build_runtime(
    broker: str = "dhan",
    *,
    authorize_risk_fail_open: bool = False,
    env_path: Path | None = None,
    wire_orchestrator: bool = True,
    wire_intelligent_gateway: bool | None = None,
    skip_parity_gate: bool = True,
) -> Runtime:
    """Single composition root for the trading runtime (CLI path)."""
    from interface.ui.services.broker_service import BrokerService

    bs = BrokerService()
    return TradingRuntimeFactory(
        broker=broker,
        authorize_risk_fail_open=authorize_risk_fail_open,
        env_path=env_path,
        wire_orchestrator=wire_orchestrator,
        wire_intelligent_gateway=wire_intelligent_gateway,
        skip_parity_gate=skip_parity_gate,
    ).build_from_broker_service(bs)


def build_for_api(
    *,
    wire_orchestrator: bool = True,
    skip_parity_gate: bool = False,
    wire_intelligent_gateway: bool | None = None,
) -> Runtime:
    """API bootstrap: single AsyncEventBus shared with BrokerService + OMS."""
    from interface.ui.services.broker_service import BrokerService
    from runtime.composition import create_api_event_bus

    event_bus, _ = create_api_event_bus(maxsize=2000)
    bs = BrokerService(event_bus=event_bus)
    factory = TradingRuntimeFactory(
        wire_orchestrator=wire_orchestrator,
        skip_parity_gate=skip_parity_gate,
        wire_intelligent_gateway=(
            wire_intelligent_gateway if wire_intelligent_gateway is not None else True
        ),
    )
    return factory.build_from_broker_service(bs)


__all__ = ["Runtime", "build_runtime", "build_for_api"]
