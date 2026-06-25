"""Factory functions to bootstrap composers from injected dependencies.

Provides convenience functions to create fully-wired composer instances
with all required coordinators, routers, and schedulers.

Two creation paths:

1. ``create_composers_from_infra(infra)`` — preferred. Takes an existing
   ``BrokerInfrastructure`` and extracts components from it.
2. ``create_composers(gateways, ...)`` — builds infrastructure internally.
   Kept for backward compatibility.
"""

from __future__ import annotations

from application.composer.execution import ExecutionComposer
from application.composer.market_data import MarketDataComposer
from brokers.common.broker_port import CommonBrokerGateway
from brokers.common.historical_coordinator import HistoricalDataCoordinator
from brokers.common.infrastructure import BrokerInfrastructure
from brokers.common.policy import SourceSelectionPolicy
from brokers.common.policy_defaults import default_source_selection_policy
from brokers.common.quota_scheduler import QuotaScheduler
from brokers.common.registry import BrokerRegistry
from brokers.common.router import BrokerRouter
from brokers.common.stream_orchestrator import StreamOrchestrator


def create_composers_from_infra(
    infra: BrokerInfrastructure,
) -> tuple[MarketDataComposer, ExecutionComposer]:
    """Create composers from an existing BrokerInfrastructure.

    This is the preferred creation path when infrastructure is already
    bootstrapped (e.g. via ``bootstrap_from_gateways``).

    Parameters
    ----------
    infra
        Fully-wired BrokerInfrastructure with registry, router, quota,
        historical coordinator, stream orchestrator, and extensions.

    Returns
    -------
    tuple[MarketDataComposer, ExecutionComposer]
        Wired composer instances ready for use.
    """
    market_data = MarketDataComposer(
        historical_coordinator=infra.historical,
        stream_orchestrator=infra.streams,
    )
    execution = ExecutionComposer(
        registry=infra.registry,
        router=infra.router,
        quota_scheduler=infra.quota,
    )
    return market_data, execution


def create_composers(
    gateways: list[CommonBrokerGateway],
    policy: SourceSelectionPolicy | None = None,
    quota_scheduler: QuotaScheduler | None = None,
) -> tuple[MarketDataComposer, ExecutionComposer]:
    """Create fully-wired MarketDataComposer and ExecutionComposer.

    Builds infrastructure internally. Prefer ``create_composers_from_infra``
    when infrastructure is already bootstrapped.

    Parameters
    ----------
    gateways
        List of broker gateway instances to register.
    policy
        Source selection policy. Uses default if None.
    quota_scheduler
        Quota scheduler instance. Creates new instance with defaults if None.

    Returns
    -------
    tuple[MarketDataComposer, ExecutionComposer]
        Wired composer instances ready for use.
    """
    # 1. Create registry and register gateways
    registry = BrokerRegistry()
    for gw in gateways:
        registry.register(gw)

    # 2. Create policy
    if policy is None:
        policy = default_source_selection_policy()

    # 3. Create quota scheduler
    if quota_scheduler is None:
        quota_scheduler = QuotaScheduler()
        for broker_id in registry.list_brokers():
            caps = registry.get_capabilities(broker_id).capabilities
            for profile in caps.rate_limit_profiles:
                quota_scheduler.register_profile(broker_id, profile)

    # 4. Create router
    router = BrokerRouter(
        registry=registry,
        policy=policy,
        quota_headroom_fn=quota_scheduler.headroom_for,
    )

    # 5. Create historical coordinator
    historical_coordinator = HistoricalDataCoordinator(
        registry=registry,
        router=router,
        quota_fn=quota_scheduler.acquire,
    )

    # 6. Create stream orchestrator
    stream_orchestrator = StreamOrchestrator(
        registry=registry,
        router=router,
    )

    # 7. Create composers
    market_data_composer = MarketDataComposer(
        historical_coordinator=historical_coordinator,
        stream_orchestrator=stream_orchestrator,
    )

    execution_composer = ExecutionComposer(
        registry=registry,
        router=router,
        quota_scheduler=quota_scheduler,
    )

    return market_data_composer, execution_composer


def create_market_data_composer(
    gateways: list[CommonBrokerGateway],
    policy: SourceSelectionPolicy | None = None,
) -> MarketDataComposer:
    """Create only MarketDataComposer (for read-only market data use cases)."""
    market_data, _ = create_composers(gateways, policy=policy)
    return market_data


def create_execution_composer(
    gateways: list[CommonBrokerGateway],
    policy: SourceSelectionPolicy | None = None,
    quota_scheduler: QuotaScheduler | None = None,
) -> ExecutionComposer:
    """Create only ExecutionComposer (for execution-only use cases)."""
    _, execution = create_composers(gateways, policy=policy, quota_scheduler=quota_scheduler)
    return execution
