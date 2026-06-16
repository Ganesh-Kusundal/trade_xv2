"""BrokerProviderFactory — abstract interface for broker factory implementations.

Both BrokerFactory (Dhan) and UpstoxBrokerFactory should implement this
interface so BrokerService can call either factory polymorphically.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from brokers.common.gateway import MarketDataGateway


class BrokerProviderFactory(ABC):
    """Abstract factory for creating configured MarketDataGateway instances."""

    @abstractmethod
    def create(
        self,
        *,
        env_path: Path | None = None,
        load_instruments: bool = True,
        event_bus: Any | None = None,
        risk_manager: Any | None = None,
        lifecycle: Any | None = None,
    ) -> MarketDataGateway:
        """Create a configured MarketDataGateway for this broker.

        Parameters
        ----------
        env_path:
            Path to the .env file with broker credentials.
        load_instruments:
            Whether to load the instrument master on creation.
        event_bus:
            Optional EventBus for domain event publishing.
        risk_manager:
            Optional RiskManager for pre-trade risk checks.
        lifecycle:
            Optional LifecycleManager for managed service registration.
        """
        ...
