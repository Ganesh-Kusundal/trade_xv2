"""Broker Lifecycle — infrastructure bootstrap and gateway shutdown.

Extracted from BrokerService to separate lifecycle management from
broker initialization and OMS wiring.

This module handles:
- Federated BrokerInfrastructure bootstrap from available gateways
- Graceful shutdown of all gateway connections
- Mock broker creation for offline/dev mode
"""

from __future__ import annotations

import logging
from typing import Any

from domain.ports.broker_adapter import BrokerAdapter as MarketDataGateway
from runtime.broker_infrastructure import BrokerInfrastructure
from infrastructure.io.async_compat import run_async_compat
from infrastructure.pool.connection_pool import get_connection_pool

# TODO: restore bootstrap import when bootstrap module is recreated
# from infrastructure.bootstrap import bootstrap_from_gateways, policy_from_env

logger = logging.getLogger(__name__)


def build_broker_infrastructure(
    gateway: Any | None,
    upstox_gateway: Any | None,
    paper: Any | None,
) -> BrokerInfrastructure | None:
    """Bootstrap BrokerInfrastructure from available live gateways.

    Collects all live gateways (Dhan, Upstox, Paper) and bootstraps
    the federated BrokerInfrastructure for unified routing, quota
    management, historical data, and stream orchestration.

    Args:
        gateway: Dhan MarketDataGateway (or None).
        upstox_gateway: Upstox MarketDataGateway (or None).
        paper: PaperGateway (or None).

    Returns:
        BrokerInfrastructure if bootstrap succeeded, None otherwise.
    """
    gateways: list[tuple[str, MarketDataGateway]] = []
    if gateway is not None:
        gateways.append(("dhan", gateway))
    if upstox_gateway is not None:
        gateways.append(("upstox", upstox_gateway))
    if paper is not None:
        gateways.append(("paper", paper))
    if not gateways:
        return None
    # TODO: restore bootstrap logic when bootstrap module is recreated.
    # For now this returns None to avoid import errors on the deleted module.
    logger.warning(
        "BrokerInfrastructure bootstrap skipped — bootstrap module removed",
        extra={"brokers": [bid for bid, _ in gateways]},
    )
    return None


def close_all_gateways(
    broker_infra: Any | None,
    gateway: Any | None,
    upstox_gateway: Any | None,
) -> None:
    """Gracefully shut down all gateway connections and pools.

    Shutdown order:
    1. BrokerInfrastructure stream orchestrator (async stop).
    2. Dhan gateway (HTTP session + broker resources).
    3. Upstox gateway (HTTP session + broker resources).
    4. Global connection pool (release all HTTP pools).

    Each step is best-effort: failures are logged and swallowed so
    the CLI always exits cleanly.

    Args:
        broker_infra: BrokerInfrastructure (or None).
        gateway: Dhan MarketDataGateway (or None).
        upstox_gateway: Upstox MarketDataGateway (or None).
    """
    # Drain federated broker infrastructure (stream orchestrator).
    if broker_infra is not None:
        try:
            run_async_compat(
                broker_infra.streams.stop(),
                fire_and_forget=False,
            )
        except Exception as exc:
            logger.debug("broker_infra_stop_failed: %s", exc)
    # Close Dhan gateway
    if gateway is not None:
        try:
            gateway.close()
        except Exception as exc:
            logger.debug("gateway_close_failed: %s", exc)
    # Close Upstox gateway
    if upstox_gateway is not None:
        try:
            upstox_gateway.close()
        except Exception as exc:
            logger.debug("upstox_gateway_close_failed: %s", exc)
    # Close connection pool to release all HTTP connection pools
    try:
        from interface.ui.services.broker_facade import AccountConnectionRegistry

        AccountConnectionRegistry.release_all()
    except Exception as exc:
        logger.debug("account_registry_release_failed: %s", exc)
    try:
        pool = get_connection_pool()
        pool.close_all()
    except Exception as exc:
        logger.debug("connection_pool_close_failed: %s", exc)


def maybe_create_mock_broker(name: str) -> Any | None:
    """Create a seeded mock broker for offline/dev mode.

    Only creates a mock when the broker name is 'dhan' (the default
    offline fallback). Returns None for other broker names.

    Args:
        name: Broker name (typically 'dhan' for mock fallback).

    Returns:
        Seeded MockBroker instance, or None.
    """
    if name == "dhan":
        from interface.ui.services.broker_facade import create_demo_broker
        return create_demo_broker("dhan")
    return None
