"""Broker Observability — health reporting and status collection.

Extracted from BrokerService to separate observability concerns from
broker lifecycle management.

This module handles:
- Broker connectivity status collection
- Health/readiness property computation (live_actionable, authenticated)
- Active broker resolution with proper error reporting
"""

from __future__ import annotations

import logging
from typing import Any

from domain.enums import BrokerId
from domain.errors import BrokerNotReadyError
from domain.ports.bootstrap import BootstrapStatus

logger = logging.getLogger(__name__)


def collect_broker_statuses(
    gateway: Any | None,
    upstox_gateway: Any | None,
) -> list[dict[str, str]]:
    """Collect connectivity status for all known brokers.

    Returns a list of dicts with 'broker' and 'status' keys, suitable
    for display in the ``broker status`` CLI command.

    Args:
        gateway: Dhan MarketDataGateway (or None if unavailable).
        upstox_gateway: Upstox MarketDataGateway (or None if unavailable).
    """
    statuses: list[dict[str, str]] = []
    statuses.append({
        "broker": "Dhan",
        "status": "Connected" if gateway is not None else "Unavailable",
    })
    statuses.append({
        "broker": "Upstox",
        "status": "Connected" if upstox_gateway is not None else "Unavailable",
    })
    statuses.append({"broker": "Paper", "status": "Available"})
    return statuses


def resolve_active_broker(
    active_name: str,
    *,
    paper: Any | None,
    oms_proxy: Any | None,
    gateway: Any | None,
    upstox_oms_proxy: Any | None,
    upstox_gateway: Any | None,
    mock: Any | None,
    dhan_load_error: str | None,
    upstox_load_error: str | None,
    dhan_bootstrap: Any | None,
    upstox_bootstrap: Any | None,
) -> Any:
    """Resolve the active broker gateway based on current selection.

    Priority order:
    1. Active name match (paper / upstox / dhan) — prefers OMS proxy
       over raw gateway when available (B4 kill-switch enforcement).
    2. Fallback to paper, then mock.
    3. Raise ``BrokerNotReadyError`` if nothing is available.

    Args:
        active_name: Currently selected broker name.
        paper: PaperGateway instance (or None).
        oms_proxy: Dhan OMSGatewayProxy (or None).
        gateway: Dhan MarketDataGateway (or None).
        upstox_oms_proxy: Upstox OMSGatewayProxy (or None).
        upstox_gateway: Upstox MarketDataGateway (or None).
        mock: MockBroker instance (or None).
        dhan_load_error: Dhan error message (or None).
        upstox_load_error: Upstox error message (or None).
        dhan_bootstrap: Dhan BootstrapResult (or None).
        upstox_bootstrap: Upstox BootstrapResult (or None).

    Returns:
        The active broker gateway (may be OMSGatewayProxy).

    Raises:
        BrokerNotReadyError: If no broker is available.
    """
    if active_name == BrokerId.PAPER and paper is not None:
        return paper
    if active_name == BrokerId.UPSTOX:
        if upstox_oms_proxy is not None:
            return upstox_oms_proxy
        if upstox_gateway is not None:
            return upstox_gateway
    if active_name == BrokerId.DHAN:
        if oms_proxy is not None:
            return oms_proxy
        if gateway is not None:
            return gateway
    # Fallback chain
    if paper is not None:
        return paper
    if mock is not None:
        return mock
    # Nothing available — raise with diagnostic context
    error = dhan_load_error or upstox_load_error
    bootstrap = dhan_bootstrap if active_name == BrokerId.DHAN else upstox_bootstrap
    status = bootstrap.status if bootstrap is not None else None
    raise BrokerNotReadyError(
        error or f"No broker available for active selection '{active_name}'",
        broker=active_name,
        status=status or BootstrapStatus.FAILED,
        bootstrap=bootstrap,
    )


def compute_live_actionable(
    live_intent: bool,
    gateway: Any | None,
    dhan_load_error: str | None,
    dhan_bootstrap: Any | None,
    readiness_report: Any | None,
) -> bool:
    """Compute whether the live Dhan gateway is actionable.

    ``True`` only when ALL of:
    - Live intent was detected (``.env.local`` existed at init).
    - Gateway was created successfully.
    - No load error occurred.
    - Bootstrap passed authenticated readiness.
    - Production readiness check passed (if one was run).

    Args:
        live_intent: Whether ``.env.local`` existed at init time.
        gateway: Dhan MarketDataGateway (or None).
        dhan_load_error: Error message from Dhan init (or None).
        dhan_bootstrap: Dhan BootstrapResult (or None).
        readiness_report: ProductionReadinessChecker report (or None).
    """
    if not live_intent:
        return False
    if gateway is None:
        return False
    if dhan_load_error:
        return False
    if dhan_bootstrap is None or not getattr(dhan_bootstrap, "live_ready", False):
        return False
    return not (readiness_report is not None and not getattr(readiness_report, "passed", True))


def compute_upstox_authenticated(upstox_bootstrap: Any | None) -> bool:
    """Compute whether Upstox passed authenticated readiness.

    Args:
        upstox_bootstrap: Upstox BootstrapResult (or None).
    """
    return upstox_bootstrap is not None and getattr(upstox_bootstrap, "live_ready", False)
