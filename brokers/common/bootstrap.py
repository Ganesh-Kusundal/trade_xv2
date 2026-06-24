"""Bootstrap BrokerInfrastructure from legacy MarketDataGateway instances."""

from __future__ import annotations

import os
from typing import Any, Sequence

from brokers.common.adapters import build_extension_bundle
from brokers.common.adapters.market_data_gateway_adapter import wrap_market_gateway
from brokers.common.gateway import MarketDataGateway
from brokers.common.infrastructure import BrokerInfrastructure, build_infrastructure
from brokers.common.policy import (
    SourceSelectionPolicy,
    auto_dual_broker_policy,
    default_dhan_only_policy,
)


def policy_from_env(execution_account: str | None = None) -> SourceSelectionPolicy:
    """Select routing policy from environment."""
    mode = os.environ.get("TRADEX_BROKER_POLICY", "auto").lower()
    exec_account = execution_account or os.environ.get("TRADEX_EXECUTION_BROKER", "dhan")
    if mode == "dhan":
        return default_dhan_only_policy()
    if mode == "upstox":
        from brokers.common.policy import default_upstox_only_policy

        return default_upstox_only_policy()
    return auto_dual_broker_policy(execution_account=exec_account)


async def bootstrap_from_gateways(
    gateways: Sequence[tuple[str, MarketDataGateway]],
    *,
    policy: SourceSelectionPolicy | None = None,
) -> BrokerInfrastructure:
    """Wrap legacy gateways and build full BrokerInfrastructure."""
    common_gateways = []
    bundles = {}
    for broker_id, legacy_gw in gateways:
        bundle = build_extension_bundle(broker_id, legacy_gw)
        adapter = wrap_market_gateway(
            legacy_gw,
            broker_id,
            extensions=bundle.registered_names(),
        )
        common_gateways.append(adapter)
        bundles[broker_id] = bundle

    return await build_infrastructure(
        common_gateways,
        policy or policy_from_env(),
        bundles=bundles,
    )


async def bootstrap_from_broker_registry(
    broker_names: Sequence[str],
    *,
    policy: SourceSelectionPolicy | None = None,
    **bootstrap_kwargs: Any,
) -> BrokerInfrastructure | None:
    """Bootstrap infrastructure using cli.services.broker_registry."""
    from cli.services.broker_registry import bootstrap_gateway

    wrapped: list[tuple[str, MarketDataGateway]] = []
    for name in broker_names:
        result = bootstrap_gateway(name, **bootstrap_kwargs)
        if result.ok and result.gateway is not None:
            wrapped.append((name, result.gateway))
    if not wrapped:
        return None
    return await bootstrap_from_gateways(wrapped, policy=policy)
