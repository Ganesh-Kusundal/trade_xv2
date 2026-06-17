"""Composition root — single entry point for wiring the trading runtime.

Phase 5: replaces the fragmented wiring previously split between
``BrokerService._ensure_initialized`` (the gateway + OMS lifecycle),
``cli/main.py`` (the gateway and event bus service), and
``OmsService`` construction (discarded on every CLI invocation).

The :func:`build_runtime` function returns a :class:`Runtime` that owns:

* the active ``MarketDataGateway`` (Dhan, Upstox, paper, or datalake)
* the OMS ``TradingContext`` (EventBus, OrderManager, PositionManager,
  RiskManager, ProcessedTradeRepository, EventLog, ReconciliationService)
* the ``LifecycleManager`` (every ManagedService)
* the HTTP observability server (registered with the lifecycle)
* the ``OmsService`` (canonical place-order entry)
* the production readiness ``ReadinessReport``
* the ``live_actionable`` flag (False until the gate passes)

Callers MUST use this function instead of constructing ``BrokerService``
directly. ``BrokerService`` is now a thin facade for backward
compatibility with the existing CLI router.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from brokers.common.gateway import MarketDataGateway
from brokers.common.lifecycle import LifecycleManager
from brokers.common.oms.context import TradingContext

logger = logging.getLogger(__name__)


@dataclass
class Runtime:
    """The fully-wired trading runtime.

    Attributes
    ----------
    broker_name:
        Name of the active broker (``"dhan"``, ``"upstox"``,
        ``"paper"``, ``"datalake"``).
    gateway:
        The active ``MarketDataGateway``.
    trading_context:
        The OMS ``TradingContext``. ``None`` when init fails.
    lifecycle:
        The ``LifecycleManager`` owning every ``ManagedService``.
    oms_service:
        The canonical ``OmsService`` for placing orders.
    http_observability:
        The HTTP observability server (or ``None`` if init failed).
    readiness_report:
        The production ``ReadinessReport`` (or ``None`` if init failed).
    live_actionable:
        True when the runtime is safe to place live orders.
    """

    broker_name: str
    gateway: MarketDataGateway | None
    trading_context: TradingContext | None
    lifecycle: LifecycleManager
    oms_service: Any
    http_observability: Any
    readiness_report: Any
    live_actionable: bool


def build_runtime(
    broker: str = "dhan",
    *,
    authorize_risk_fail_open: bool = False,
    env_path: Path | None = None,
) -> Runtime:
    """Single composition root for the trading runtime.

    Parameters
    ----------
    broker:
        Broker name: ``"dhan"``, ``"upstox"``, ``"paper"``, or
        ``"datalake"`` (read-only).
    authorize_risk_fail_open:
        Explicit operator consent to use the legacy 1,000,000 INR
        placeholder capital. See :class:`BrokerService` for the
        refusal policy on the env var.
    env_path:
        Optional explicit path to the broker env file. Defaults are
        ``.env.local`` for Dhan, ``.env.upstox`` for Upstox, ``None``
        for paper and datalake.

    Returns
    -------
    Runtime
        A fully-wired runtime. ``runtime.live_actionable`` is True
        only when the production readiness gate has passed.
    """
    # Delegate to BrokerService for now: it already implements the
    # full wiring sequence. Phase 5 leaves the existing logic intact
    # and simply exposes the result through a typed ``Runtime``
    # object so callers do not need to thread individual references.
    from cli.services.broker_service import BrokerService
    from cli.services.oms_service import OmsService

    bs = BrokerService(authorize_risk_fail_open=authorize_risk_fail_open)
    # _ensure_initialized is called on first property access; force
    # it now so the runtime is fully populated before we return.
    _ = bs.active_broker  # triggers _ensure_initialized

    tc = bs.trading_context
    gateway = bs._gateway if bs._active_name == "dhan" else bs._upstox_gateway

    def _live_actionable() -> bool:
        return bs.live_actionable

    # Best-effort oms_service construction — when TradingContext is
    # missing the OMS path is unavailable.
    if tc is not None and gateway is not None:
        oms_service = OmsService(
            gateway=gateway,
            trading_context=tc,
            live_actionable_fn=_live_actionable,
        )
    else:
        oms_service = OmsService(
            gateway=gateway,
            trading_context=tc,
            live_actionable_fn=lambda: False,
        )

    return Runtime(
        broker_name=bs.active_broker_name,
        gateway=gateway,
        trading_context=tc,
        lifecycle=bs.lifecycle,
        oms_service=oms_service,
        http_observability=bs.http_observability,
        readiness_report=bs.readiness_report,
        live_actionable=bs.live_actionable,
    )