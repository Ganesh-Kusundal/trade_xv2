"""CLI runtime composition — single entry for broker, OMS, and websocket wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.services.broker_registry import create_gateway, resolve_env_path
from cli.services.broker_service import BrokerService
from cli.services.observability_setup import start_http_observability
from cli.services.oms_setup import build_risk_manager, register_oms_services
from cli.services.websocket_wiring import start_websocket_services


def build_cli_runtime(
    *,
    load_instruments: bool = True,
    event_bus: Any | None = None,
    broker: str = "dhan",
) -> BrokerService:
    """Initialize a :class:`BrokerService` with unified env resolution."""
    service = BrokerService(load_instruments=load_instruments, event_bus=event_bus)
    service._ensure_initialized()
    if broker != service._active_name:
        service.set_active_broker(broker)
    return service


def wire_broker_stack(service: BrokerService) -> None:
    """Explicit wiring steps extracted from :class:`BrokerService` initialization."""
    oms_risk_manager, capital_provider = build_risk_manager(service)
    env_path = resolve_env_path("dhan") or Path(".env.local")
    gateway = create_gateway(
        "dhan",
        env_path=env_path,
        load_instruments=service._load_instruments,
        event_bus=service._event_bus,
        lifecycle=service._lifecycle,
        risk_manager=oms_risk_manager,
    )
    if gateway is not None:
        service._gateway = gateway
        if capital_provider is not None:
            capital_provider.update_gateway(gateway)
    register_oms_services(service, oms_risk_manager)
    start_websocket_services(service._gateway, service._lifecycle)
    service._lifecycle.start_all()
    start_http_observability(service, oms_risk_manager, lifecycle=service._lifecycle)


__all__ = ["BrokerService", "build_cli_runtime", "wire_broker_stack"]
