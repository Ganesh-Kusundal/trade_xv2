from enum import Enum


class OrderStatus(Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


class Order:
    def __init__(self, order_id: str, quantity: int, price: float):
        self.order_id = order_id
        self.quantity = quantity
        self.price = price
        self.filled_qty = 0
        self.status = OrderStatus.PENDING

    @property
    def remaining_qty(self) -> int:
        return self.quantity - self.filled_qty


class OrderManager:
    """Mock Order Management System for isolation testing."""

    def __init__(self):
        self.orders: dict[str, Order] = {}

    def create_order(self, order_id: str, quantity: int, price: float) -> Order:
        order = Order(order_id, quantity, price)
        self.orders[order_id] = order
        return order

    def open_order(self, order_id: str) -> None:
        order = self.orders[order_id]
        if order.status == OrderStatus.PENDING:
            order.status = OrderStatus.OPEN

    def process_fill(self, order_id: str, fill_qty: int) -> None:
        order = self.orders[order_id]
        if order.status in [OrderStatus.CANCELLED, OrderStatus.FILLED]:
            raise ValueError("Cannot fill completed or cancelled order")

        order.filled_qty += fill_qty

        if order.filled_qty >= order.quantity:
            order.status = OrderStatus.FILLED
        else:
            order.status = OrderStatus.PARTIALLY_FILLED

    def cancel_order(self, order_id: str) -> bool:
        order = self.orders[order_id]
        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED]:
            return False  # Cannot cancel completed or already cancelled order
        order.status = OrderStatus.CANCELLED
        return True

    def modify_order(self, order_id: str, new_qty: int) -> bool:
        order = self.orders[order_id]
        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED]:
            return False
        if new_qty < order.filled_qty:
            return False  # Cannot modify quantity to be less than what is already filled
        order.quantity = new_qty
        return True


# ── Tests ──────────────────────────────────────────────────────────────────


def test_order_lifecycle_transitions():
    oms = OrderManager()
    order = oms.create_order("ORD1", 100, 2500.0)
    assert order.status == OrderStatus.PENDING
    assert order.filled_qty == 0

    # 1. Transition PENDING -> OPEN
    oms.open_order("ORD1")
    assert order.status == OrderStatus.OPEN

    # 2. Transition OPEN -> PARTIALLY_FILLED
    oms.process_fill("ORD1", 40)
    assert order.status == OrderStatus.PARTIALLY_FILLED
    assert order.filled_qty == 40
    assert order.remaining_qty == 60

    # 3. Transition PARTIALLY_FILLED -> FILLED
    oms.process_fill("ORD1", 60)
    assert order.status == OrderStatus.FILLED
    assert order.filled_qty == 100
    assert order.remaining_qty == 0


def test_cancel_order_rules():
    oms = OrderManager()
    order1 = oms.create_order("ORD1", 10, 150.0)
    order2 = oms.create_order("ORD2", 10, 150.0)

    # Can cancel pending/open orders
    assert oms.cancel_order("ORD1") is True
    assert order1.status == OrderStatus.CANCELLED

    # Cannot cancel filled orders
    oms.open_order("ORD2")
    oms.process_fill("ORD2", 10)
    assert oms.cancel_order("ORD2") is False
    assert order2.status == OrderStatus.FILLED


def test_modify_order_rules():
    oms = OrderManager()
    order = oms.create_order("ORD1", 50, 100.0)
    oms.open_order("ORD1")

    # Can modify quantity of open order
    assert oms.modify_order("ORD1", 80) is True
    assert order.quantity == 80

    # Cannot modify quantity to be less than filled quantity
    oms.process_fill("ORD1", 30)
    assert oms.modify_order("ORD1", 20) is False
    assert order.quantity == 80
