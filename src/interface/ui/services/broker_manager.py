"""Broker Manager — active broker switching, status queries.

Extracted from BrokerService to reduce complexity and enable independent
testing.  This module handles:

- Active broker resolution with proper error reporting
- Broker switching (dhan, upstox, paper, datalake)
- Status queries (live_actionable, readiness_report, load errors)
- Broker connectivity status collection
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from domain.enums import BrokerId
from domain.errors import BrokerNotReadyError
from domain.ports.bootstrap import BootstrapStatus
from domain.ports.broker_adapter import BrokerAdapter as MarketDataGateway
from interface.ui.services.broker_observability import (
    resolve_active_broker,
)

if TYPE_CHECKING:
    from interface.ui.services.broker_registry import MockBroker, PaperGateway
    from interface.ui.services.broker_service import BrokerService

logger = logging.getLogger(__name__)


class BrokerManager:
    """Manages broker selection, switching, and status queries.

    Every method receives the owning :class:`BrokerService` via the
    constructor so it can read / mutate shared state (active_name,
    gateway references, bootstrap results, etc.).
    """

    def __init__(self, service: BrokerService) -> None:
        self._svc = service

    # ------------------------------------------------------------------
    # Active broker resolution
    # ------------------------------------------------------------------

    def get_active_broker(self) -> MarketDataGateway | PaperGateway | MockBroker:
        """Return the active broker: live Dhan, live Upstox, paper, or mock.

        Raises BrokerNotReadyError when the selected live broker failed
        authenticated bootstrap and no paper/mock fallback is appropriate.
        """
        svc = self._svc
        svc._ensure_initialized()
        # Live selection that failed auth must not silently fall back to mock
        # when operator explicitly selected dhan/upstox after a failed bootstrap.
        if (
            svc._active_name == BrokerId.DHAN
            and svc._gateway is None
            and svc._dhan_bootstrap is not None
            and svc._dhan_bootstrap.status
            in {BootstrapStatus.REAUTH_REQUIRED, BootstrapStatus.FAILED}
        ):
            raise BrokerNotReadyError.from_bootstrap(svc._dhan_bootstrap)
        if (
            svc._active_name == BrokerId.UPSTOX
            and svc._upstox_gateway is None
            and svc._upstox_bootstrap is not None
            and svc._upstox_bootstrap.status
            in {BootstrapStatus.REAUTH_REQUIRED, BootstrapStatus.FAILED}
        ):
            raise BrokerNotReadyError.from_bootstrap(svc._upstox_bootstrap)

        return resolve_active_broker(
            svc._active_name,
            paper=svc._paper,
            oms_proxy=None,
            gateway=svc._gateway,
            upstox_oms_proxy=None,
            upstox_gateway=svc._upstox_gateway,
            mock=svc._mock,
            dhan_load_error=svc._dhan_load_error,
            upstox_load_error=svc._upstox_load_error,
            dhan_bootstrap=svc._dhan_bootstrap,
            upstox_bootstrap=svc._upstox_bootstrap,
        )

    def get_active_broker_name(self) -> str:
        return self._svc._active_name

    def is_live_dhan_active(self) -> bool:
        """``True`` when a real ``BrokerGateway`` is connected (not mock)."""
        self._svc._ensure_initialized()
        return self._svc._gateway is not None

    def is_live_actionable(self) -> bool:
        """``True`` when the runtime is safe to place live orders.

        The runtime is ``live_actionable`` only when:

        * The Dhan gateway was constructed without error, AND
        * The OMS services (reconciliation, event log) are wired, AND
        * Both WebSocket services (market feed + order stream) are
          registered with the LifecycleManager, AND
        * The HTTP observability server is running, AND
        * The risk manager has a real capital source (no phantom fallback
          unless ``--risk-fail-open`` was set explicitly), AND
        * All required credentials are present.

        When this property is ``False`` the CLI may still run read-only
        diagnostic commands (``quote``, ``depth``, ``historical``,
        ``instruments``, ``broker list``, ``doctor``) but every
        ``BrokerService.place_order`` call refuses with a structured error.
        """
        self._svc._ensure_initialized()
        return self._svc._live_actionable

    def get_readiness_report(self):
        """The most recent :class:`ReadinessReport` from the production
        readiness gate, or ``None`` if init has not run yet."""
        self._svc._ensure_initialized()
        return self._svc._readiness_report

    def get_dhan_load_error(self) -> str | None:
        return self._svc._dhan_load_error

    # ------------------------------------------------------------------
    # Broker switching
    # ------------------------------------------------------------------

    def set_active_broker(self, name: str) -> None:
        svc = self._svc
        svc._ensure_initialized()
        name_lower = name.lower()

        # M4: Forbid cross-broker switch when OMS submit_fn is wired to a different broker.
        if name_lower not in (BrokerId.PAPER, BrokerId.DATALAKE) and svc._active_name != name_lower:
            oms_broker = getattr(svc, "_oms_broker_id", None)
            if oms_broker is not None and oms_broker != name_lower:
                raise ValueError(
                    f"Cannot switch to '{name_lower}': OMS submit_fn is wired to '{oms_broker}'. "
                    f"Rebuild TradingContext for {name_lower} first."
                )

        if name_lower == BrokerId.PAPER:
            if svc._paper is None:
                from interface.ui.services.broker_registry import get_paper_gateway_class
                PaperGateway = get_paper_gateway_class()
                svc._paper = PaperGateway()
            svc._active_name = BrokerId.PAPER
        elif name_lower == BrokerId.DHAN:
            if svc._gateway is None:
                raise ValueError("Dhan broker not available. Check .env.local credentials.")
            svc._active_name = BrokerId.DHAN
        elif name_lower == BrokerId.UPSTOX:
            if svc._upstox_gateway is None:
                raise ValueError("Upstox broker not available. Check .env.upstox credentials.")
            svc._active_name = BrokerId.UPSTOX
        elif name_lower == BrokerId.DATALAKE:
            # Phase 6: read-only datalake gateway. Created lazily so
            # operators can switch between live and historical data
            # without restarting the CLI.
            from interface.ui.services.connect import connect_analytics

            result = connect_analytics(BrokerId.DATALAKE, load_instruments=False)
            svc._paper = result.gateway if result.ok else None
            if svc._paper is None:
                raise ValueError(
                    "DataLake gateway not available. Verify the 'market_data' directory exists."
                )
            svc._active_name = BrokerId.DATALAKE
        else:
            raise ValueError(
                f"Broker '{name}' is not registered. Use 'dhan', 'upstox', 'paper', or 'datalake'."
            )
        svc._active_name = name_lower

    def use_paper(self) -> None:
        """Switch to paper trading mode."""
        self.set_active_broker(BrokerId.PAPER)

    def get_broker_statuses(self) -> list[dict[str, str]]:
        self._svc._ensure_initialized()
        svc = self._svc
        statuses = []
        if svc._gateway is not None:
            statuses.append({"broker": "Dhan", "status": "Connected"})
        else:
            statuses.append({"broker": "Dhan", "status": "Unavailable"})
        if svc._upstox_gateway is not None:
            statuses.append({"broker": "Upstox", "status": "Connected"})
        else:
            statuses.append({"broker": "Upstox", "status": "Unavailable"})
        statuses.append({"broker": "Paper", "status": "Available"})
        # Phase 6: read-only datalake gateway. Marked as Available
        # when the local Parquet directory exists, otherwise the
        # operator gets a hint to bootstrap it.
        from pathlib import Path as _Path
        datalake_status = (
            "Available" if _Path("market_data").exists() else "Directory not found"
        )
        statuses.append({"broker": "DataLake (read-only)", "status": datalake_status})
        return statuses
