"""Service for squaring off positions with OMS risk integration.

Routes position closure through the OMS pipeline for risk checks,
idempotency, and event publishing.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from brokers.common.resilience.errors import TradeXV2Error
from domain.events.types import EventType
from domain.symbols import normalize_symbol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SquareOffResult:
    symbol: str
    quantity: int
    side: str
    order_id: str | None = None
    success: bool = True
    error: str | None = None


@dataclass(frozen=True)
class SquareOffSummary:
    status: str
    squared_off: int
    failed: int
    details: list[SquareOffResult] = field(default_factory=list)


class SquareOffService:
    """Squares off positions through the OMS risk pipeline.

    Ensures:
    1. Kill switch check before any order placement
    2. Each order goes through RiskManager.check_order()
    3. Correct product type (not hardcoded INTRADAY)
    4. Aggregate event publishing
    """

    def __init__(
        self,
        order_manager: Any,
        position_manager: Any,
        risk_manager: Any,
        event_bus: Any,
        submit_fn: Any = None,
    ) -> None:
        self._oms = order_manager
        self._positions = position_manager
        self._risk = risk_manager
        self._events = event_bus
        self._submit_fn = submit_fn

    def square_off(self, symbol: str | None = None) -> SquareOffSummary:
        """Square off all or specific positions.

        Args:
            symbol: If provided, only square off this symbol's position.
                   If None, square off all non-zero positions.

        Returns:
            SquareOffSummary with results for each position.
        """
        # Pre-flight: kill switch check
        if self._risk is not None and self._risk.is_kill_switch_active():
            raise SquareOffRejectedError("Kill switch is active — square-off rejected")

        # Get positions
        positions = self._positions.get_positions()
        if symbol:
            positions = [p for p in positions if p.symbol.upper() == normalize_symbol(symbol)]
        else:
            positions = [p for p in positions if p.quantity != 0]

        if not positions:
            return SquareOffSummary(status="no_positions", squared_off=0, failed=0)

        results: list[SquareOffResult] = []
        submit_fn = self._get_submit_fn()

        for pos in positions:
            result = self._close_position(pos, submit_fn)
            results.append(result)

        # Publish aggregate event
        successful = [r for r in results if r.success]
        self._publish_event(
            EventType.ORDER_PLACED,
            {
                "order_type": "square_off",
                "squared_off": len(successful),
                "failed": len(results) - len(successful),
                "symbols": [r.symbol for r in successful],
            },
        )

        return SquareOffSummary(
            status="completed",
            squared_off=len(successful),
            failed=len(results) - len(successful),
            details=results,
        )

    def _close_position(self, pos: Any, submit_fn: Any) -> SquareOffResult:
        """Close a single position through the OMS pipeline."""
        try:
            from decimal import Decimal

            from application.oms.order_manager import OmsOrderCommand
            from domain import OrderType, ProductType, Side

            opposite_side = Side.SELL if pos.quantity > 0 else Side.BUY
            quantity = abs(pos.quantity)

            # Use the position's actual product type, not hardcoded INTRADAY
            product_type = getattr(pos, "product_type", None)
            if product_type is None:
                product_type = ProductType.INTRADAY

            cmd = OmsOrderCommand(
                symbol=pos.symbol,
                exchange=pos.exchange,
                side=opposite_side,
                order_type=OrderType.MARKET,
                product_type=product_type,
                quantity=quantity,
                price=Decimal("0"),
                correlation_id=f"so-{pos.symbol}-{uuid.uuid4().hex[:8]}",
            )

            result = self._oms.place_order(cmd, submit_fn=submit_fn)

            if result.success:
                return SquareOffResult(
                    symbol=pos.symbol,
                    quantity=quantity,
                    side=opposite_side.value,
                    order_id=result.order.order_id if result.order else None,
                    success=True,
                )
            else:
                return SquareOffResult(
                    symbol=pos.symbol,
                    quantity=quantity,
                    side=opposite_side.value,
                    success=False,
                    error=result.error or "OMS rejected order",
                )
        except Exception as exc:
            logger.exception("Failed to square off %s", pos.symbol)
            return SquareOffResult(
                symbol=pos.symbol,
                quantity=abs(pos.quantity),
                side="SELL" if pos.quantity > 0 else "BUY",
                success=False,
                error=str(exc),
            )

    def _get_submit_fn(self) -> Any:
        """Get the broker submit function."""
        return self._submit_fn

    def _publish_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if self._events is None:
            return
        try:
            from infrastructure.event_bus.event_bus import DomainEvent

            event = DomainEvent.now(event_type=event_type, payload=payload)
            self._events.publish(event)
        except Exception:
            logger.exception("Failed to publish event %s", event_type)


class SquareOffRejectedError(TradeXV2Error):
    """Raised when square-off is rejected by risk checks."""
