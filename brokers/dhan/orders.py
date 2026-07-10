"""Backward-compat shim — re-exports from decomposed submodules.

``OrdersAdapter`` now lives in ``brokers.dhan.execution.orders``.
``IdempotencyCache``, ``OrderPlacer``, ``OrderCanceller``, ``OrderValidator``
live in their own root-level modules.
"""
from brokers.dhan.execution.orders import OrdersAdapter  # noqa: F401
from brokers.dhan.order_cancellation import OrderCanceller  # noqa: F401
from brokers.dhan.order_placement import IdempotencyCache, OrderPlacer  # noqa: F401
from brokers.dhan.order_validator import OrderValidator  # noqa: F401
