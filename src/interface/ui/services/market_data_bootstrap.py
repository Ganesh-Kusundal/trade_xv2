"""Market Data Bootstrap — read-only gateway bootstrap for market-data-only
sessions.

Extracted from BrokerService (matching OmsBootstrap/BrokerManager/
CliBrokerFacade) to keep a single responsibility: bootstrap a broker
gateway for live quotes/depth with no OMS/risk-manager/reconciliation
wiring and no ProductionReadinessChecker gate. Independent of
BrokerService._ensure_initialized()/the full live-trade bootstrap, so it
never discards a working gateway over an unrelated trade-readiness
failure, and never requires one to run.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from domain.errors import BrokerNotReadyError
from domain.ports.broker_adapter import BrokerAdapter as MarketDataGateway
from interface.ui.services.broker_registry import bootstrap_gateway

if TYPE_CHECKING:
    from interface.ui.services.broker_service import BrokerService

logger = logging.getLogger(__name__)


class MarketDataBootstrap:
    """Bootstraps broker gateways for read-only market-data sessions.

    Every method receives the owning :class:`BrokerService` via the
    constructor so it can read shared state (lifecycle, etc.), matching
    the pattern used by :class:`~interface.ui.services.oms_bootstrap.OmsBootstrap`
    and :class:`~interface.ui.services.broker_manager.BrokerManager`.
    """

    def __init__(self, service: BrokerService) -> None:
        self._svc = service
        self._gateways: dict[str, MarketDataGateway] = {}

    def market_gateway(self, name: str) -> MarketDataGateway:
        """Bootstrap *name* for read-only market data only. Cached per
        broker name; safe to call repeatedly."""
        key = (name or "").lower().strip()
        cached = self._gateways.get(key)
        if cached is not None:
            return cached

        from runtime.event_loop import ensure_runtime_loop_running

        ensure_runtime_loop_running()

        result = bootstrap_gateway(
            key,
            load_instruments=True,
            lifecycle=self._svc.lifecycle,
            require_authenticated=True,
        )
        if not result.live_ready or result.gateway is None:
            raise BrokerNotReadyError.from_bootstrap(result)
        self._svc.lifecycle.start_all()
        self._gateways[key] = result.gateway
        return result.gateway
