"""Upstox reconciliation: drift detection between local OMS and Upstox state.

Uses shared :class:`domain.reconciliation_engine.ReconciliationEngine` (parity
with Dhan). Broker fetch + repair remain Upstox-specific.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from brokers.common.recon_local import local_orders_as_domain, local_positions_as_domain
from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
from brokers.upstox.market_data.portfolio_client import UpstoxPortfolioClient
from brokers.upstox.orders.order_client import UpstoxRestOrderClient
from domain.reconciliation import DriftItem, ReconciliationReport
from domain.reconciliation_engine import ReconciliationEngine

logger = logging.getLogger(__name__)


def create_reconciliation_service(
    order_client: UpstoxRestOrderClient,
    portfolio_client: UpstoxPortfolioClient,
    oms: Any = None,
    auto_repair: bool = True,
) -> UpstoxReconciliationService:
    """Factory function to create an UpstoxReconciliationService."""
    return UpstoxReconciliationService(
        order_client=order_client,
        portfolio_client=portfolio_client,
        oms=oms,
        auto_repair=auto_repair,
    )


class UpstoxReconciliationService:
    """Compare OMS state to Upstox authoritative state via ReconciliationEngine."""

    def __init__(
        self,
        order_client: UpstoxRestOrderClient,
        portfolio_client: UpstoxPortfolioClient,
        oms: Any = None,
        *,
        auto_repair: bool = True,
    ) -> None:
        self._order_client = order_client
        self._portfolio_client = portfolio_client
        self._oms = oms
        self._auto_repair = auto_repair

    def reconcile(
        self,
        local_orders: list[Any] | None = None,
        local_positions: list[Any] | None = None,
        *,
        on_drift: Callable[[ReconciliationReport], None] | None = None,
    ) -> ReconciliationReport:
        report = ReconciliationReport(timestamp_ms=int(time.time() * 1000))
        drift: list[DriftItem] = []

        try:
            broker_orders = [
                UpstoxDomainMapper.to_order(row)
                for row in self._order_client.get_order_list()
                if isinstance(row, dict)
            ]
            report.broker_orders = len(broker_orders)
        except Exception as exc:
            logger.warning("Reconciliation: could not fetch Upstox orders: %s", exc)
            broker_orders = []
            drift.append(
                DriftItem(
                    kind="fetch_error",
                    severity="HIGH",
                    details=f"Failed to fetch Upstox orders: {exc}",
                )
            )

        try:
            broker_positions = [
                UpstoxDomainMapper.to_position(row)
                for row in self._portfolio_client.get_short_term_positions()
                if isinstance(row, dict)
            ]
            report.broker_positions = len(broker_positions)
        except Exception as exc:
            logger.warning("Reconciliation: could not fetch Upstox positions: %s", exc)
            broker_positions = []
            drift.append(
                DriftItem(
                    kind="fetch_error",
                    severity="HIGH",
                    details=f"Failed to fetch Upstox positions: {exc}",
                )
            )

        if local_orders is None:
            local_orders = self._oms_orders() if self._oms is not None else []
        if local_positions is None:
            local_positions = self._oms_positions() if self._oms is not None else []

        local_order_domain = local_orders_as_domain(local_orders)
        local_position_domain = local_positions_as_domain(local_positions)

        engine = ReconciliationEngine()
        if local_order_domain is not None:
            drift += engine.compare_orders(local_order_domain, broker_orders)
        if local_position_domain is not None:
            drift += engine.compare_positions(local_position_domain, broker_positions)

        report.drift_items = drift
        # I6: Attach actual broker objects so ExecutionEngine.apply_mass_status() can heal
        report.broker_order_list = broker_orders
        report.broker_position_list = broker_positions

        # I6: auto_repair disabled — apply goes through ExecutionEngine, not broker adapter
        orders_repaired = 0
        positions_repaired = 0
        if self._auto_repair:
            for item in drift:
                if item.severity != "HIGH":
                    continue
                if item.kind == "missing_local_order":
                    orders_repaired += self._repair_missing_order(item.payload or {})
                elif item.kind == "position_quantity_mismatch":
                    positions_repaired += self._repair_position_drift(item.payload or {})

        report.orders_repaired = orders_repaired
        report.positions_repaired = positions_repaired

        if on_drift is not None and drift:
            try:
                on_drift(report)
            except (ValueError, KeyError, ConnectionError, TimeoutError) as exc:
                logger.exception("on_drift callback failed: %s", exc)

        return report

    def _oms_orders(self) -> list[Any]:
        if self._oms is None:
            return []
        for name in ("get_orders", "get_all_orders"):
            method = getattr(self._oms, name, None)
            if method is None:
                continue
            try:
                return method()
            except (ValueError, KeyError, ConnectionError, TimeoutError):
                return []
        return []

    def _oms_positions(self) -> list[Any]:
        if self._oms is None:
            return []
        for name in ("get_positions", "get_positions_as_dicts"):
            method = getattr(self._oms, name, None)
            if method is None:
                continue
            try:
                return method()
            except Exception as exc:
                logger.debug("oms_get_positions_failed via %s: %s", name, exc)
        return []

    def _repair_missing_order(self, payload: dict[str, Any]) -> int:
        if self._oms is None:
            return 0
        method = getattr(self._oms, "upsert_order", None)
        if method is None:
            return 0
        try:
            method(payload)
            return 1
        except (ValueError, KeyError, ConnectionError, TimeoutError):
            return 0

    def _repair_position_drift(self, payload: dict[str, Any]) -> int:
        if self._oms is None:
            return 0
        method = getattr(self._oms, "upsert_position", None)
        if method is None:
            return 0
        try:
            broker_pos = payload.get("broker") or payload.get("upstox") or payload
            method(broker_pos)
            return 1
        except (ValueError, KeyError, ConnectionError, TimeoutError):
            return 0
