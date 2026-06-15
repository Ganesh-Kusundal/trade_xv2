"""Dhan reconciliation — drift detection between local OMS and Dhan broker state."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from brokers.dhan.orders import OrdersAdapter
from brokers.dhan.portfolio import PortfolioAdapter

logger = logging.getLogger(__name__)


def create_reconciliation_service(
    orders_adapter: OrdersAdapter,
    portfolio_adapter: PortfolioAdapter,
    oms: Any = None,
    auto_repair: bool = False,
) -> DhanReconciliationService:
    """Factory that creates a DhanReconciliationService with the right wiring.

    Args:
        orders_adapter: Adapter for fetching broker order state.
        portfolio_adapter: Adapter for fetching broker position state.
        oms: Optional OMS (OrderManager) for auto-repair of local state.
        auto_repair: When True and oms is provided, repair local state from broker.

    Returns:
        A configured DhanReconciliationService instance.
    """
    return DhanReconciliationService(
        orders=orders_adapter,
        portfolio=portfolio_adapter,
        oms=oms,
        auto_repair=auto_repair,
    )


@dataclass
class DriftItem:
    kind: str  # "order_status", "missing_position", "extra_position", "quantity_mismatch"
    severity: str  # "HIGH", "MEDIUM", "LOW"
    symbol: str = ""
    details: str = ""


@dataclass
class ReconciliationReport:
    drift_items: list[DriftItem] = field(default_factory=list)
    broker_orders: int = 0
    broker_positions: int = 0
    timestamp_ms: int = 0

    @property
    def has_drift(self) -> bool:
        return len(self.drift_items) > 0

    @property
    def high_severity_count(self) -> int:
        return sum(1 for d in self.drift_items if d.severity == "HIGH")


class DhanReconciliationService:
    """Detects drift between local OMS state and Dhan broker state.

    When ``auto_repair=True`` and an ``oms`` object is provided, the service
    will also repair local state by upserting missing/mismatched orders and
    positions from broker state.

    Usage::

        recon = DhanReconciliationService(orders, portfolio, oms=order_manager)
        report = recon.reconcile()
        if report.has_drift:
            for item in report.drift_items:
                print(f"{item.severity}: {item.kind} — {item.symbol}: {item.details}")
    """

    def __init__(
        self,
        orders: OrdersAdapter,
        portfolio: PortfolioAdapter,
        oms: Any = None,
        *,
        auto_repair: bool = False,
    ):
        self._orders = orders
        self._portfolio = portfolio
        self._oms = oms
        self._auto_repair = auto_repair

    def reconcile(
        self,
        local_orders: list[Any] | None = None,
        local_positions: list[Any] | None = None,
    ) -> ReconciliationReport:
        """Run reconciliation and return a drift report.

        Args:
            local_orders: Optional list of local OMS orders to compare against broker.
            local_positions: Optional list of local positions to compare against broker.
        """
        report = ReconciliationReport(timestamp_ms=int(time.time() * 1000))
        drift: list[DriftItem] = []

        # 1. Fetch broker state
        try:
            broker_orders = self._orders.get_orderbook()
            report.broker_orders = len(broker_orders)
        except Exception as exc:
            logger.error("reconciliation_orders_failed: %s", exc)
            broker_orders = []
            drift.append(DriftItem(
                kind="fetch_error",
                severity="HIGH",
                details=f"Failed to fetch broker orders: {exc}",
            ))

        try:
            broker_positions = self._portfolio.get_positions()
            report.broker_positions = len(broker_positions)
        except Exception as exc:
            logger.error("reconciliation_positions_failed: %s", exc)
            broker_positions = []
            drift.append(DriftItem(
                kind="fetch_error",
                severity="HIGH",
                details=f"Failed to fetch broker positions: {exc}",
            ))

        # 2. Compare orders if local state provided
        if local_orders is not None:
            broker_order_map = {o.order_id: o for o in broker_orders if o.order_id}
            for local in local_orders:
                local_id = getattr(local, "order_id", None)
                if not local_id:
                    continue
                broker_order = broker_order_map.get(local_id)
                if broker_order is None:
                    # Local order not found on broker
                    local_status = getattr(local, "status", None)
                    if local_status and not getattr(local_status, "is_terminal", False):
                        drift.append(DriftItem(
                            kind="missing_order",
                            severity="HIGH",
                            symbol=getattr(local, "symbol", ""),
                            details=f"Local order {local_id} not found on broker",
                        ))
                else:
                    # Compare statuses
                    local_status = getattr(local, "status", None)
                    broker_status = broker_order.status
                    if local_status and str(local_status) != str(broker_status):
                        drift.append(DriftItem(
                            kind="order_status_mismatch",
                            severity="MEDIUM",
                            symbol=getattr(local, "symbol", ""),
                            details=f"Local={local_status}, Broker={broker_status} for {local_id}",
                        ))

        # 3. Compare positions if local state provided
        if local_positions is not None:
            broker_pos_map = {p.symbol: p for p in broker_positions}
            for local in local_positions:
                sym = getattr(local, "symbol", "")
                if not sym:
                    continue
                broker_pos = broker_pos_map.get(sym)
                local_qty = getattr(local, "quantity", 0)
                if broker_pos is None and local_qty != 0:
                    drift.append(DriftItem(
                        kind="missing_position",
                        severity="HIGH",
                        symbol=sym,
                        details=f"Local has qty={local_qty}, broker has no position",
                    ))
                elif broker_pos is not None:
                    broker_qty = broker_pos.quantity
                    if local_qty != broker_qty:
                        drift.append(DriftItem(
                            kind="quantity_mismatch",
                            severity="HIGH",
                            symbol=sym,
                            details=f"Local qty={local_qty}, Broker qty={broker_qty}",
                        ))

        report.drift_items = drift

        # 4. Repair local OMS if auto_repair is enabled
        if self._auto_repair and self._oms is not None:
            self._repair_local_oms(broker_orders, broker_positions, drift)

        logger.info("reconciliation_complete", extra={
            "drift_count": len(drift),
            "high_severity": report.high_severity_count,
            "broker_orders": report.broker_orders,
            "broker_positions": report.broker_positions,
        })
        return report

    def _repair_local_oms(
        self,
        broker_orders: list[Any],
        broker_positions: list[Any],
        drift: list[DriftItem],
    ) -> None:
        """Repair local OMS state from broker state."""
        # Upsert missing orders
        upsert_order = getattr(self._oms, "upsert_order", None)
        if upsert_order is not None:
            for broker_order in broker_orders:
                local_order = getattr(self._oms, "get_order", lambda oid: None)(broker_order.order_id)
                if local_order is None:
                    try:
                        upsert_order(broker_order)
                        logger.info("Repaired missing order %s", broker_order.order_id)
                    except Exception as exc:
                        logger.warning("Failed to repair order %s: %s", broker_order.order_id, exc)

        # Upsert positions from broker
        upsert_position = getattr(self._oms, "upsert_position", None)
        if upsert_position is not None:
            for broker_pos in broker_positions:
                try:
                    upsert_position({
                        "symbol": broker_pos.symbol,
                        "exchange": getattr(broker_pos, "exchange", "NSE"),
                        "quantity": broker_pos.quantity,
                        "avg_price": str(getattr(broker_pos, "avg_price", "0")),
                        "ltp": str(getattr(broker_pos, "ltp", "0")),
                    })
                    logger.info("Repaired position %s", broker_pos.symbol)
                except Exception as exc:
                    logger.warning("Failed to repair position %s: %s", broker_pos.symbol, exc)
