"""BrokerInfrastructure — composition-root DI container for broker wiring.

Composition root (``runtime/``): allowed to wire application orchestrators
with domain ports. Application-layer code depends on this object and never
imports DhanGateway or UpstoxGateway directly.

Usage at composition root (bootstrap)::

    from runtime.broker_infrastructure import BrokerInfrastructure, build_infrastructure
    from domain.policies.source_selection import auto_dual_broker_policy

    infra = build_infrastructure(
        gateways=[dhan_gw, upstox_gw],
        bundles={"dhan": dhan_bundle, "upstox": upstox_bundle},
        policy=auto_dual_broker_policy(execution_account="dhan"),
    )
    # Streams start on Runtime.start() / await infra.streams.start()

Usage in application code::

    series, ledger = await infra.historical.fetch(query)
    sub_id = await infra.streams.subscribe(request)
    news = infra.extensions.require("upstox", NewsProvider)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from application.composer.registry import BrokerRegistry
from application.composer.router import BrokerRouter
from application.data.batch_quote_coordinator import BatchQuoteCoordinator
from application.data.historical_coordinator import HistoricalDataCoordinator
from application.scheduling.quota_scheduler import QuotaScheduler
from application.streaming.orchestrator import StreamOrchestrator
from domain.capabilities.broker_capabilities import BrokerCapabilities
from domain.extensions.broker_bundle import ExtensionBundle, ExtensionRegistry
from domain.policies.source_selection import SourceSelectionPolicy
from domain.ports.broker_gateway import CommonBrokerGateway
from domain.ports.broker_id import BrokerId


@dataclass
class BrokerInfrastructure:
    """Single facade injected into all application-layer components.

    Composers depend on this object — never on DhanGateway or UpstoxGateway.

    registry    — gateway instances, capabilities, health state.
    router      — broker selection for any operation.
    policy      — source selection configuration (injected, not hardcoded).
    quota       — global API budget coordinator.
    historical  — federated historical data coordinator.
    batch_quotes — federated batch-quote coordinator.
    streams     — stream lifecycle manager.
    extensions  — typed extension interface registry.
    """

    registry: BrokerRegistry
    router: BrokerRouter
    policy: SourceSelectionPolicy
    quota: QuotaScheduler
    historical: HistoricalDataCoordinator
    batch_quotes: BatchQuoteCoordinator
    streams: StreamOrchestrator
    extensions: ExtensionRegistry

    def gateway_for(self, broker_id: str | BrokerId) -> CommonBrokerGateway:
        """Return a gateway by broker_id — for explicit single-broker use cases."""
        return self.registry.get_gateway(broker_id)

    def capabilities_for(self, broker_id: str | BrokerId) -> BrokerCapabilities:
        """Return the capability matrix for a broker."""
        return self.registry.get_capabilities(broker_id).capabilities


def build_infrastructure(
    gateways: Sequence[CommonBrokerGateway],
    policy: SourceSelectionPolicy,
    bundles: dict[str, ExtensionBundle] | None = None,
    *,
    reserved_headroom: float = 0.20,
) -> BrokerInfrastructure:
    """Bootstrap ``BrokerInfrastructure`` from a list of live gateways.

    Registers all gateways and their extension bundles, registers rate profiles
    with the quota scheduler. Does **not** start the stream orchestrator —
    call ``await infra.streams.start()`` from ``Runtime.start()`` (or an
    async lifespan) so composition roots never need ``asyncio.run``.

    Parameters
    ----------
    gateways
        Live broker gateway instances (already authenticated and ready).
    policy
        Source selection policy — use one of the factory helpers in
        ``domain.policies`` or construct your own.
    bundles
        Optional mapping of broker_id → ExtensionBundle.  Pass None if a broker
        has no extensions to register.
    reserved_headroom
        Fraction of each quota bucket held in reserve for execution-critical
        traffic.  Default 20%.
    """
    registry = BrokerRegistry()
    quota = QuotaScheduler(reserved_headroom=reserved_headroom)

    for gw in gateways:
        bundle = (bundles or {}).get(gw.broker_id)
        registry.register(gw, bundle)

        # Register the broker's rate limit profiles with the quota scheduler
        capabilities = gw.list_capabilities().capabilities
        for profile in capabilities.rate_limit_profiles:
            quota.register_profile(gw.broker_id, profile)

    router = BrokerRouter(
        registry=registry,
        policy=policy,
        quota_headroom_fn=quota.headroom_for,
    )

    historical = HistoricalDataCoordinator(
        registry=registry,
        router=router,
        quota_fn=quota.acquire,
    )

    batch_quotes = BatchQuoteCoordinator(
        registry=registry,
        router=router,
        quota_fn=quota.acquire,
    )

    streams = StreamOrchestrator(registry=registry, router=router)
    # ponytail: streams.start() deferred to Runtime.start() — avoids asyncio.run
    # in the composition root when FastAPI/CLI already own a loop.

    return BrokerInfrastructure(
        registry=registry,
        router=router,
        policy=policy,
        quota=quota,
        historical=historical,
        batch_quotes=batch_quotes,
        streams=streams,
        extensions=registry.get_extensions(),
    )
