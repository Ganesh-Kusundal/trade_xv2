"""CLI helper utilities for composer initialization.

Provides functions to bootstrap MarketDataComposer and ExecutionComposer
from CLI commands, ensuring all entry points use the unified multi-broker
architecture.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from application.composer.execution import ExecutionComposer
    from application.composer.market_data import MarketDataComposer

logger = logging.getLogger(__name__)


def _detect_enabled_brokers() -> list[str]:
    """Detect which brokers are enabled via environment configuration.

    Returns list of broker IDs that should be initialized.
    """
    import os

    enabled = []

    # Dhan: requires DHAN_CLIENT_ID or DHAN_ACCESS_TOKEN
    if os.getenv("DHAN_CLIENT_ID") or os.getenv("DHAN_ACCESS_TOKEN"):
        enabled.append("dhan")

    # Paper trading: always available for testing
    enabled.append("paper")

    return enabled


def _create_gateways(broker_ids: list[str] | None = None) -> list[Any]:
    """Create broker gateways for the specified broker IDs.

    Parameters
    ----------
    broker_ids
        List of broker IDs to initialize. If None, auto-detects from env.
    """
    try:
        from interface.ui.services.broker_facade import DhanBrokerGateway
    except ImportError:
        DhanBrokerGateway = None  # noqa: N806

    try:
        from interface.ui.services.broker_facade import PaperBrokerGateway
    except ImportError:
        PaperBrokerGateway = None  # noqa: N806
    if broker_ids is None:
        broker_ids = _detect_enabled_brokers()

    gateways: list[Any] = []

    for broker_id in broker_ids:
        if broker_id == "dhan":
            if DhanBrokerGateway is None:
                logger.warning("DhanBrokerGateway not available")
                continue
            try:
                gateway = DhanBrokerGateway.from_env()
                gateways.append(gateway)
                logger.info("Initialized DhanBrokerGateway")
            except Exception as exc:
                logger.warning("Failed to initialize DhanBrokerGateway: %s", exc)
        elif broker_id == "paper":
            if PaperBrokerGateway is None:
                logger.warning("PaperBrokerGateway not available")
                continue
            gateway = PaperBrokerGateway()
            gateways.append(gateway)
            logger.info("Initialized PaperBrokerGateway")
        else:
            logger.warning("Unknown broker ID: %s", broker_id)

    return gateways


def _create_composer(broker_ids: tuple[str, ...] | None) -> tuple[Any, Any]:
    """Build gateways and create both composers. Returns (market_data, execution)."""
    from application.composer.factory import create_composers
    from application.scheduling.quota_scheduler import QuotaScheduler  # sanctioned — broker wiring layer
    from domain.policies.defaults import default_source_selection_policy  # sanctioned — broker wiring layer

    gateways = _create_gateways(list(broker_ids) if broker_ids else None)

    if not gateways:
        raise RuntimeError(
            "No broker gateways could be initialized. "
            "Set DHAN_CLIENT_ID/DHAN_ACCESS_TOKEN for Dhan, or use paper trading."
        )

    policy = default_source_selection_policy()
    quota_scheduler = QuotaScheduler()

    return create_composers(
        gateways=gateways,
        policy=policy,
        quota_scheduler=quota_scheduler,
    )


@lru_cache(maxsize=1)
def get_market_data_composer(
    broker_ids: tuple[str, ...] | None = None,
) -> MarketDataComposer:
    """Get or create MarketDataComposer instance (cached)."""
    market_data_composer, _ = _create_composer(broker_ids)
    logger.info("MarketDataComposer initialized")
    return market_data_composer


@lru_cache(maxsize=1)
def get_execution_composer(
    broker_ids: tuple[str, ...] | None = None,
) -> ExecutionComposer:
    """Get or create ExecutionComposer instance (cached)."""
    _, execution_composer = _create_composer(broker_ids)
    logger.info("ExecutionComposer initialized")
    return execution_composer


def reset_composer_cache() -> None:
    """Reset the composer cache. FOR TESTING ONLY.

    Clears the LRU cache so tests can isolate their composer instances.
    """
    get_market_data_composer.cache_clear()
    get_execution_composer.cache_clear()
