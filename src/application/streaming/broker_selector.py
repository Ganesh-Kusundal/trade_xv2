"""BrokerSelector — broker selection logic for stream subscriptions.

Decouples the "which broker should handle this stream?" decision from
session lifecycle and message routing.  Pure selection: no side effects.
"""

from __future__ import annotations

import logging

from domain.models.routing import OperationKind, RoutingRequest

logger = logging.getLogger(__name__)


class BrokerSelector:
    """Selects a broker for a stream subscription request.

    Checks preferred-broker hints first (with liveness filtering), then
    falls back to the routing policy.
    """

    def __init__(self, registry, router) -> None:
        self._registry = registry
        self._router = router

    async def select_broker(self, request, trace_id: str) -> str:
        """Return a broker_id for the given subscription request.

        *Preferred brokers* — when the caller lists preferred brokers they
        are checked in order; the first one that reports usable health wins.
        *Routing fallback* — if none of the preferred brokers are usable (or
        none were specified), the ``BrokerRouter`` policy engine decides.
        """
        if request.preferred_brokers:
            for bid in request.preferred_brokers:
                health = self._registry.get_health(bid)
                if health.is_usable():
                    return bid

        operation = (
            OperationKind.OPEN_MARKET_STREAM
            if request.stream_kind == "market"
            else OperationKind.OPEN_ORDER_STREAM
        )
        routing_request = RoutingRequest(
            operation=operation,
            trace_id=trace_id,
        )
        decision = self._router.route(routing_request)
        return decision.primary_broker
