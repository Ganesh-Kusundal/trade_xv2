"""Advanced order models and adapters for Dhan broker adapter.

Implements advanced order types: Bracket, Slice, and GTT orders.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from brokers.common.api.ports import (
    BracketOrderProvider,
    GttOrderProvider,
    SliceOrderCommand,
)
from brokers.common.core.enums import (
    ExchangeSegment,
    OrderType,
    ProductType,
    TransactionType,
    Validity,
)
from brokers.dhan.orders.orders import DhanRestOrderClient


class BracketOrder(BaseModel):
    """Bracket order with profit target and stop loss.

    A bracket order is a combination of a main order with an attached profit
    target and stop loss to automate partial profit taking and risk management.
    """

    order_id: str = ""
    security_id: str = ""
    exchange_segment: ExchangeSegment = ExchangeSegment.NSE
    transaction_type: TransactionType = TransactionType.BUY
    quantity: int = 0
    price: Decimal = Decimal("0")
    trigger_price: Decimal | None = None
    order_type: OrderType = OrderType.LIMIT
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY

    # Bracket order specific fields
    profit_target: Decimal = Decimal("0")
    stop_loss: Decimal = Decimal("0")
    trailing_jump: Decimal | None = None

    # Status fields
    status: str = ""
    filled_quantity: int = 0
    average_price: Decimal = Decimal("0")
    order_timestamp: datetime | None = None

    # Metadata
    correlation_id: str | None = None
    tag: str | None = None

    def is_valid(self) -> bool:
        """Validate bracket order parameters."""
        if self.quantity <= 0:
            return False
        if self.price <= 0 and self.order_type != OrderType.MARKET:
            return False
        if self.profit_target <= 0:
            return False
        if self.stop_loss <= 0:
            return False
        return not self.profit_target <= self.stop_loss

    def calculate_risk_reward_ratio(self) -> Decimal | None:
        """Calculate risk/reward ratio for the bracket order."""
        if self.price > 0 and self.stop_loss > 0 and self.profit_target > 0:
            risk = abs(self.price - self.stop_loss)
            reward = abs(self.profit_target - self.price)
            if risk > 0:
                return reward / risk
        return None


class SliceOrder(BaseModel):
    """Slice order for splitting large orders into child orders.

    A slice order automatically divides a large order into multiple smaller
    child orders to improve execution and reduce market impact.
    """

    order_id: str = ""
    security_id: str = ""
    exchange_segment: ExchangeSegment = ExchangeSegment.NSE
    transaction_type: TransactionType = TransactionType.BUY
    quantity: int = 0
    price: Decimal = Decimal("0")
    trigger_price: Decimal | None = None
    order_type: OrderType = OrderType.LIMIT
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY

    # Slice order specific fields
    slice_quantity: int | None = None
    slice_count: int | None = None
    slice_interval: int | None = None

    # Child orders
    child_orders: list[dict[str, Any]] = []

    # Status fields
    status: str = ""
    filled_quantity: int = 0
    average_price: Decimal = Decimal("0")
    order_timestamp: datetime | None = None

    # Metadata
    correlation_id: str | None = None
    tag: str | None = None

    def is_valid(self) -> bool:
        """Validate slice order parameters."""
        if self.quantity <= 0:
            return False
        if self.slice_count is not None and self.slice_count <= 0:
            return False
        if self.slice_quantity is not None and self.slice_quantity <= 0:
            return False
        if self.slice_count and self.slice_quantity:
            expected_total = self.slice_quantity * self.slice_count
            if expected_total != self.quantity:
                return False
        return True

    def calculate_slice_details(self) -> dict[str, Any]:
        """Calculate slice order details."""
        if not self.is_valid():
            return {}

        if self.slice_count and self.slice_quantity:
            slice_qty = self.slice_quantity
            remaining = self.quantity
            slices = []
            for i in range(self.slice_count):
                current_slice = min(slice_qty, remaining)
                if current_slice > 0:
                    slices.append(
                        {
                            "slice_number": i + 1,
                            "quantity": current_slice,
                            "price": float(self.price) if self.price > 0 else 0,
                            "trigger_price": float(self.trigger_price)
                            if self.trigger_price
                            else None,
                        }
                    )
                    remaining -= current_slice
                else:
                    break

            return {
                "total_slices": len(slices),
                "slices": slices,
                "total_quantity": sum(s["quantity"] for s in slices),
            }

        return {}


class GttOrder(BaseModel):
    """Good Till Trigger (GTT) order.

    A GTT order is a conditional order that executes when a specified
    price condition is met, remaining active until the condition is triggered
    or the order is cancelled.
    """

    order_id: str = ""
    security_id: str = ""
    exchange_segment: ExchangeSegment = ExchangeSegment.NSE
    transaction_type: TransactionType = TransactionType.BUY
    quantity: int = 0
    price: Decimal = Decimal("0")
    trigger_price: Decimal | None = None
    order_type: OrderType = OrderType.LIMIT
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY

    # GTT order specific fields
    comparison_type: str = "LTP"  # LTP, VWAP, etc.
    operator: str | None = None  # GT, LT, EQ, etc.
    time_frame: str | None = None  # DAY, WEEK, MONTH, etc.
    comparing_value: Decimal | None = None
    indicator_name: str | None = None
    comparing_indicator_name: str | None = None
    frequency: str | None = None
    expiry_date: str | None = None
    user_note: str | None = None

    # Status fields
    status: str = ""
    filled_quantity: int = 0
    average_price: Decimal = Decimal("0")
    order_timestamp: datetime | None = None
    trigger_timestamp: datetime | None = None

    # Metadata
    correlation_id: str | None = None
    tag: str | None = None

    def is_valid(self) -> bool:
        """Validate GTT order parameters."""
        if self.quantity <= 0:
            return False
        if not self.comparison_type:
            return False
        if not self.operator:
            return False
        if self.comparing_value is None:
            return False
        return self.expiry_date

    def is_triggered(self) -> bool:
        """Check if GTT order has been triggered."""
        return self.status.lower() == "triggered"

    def calculate_trigger_price_range(self) -> dict[str, Decimal]:
        """Calculate trigger price range based on comparison type and operator."""
        if not self.comparing_value or not self.operator:
            return {}

        if self.comparison_type == "LTP":
            if self.operator == "GT":
                return {"min": self.comparing_value, "max": Decimal("999999")}
            elif self.operator == "LT":
                return {"min": Decimal("0"), "max": self.comparing_value}
            elif self.operator == "EQ":
                return {"min": self.comparing_value, "max": self.comparing_value}

        return {}


class DhanBracketOrderAdapter(BracketOrderProvider):
    """Adapter for bracket orders.

    Wraps Dhan's bracket order functionality through the REST client.
    """

    def __init__(self, order_client: DhanRestOrderClient, *args: Any) -> None:
        self._order_client = order_client

    def place_super_order(
        self,
        request: Any,
        target_price: Decimal,
        stop_loss_price: Decimal,
        trailing_jump: Decimal,
    ) -> Any:
        """Place a Dhan super/bracket order."""
        return self._order_client.place_super_order(
            request, target_price, stop_loss_price, trailing_jump
        )

    def modify_super_order(
        self,
        order_id: str,
        leg_name: str,
        quantity: int,
        price: Decimal,
        trigger_price: Decimal,
    ) -> Any:
        """Modify a bracket/super order leg."""
        return self._order_client.modify_super_order(
            order_id, leg_name, quantity, price, trigger_price
        )

    def cancel_super_order(self, order_id: str, leg_name: str) -> bool:
        """Cancel a bracket/super order leg."""
        return self._order_client.cancel_super_order(order_id, leg_name)

    def get_super_orders(self) -> list[Any]:
        """Return bracket/super orders."""
        return self._order_client.get_super_orders()


class DhanSliceOrderAdapter(SliceOrderCommand):
    """Adapter for slice orders.

    Wraps Dhan's slice order functionality through the REST client.
    """

    def __init__(self, order_client: DhanRestOrderClient, *args: Any) -> None:
        self._order_client = order_client

    def place_slice_order(self, request: Any) -> list[Any]:
        """Split an order request into executable child orders."""
        return self._order_client.place_slice_order(request)


class DhanGttOrderAdapter(GttOrderProvider):
    """Adapter for GTT (Good Till Trigger) orders.

    Wraps Dhan's GTT order functionality through the REST client.
    """

    def __init__(self, order_client: DhanRestOrderClient, *args: Any) -> None:
        self._order_client = order_client

    def place_forever_order(
        self,
        request: Any,
        order_flag: str,
        quantity2: int | None = None,
        price2: Decimal | None = None,
        trigger_price2: Decimal | None = None,
    ) -> Any:
        """Place a GTT/forever order."""
        return self._order_client.place_forever_order(
            request, order_flag, quantity2, price2, trigger_price2
        )

    def modify_forever_order(
        self,
        order_id: str,
        order_flag: str,
        leg_name: str,
        quantity: int,
        price: Decimal,
        trigger_price: Decimal,
    ) -> Any:
        """Modify a GTT/forever order."""
        return self._order_client.modify_forever_order(
            order_id, order_flag, leg_name, quantity, price, trigger_price
        )

    def cancel_forever_order(self, order_id: str) -> bool:
        """Cancel a GTT/forever order."""
        return self._order_client.cancel_forever_order(order_id)

    def get_forever_orders(self) -> list[Any]:
        """Return GTT/forever orders."""
        return self._order_client.get_forever_orders()
