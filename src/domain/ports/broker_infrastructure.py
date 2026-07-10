"""BrokerInfrastructurePort — protocol for the broker infrastructure container.

Application-layer code depends on this protocol rather than the concrete
``runtime.broker_infrastructure.BrokerInfrastructure`` dataclass, keeping
the dependency direction correct (application → domain, never application → runtime).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from domain.capabilities.broker_capabilities import BrokerCapabilities


@runtime_checkable
class BrokerInfrastructurePort(Protocol):
    """Structural protocol matching ``runtime.broker_infrastructure.BrokerInfrastructure``."""

    @property
    def registry(self) -> Any: ...
    @property
    def router(self) -> Any: ...
    @property
    def policy(self) -> Any: ...
    @property
    def quota(self) -> Any: ...
    @property
    def historical(self) -> Any: ...
    @property
    def streams(self) -> Any: ...
    @property
    def extensions(self) -> Any: ...
    def gateway_for(self, broker_id: str) -> Any: ...
    def capabilities_for(self, broker_id: str) -> BrokerCapabilities: ...
