"""BrokerPluginInterface — completeness contract for a new broker (TOS-P1-005).

A broker package is complete when it can supply the surfaces below.
Registration still uses the existing registries; this Protocol documents
what "done" means so agents/engineers do not invent a fifth parallel path.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BrokerPluginInterface(Protocol):
    """Minimal surfaces a first-class broker plugin must provide."""

    broker_id: str

    def data_provider_factory(self) -> Any:
        """Return a factory/class implementing DataProvider."""
        ...

    def execution_provider_factory(self) -> Any:
        """Return a factory/class implementing ExecutionProvider / OrderTransportPort."""
        ...

    def register(self) -> None:
        """Register with BrokerPlugin + extension registries."""
        ...


def plugin_checklist() -> list[str]:
    """Human/agent checklist for adding a broker."""
    return [
        "Implement DataProvider + ExecutionProvider (or OrderTransportPort)",
        "Register via register_broker_plugin / entry point tradex.brokers",
        "Register extensions (OrderCapabilityPort) if extended orders supported",
        "Add capabilities module (rate limits, is_live)",
        "Pass paper-equivalent certification suite",
        "Do not edit application.oms for broker-specific branches",
    ]


__all__ = ["BrokerPluginInterface", "plugin_checklist"]
