"""Pure reconciliation — no I/O, no bus, no broker imports."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from domain.entities import Account, Order, Position
from domain.enums import DriftSeverity
from domain.value_objects import OrderId


@dataclass(frozen=True, slots=True)
class DriftItem:
    kind: str
    key: str
    severity: DriftSeverity
    reason: str
    local: Any = None
    remote: Any = None


class ReconciliationEngine:
    """Compare local vs broker snapshots → DriftItems. Side-effect free."""

    def compare_orders(
        self,
        local: list[Order],
        broker: list[Order],
        *,
        price_tolerance: Decimal = Decimal("0.01"),
    ) -> list[DriftItem]:
        drifts: list[DriftItem] = []
        local_by = {_order_key(o): o for o in local}
        broker_by = {_order_key(o): o for o in broker}

        for key, bo in broker_by.items():
            lo = local_by.get(key)
            if lo is None:
                drifts.append(
                    DriftItem(
                        kind="order",
                        key=key,
                        severity=DriftSeverity.HIGH,
                        reason="missing local order",
                        local=None,
                        remote=bo,
                    )
                )
                continue
            drifts.extend(self._diff_order(lo, bo, key, price_tolerance))

        for key, lo in local_by.items():
            if key not in broker_by:
                drifts.append(
                    DriftItem(
                        kind="order",
                        key=key,
                        severity=DriftSeverity.HIGH,
                        reason="missing broker order",
                        local=lo,
                        remote=None,
                    )
                )
        return drifts

    def compare_positions(
        self,
        local: list[Position],
        broker: list[Position],
        *,
        price_tolerance: Decimal = Decimal("0.01"),
    ) -> list[DriftItem]:
        drifts: list[DriftItem] = []
        local_by = {p.instrument_id.value: p for p in local}
        broker_by = {p.instrument_id.value: p for p in broker}

        for key, bp in broker_by.items():
            lp = local_by.get(key)
            if lp is None:
                drifts.append(
                    DriftItem(
                        kind="position",
                        key=key,
                        severity=DriftSeverity.HIGH,
                        reason="missing local position",
                        local=None,
                        remote=bp,
                    )
                )
                continue
            if lp.quantity.value != bp.quantity.value:
                drifts.append(
                    DriftItem(
                        kind="position",
                        key=key,
                        severity=DriftSeverity.HIGH,
                        reason="quantity mismatch",
                        local=lp,
                        remote=bp,
                    )
                )
            elif abs(lp.avg_price.value - bp.avg_price.value) > price_tolerance:
                drifts.append(
                    DriftItem(
                        kind="position",
                        key=key,
                        severity=DriftSeverity.MEDIUM,
                        reason="avg_price drift",
                        local=lp,
                        remote=bp,
                    )
                )

        for key, lp in local_by.items():
            if key not in broker_by:
                drifts.append(
                    DriftItem(
                        kind="position",
                        key=key,
                        severity=DriftSeverity.HIGH,
                        reason="missing broker position",
                        local=lp,
                        remote=None,
                    )
                )
        return drifts

    def compare_funds(
        self,
        local: Account,
        broker: Account,
        *,
        money_tolerance: Decimal = Decimal("0.01"),
    ) -> list[DriftItem]:
        drifts: list[DriftItem] = []
        if abs(local.balance.amount - broker.balance.amount) > money_tolerance:
            drifts.append(
                DriftItem(
                    kind="funds",
                    key=local.account_id.value,
                    severity=DriftSeverity.HIGH,
                    reason="balance mismatch",
                    local=local,
                    remote=broker,
                )
            )
        elif abs(local.equity.amount - broker.equity.amount) > money_tolerance:
            drifts.append(
                DriftItem(
                    kind="funds",
                    key=local.account_id.value,
                    severity=DriftSeverity.MEDIUM,
                    reason="equity drift",
                    local=local,
                    remote=broker,
                )
            )
        return drifts

    @staticmethod
    def _diff_order(
        local: Order,
        broker: Order,
        key: str,
        price_tolerance: Decimal,
    ) -> list[DriftItem]:
        out: list[DriftItem] = []
        if local.quantity.value != broker.quantity.value:
            out.append(
                DriftItem(
                    kind="order",
                    key=key,
                    severity=DriftSeverity.HIGH,
                    reason="quantity mismatch",
                    local=local,
                    remote=broker,
                )
            )
            return out
        if local.filled_quantity.value != broker.filled_quantity.value:
            out.append(
                DriftItem(
                    kind="order",
                    key=key,
                    severity=DriftSeverity.HIGH,
                    reason="filled_quantity mismatch",
                    local=local,
                    remote=broker,
                )
            )
            return out
        lp = local.price.value if local.price else None
        bp = broker.price.value if broker.price else None
        if lp is not None and bp is not None and abs(lp - bp) > price_tolerance:
            out.append(
                DriftItem(
                    kind="order",
                    key=key,
                    severity=DriftSeverity.MEDIUM,
                    reason="price drift",
                    local=local,
                    remote=broker,
                )
            )
        elif local.status is not broker.status:
            out.append(
                DriftItem(
                    kind="order",
                    key=key,
                    severity=DriftSeverity.LOW,
                    reason="status lag",
                    local=local,
                    remote=broker,
                )
            )
        return out


def _order_key(order: Order) -> str:
    oid = order.order_id
    return oid.value if isinstance(oid, OrderId) else str(oid)
