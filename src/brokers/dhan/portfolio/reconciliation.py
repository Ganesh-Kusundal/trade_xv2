"""Dhan reconciliation — drift detection between local OMS and Dhan broker state.

Delegates order/position comparison to the shared domain
``ReconciliationEngine`` so broker-specific services only handle
fetch + repair logic.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from brokers.dhan.execution.orders import OrdersAdapter
from brokers.dhan.portfolio.portfolio import PortfolioAdapter
from domain import DriftItem, ReconciliationReport
from domain.reconciliation_engine import ReconciliationEngine

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

        Order/position comparison is delegated to the shared
        :class:`ReconciliationEngine`. This method handles broker-specific
        fetch + repair logic.

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
            drift.append(
                DriftItem(
                    kind="fetch_error",
                    severity="HIGH",
                    details=f"Failed to fetch broker orders: {exc}",
                )
            )

        try:
            broker_positions = self._portfolio.get_positions()
            report.broker_positions = len(broker_positions)
        except Exception as exc:
            logger.error("reconciliation_positions_failed: %s", exc)
            broker_positions = []
            drift.append(
                DriftItem(
                    kind="fetch_error",
                    severity="HIGH",
                    details=f"Failed to fetch broker positions: {exc}",
                )
            )

        # 2. Compare using shared engine
        engine = ReconciliationEngine()
        if local_orders is not None:
            drift += engine.compare_orders(local_orders, broker_orders)
        if local_positions is not None:
            drift += engine.compare_positions(local_positions, broker_positions)

        # 2b. Funds mismatch when both local cache and broker balance are known.
        # Local available may be provided by callers via portfolio adapter later;
        # today we only attach funds drift when an explicit local value is set on
        # the service (composition roots can set ``_local_available_balance_fn``).
        local_fn = getattr(self, "_local_available_balance_fn", None)
        local_funds = local_fn() if callable(local_fn) else None
        broker_funds = self._fetch_broker_available_balance()
        if broker_funds is not None and local_funds is not None:
            drift += engine.compare_funds(local_funds, broker_funds)

        report.drift_items = drift

        # 3. Correct-then-heal (policy-gated): broker is authoritative for local OMS
        if self._auto_repair and self._oms is not None:
            repaired_o, repaired_p = self._repair_local_oms(
                broker_orders, broker_positions, drift
            )
            report.orders_repaired = repaired_o
            report.positions_repaired = repaired_p

        logger.info(
            "reconciliation_complete",
            extra={
                "drift_count": len(drift),
                "high_severity": report.high_severity_count,
                "broker_orders": report.broker_orders,
                "broker_positions": report.broker_positions,
                "auto_repair": self._auto_repair,
                "orders_repaired": report.orders_repaired,
                "positions_repaired": report.positions_repaired,
            },
        )
        return report

    def _fetch_broker_available_balance(self) -> Any | None:
        """Best-effort funds snapshot for funds_mismatch drift."""
        portfolio = self._portfolio
        for name in ("get_balance", "funds", "get_funds"):
            fn = getattr(portfolio, name, None)
            if not callable(fn):
                continue
            try:
                bal = fn()
            except Exception as exc:
                logger.debug("reconciliation_funds_fetch_failed via %s: %s", name, exc)
                continue
            if bal is None:
                continue
            for attr in ("available_balance", "available", "withdrawable_balance"):
                if hasattr(bal, attr):
                    return getattr(bal, attr)
            if isinstance(bal, (int, float, str)):
                return bal
        return None

    def _repair_local_oms(
        self,
        broker_orders: list[Any],
        broker_positions: list[Any],
        drift: list[DriftItem],
    ) -> tuple[int, int]:
        """Repair local OMS from broker using drift items only (not full snapshot).

        Broker is authoritative. Only mutates local OMS for items that
        actually drifted — never applies the full broker snapshot which
        could turn transient broker inconsistencies into permanent local
        truth.
        """
        orders_repaired = 0
        positions_repaired = 0

        # Build lookup from broker orders/positions for selective repair.
        # Keys are canonicalised with the same domain normalisers the OMS
        # uses, so a broker Position carrying a raw/missing exchange string
        # still matches a drift item instead of being silently dropped.
        from domain.symbols import normalize_exchange, normalize_symbol

        broker_orders_by_id = {o.order_id: o for o in broker_orders if hasattr(o, "order_id")}
        broker_positions_by_key = {
            (normalize_exchange(getattr(p, "exchange", "NSE")), normalize_symbol(p.symbol)): p
            for p in broker_positions
            if hasattr(p, "symbol")
        }

        def _pos_key(exchange: str, symbol: str) -> tuple[str, str]:
            return (normalize_exchange(exchange), normalize_symbol(symbol))

        upsert_order = getattr(self._oms, "upsert_order", None)
        upsert_position = getattr(self._oms, "upsert_position", None)
        if upsert_position is None:
            pm = getattr(self._oms, "position_manager", None) or getattr(
                self._oms, "_position_manager", None
            )
            upsert_position = getattr(pm, "upsert_position", None) if pm else None

        for item in drift:
            if item.kind in ("missing_local_order", "order_status_mismatch", "fill_quantity_mismatch", "avg_price_mismatch"):
                order_id = getattr(item, "payload", {}).get("order_id") or getattr(item, "details", "")
                # Extract order_id from details if not in payload
                if not order_id or order_id.startswith("Broker"):
                    continue
                broker_order = broker_orders_by_id.get(order_id)
                if broker_order is not None and upsert_order is not None:
                    try:
                        upsert_order(broker_order)
                        orders_repaired += 1
                        logger.info("Repaired drift item %s for order %s", item.kind, order_id)
                    except Exception as exc:
                        logger.warning("Failed to repair order %s: %s", order_id, exc)

            elif item.kind in ("missing_local_position", "position_quantity_mismatch", "position_avg_price_mismatch"):
                symbol = item.symbol
                exchange = getattr(item, "payload", {}).get("exchange", "NSE")
                key = _pos_key(exchange, symbol)
                broker_pos = broker_positions_by_key.get(key)
                if broker_pos is None:
                    # No matching broker position — previously a silent drop.
                    # Surface it so persisted drift does not go unnoticed.
                    logger.warning(
                        "reconciliation_repair_miss kind=%s key=%s", item.kind, key
                    )
                    continue
                if upsert_position is not None:
                    try:
                        upsert_position(
                            {
                                "symbol": broker_pos.symbol,
                                "exchange": getattr(broker_pos, "exchange", "NSE"),
                                "quantity": broker_pos.quantity,
                                "avg_price": str(getattr(broker_pos, "avg_price", "0")),
                                "ltp": str(getattr(broker_pos, "ltp", "0")),
                            }
                        )
                        positions_repaired += 1
                        logger.info("Repaired drift item %s for position %s", item.kind, symbol)
                    except Exception as exc:
                        logger.warning("Failed to repair position %s: %s", symbol, exc)

        return orders_repaired, positions_repaired
