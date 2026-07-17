"""API composition root — build_for_api without interface.api → interface.ui.

BrokerService lives in the UI package today. Callers register a factory
(UI compose does this on import) or pass ``broker_service_factory`` explicitly
so runtime never imports ``interface`` (import-linter).
"""

from __future__ import annotations

from typing import Any, Callable

from runtime.factory import build
from runtime.factory import Runtime

_BrokerServiceFactory: Callable[..., Any] | None = None


def register_broker_service_factory(factory: Callable[..., Any]) -> None:
    """Register the BrokerService constructor (called from UI compose)."""
    global _BrokerServiceFactory
    _BrokerServiceFactory = factory


def build_for_api(
    *,
    wire_orchestrator: bool = True,
    skip_parity_gate: bool = False,
    wire_intelligent_gateway: bool | None = None,
    broker_service_factory: Callable[..., Any] | None = None,
) -> Runtime:
    """API bootstrap: single AsyncEventBus shared with BrokerService + OMS."""
    factory = broker_service_factory or _BrokerServiceFactory
    if factory is None:
        raise RuntimeError(
            "BrokerService factory not registered. Pass broker_service_factory=... "
            "or import interface.ui.services.compose (registers on import)."
        )
    from runtime.composition import create_api_event_bus

    event_bus, _ = create_api_event_bus(maxsize=2000)
    bs = factory(event_bus=event_bus)
    return build(
        bs,
        mode="trade",
        skip_parity_gate=skip_parity_gate,
        wire_orchestrator=wire_orchestrator,
        wire_intelligent_gateway=(
            wire_intelligent_gateway if wire_intelligent_gateway is not None else True
        ),
    )


__all__ = [
    "Runtime",
    "build_for_api",
    "register_broker_service_factory",
]
