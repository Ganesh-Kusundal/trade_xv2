"""Order validation logic for the OMS OrderManager.

Extracted from :class:`application.oms.order_manager.OrderManager` god class.
Owns the placement gate, risk-manager consultation, and order-object building
with validation.

Does **not** own idempotency — that lives in
:class:`application.oms.idempotency_guard.IdempotencyGuard`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

from domain.events.types import DomainEvent, EventType
from domain.ports.time_service import ClockPort, get_current_clock
from domain.enums import OrderStatus

if TYPE_CHECKING:
    from application.oms.order_manager import OmsOrderCommand, OrderResult
    from domain.entities import Order
    from domain.ports import EventBusPort

import logging

logger = logging.getLogger(__name__)


class RiskCheckPort(Protocol):
    """Port for pre-trade risk checks. ``RiskManager`` satisfies this protocol."""

    def check_order(self, order: Any) -> Any: ...


class OrderValidator:
    """Gate, risk-check, and order-construction logic for the OMS.

    Thread-safety is the caller's responsibility — this class does not
    hold a lock.
    """

    def __init__(
        self,
        risk_manager: RiskCheckPort | None = None,
        event_bus: EventBusPort | None = None,
        publish_callback: Callable | None = None,
        clock: ClockPort | None = None,
    ) -> None:
        self._risk_manager = risk_manager
        self._event_bus = event_bus
        self._publish_callback = publish_callback
        self._clock = clock or get_current_clock()
        self._placement_gate: Callable[[], tuple[bool, str | None]] | None = None

    def set_placement_gate(self, gate_fn: Callable[[], tuple[bool, str | None]]) -> None:
        """Set a callable that gates order placement.

        The gate function is called before placing an order. If it returns
        ``(False, reason)``, the order is rejected with the given reason.

        Parameters
        ----------
        gate_fn:
            Callable returning (allowed, reason). Example:
            ``lambda: (True, None)`` always allows placement.
        """
        self._placement_gate = gate_fn

    def clear_placement_gate(self) -> None:
        """Remove any active placement gate (orders allowed unless risk blocks)."""
        self._placement_gate = None

    def check_placement_gate(self) -> str | None:
        """Check if order placement is allowed. Returns rejection reason or None."""
        gate_fn = self._placement_gate
        if gate_fn is None:
            return None
        allowed, reason = gate_fn()
        if allowed:
            return None
        return reason or "Order placement blocked by gate"

    def check_order(self, order: Order) -> bool:
        """Return True if the order passes the configured risk checks."""
        if self._risk_manager is None:
            return True
        return self._risk_manager.check_order(order).allowed

    def build_and_validate(
        self,
        order_id: str,
        request: OmsOrderCommand,
    ) -> tuple[Order | None, OrderResult | None]:
        """Build order object, check gate and risk (no lock).

        Returns (order, None) on success, or (None, OrderResult) on rejection.
        """
        from application.oms.order_manager import OrderResult
        from domain.entities import Order

        gate_reason = self.check_placement_gate()
        if gate_reason is not None:
            self._publish(
                EventType.ORDER_REJECTED.value,
                Order(
                    order_id=order_id,
                    symbol=request.symbol,
                    exchange=request.exchange,
                    side=request.side,
                    order_type=request.order_type,
                    quantity=request.quantity,
                    price=request.price,
                    product_type=request.product_type,
                    status=OrderStatus.REJECTED,
                    timestamp=self._clock.now(),
                    correlation_id=request.correlation_id,
                ),
                reason=gate_reason,
            )
            return None, OrderResult(success=False, error=gate_reason)

        order = Order(
            order_id=order_id,
            symbol=request.symbol,
            exchange=request.exchange,
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            price=request.price,
            product_type=request.product_type,
            status=OrderStatus.OPEN,
            timestamp=self._clock.now(),
            correlation_id=request.correlation_id,
        )

        if self._risk_manager is not None:
            risk_result = self._risk_manager.check_order(order)
            if not risk_result.allowed:
                if self._event_bus is not None:
                    self._event_bus.publish(
                        DomainEvent.now(
                            EventType.RISK_REJECTED.value,
                            payload={
                                "order_id": order.order_id,
                                "rule": risk_result.reason,
                                "value": "0",
                                "limit": "0",
                            },
                            symbol=order.symbol,
                            source="OrderManager",
                            correlation_id=order.correlation_id,
                        )
                    )
                self._publish(
                    EventType.ORDER_REJECTED.value,
                    order,
                    reason=risk_result.reason,
                )
                return None, OrderResult(success=False, error=risk_result.reason)
            if self._event_bus is not None:
                self._event_bus.publish(
                    DomainEvent.now(
                        EventType.RISK_APPROVED.value,
                        payload={"order_id": order.order_id},
                        symbol=order.symbol,
                        source="OrderManager",
                        correlation_id=order.correlation_id,
                    )
                )

        return order, None

    def _publish(self, event_type: str, obj: object, *, reason: str | None = None) -> None:
        """Delegate to the publish callback (set by the orchestrator)."""
        if self._publish_callback is not None:
            self._publish_callback(event_type, obj, reason=reason)
