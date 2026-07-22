"""FillSource implementations — Simulated / Paper / Broker / Replay.

Only the fill venue differs; ExecutionEngine code path is identical across modes.
"""

from __future__ import annotations

from typing import Any, Mapping
from uuid import uuid4

from domain.commands import PlaceOrderCommand
from domain.entities import Order
from domain.enums import OrderStatus
from domain.value_objects import CorrelationId, OrderId, Price


def _filled_from_command(
    command: PlaceOrderCommand,
    *,
    order_id: OrderId | None = None,
    fill_price: Price | None = None,
) -> Order:
    """Build a FILLED order at command price (or explicit fill_price)."""
    price = fill_price if fill_price is not None else command.price
    if price is None:
        raise ValueError("fill requires a price (LIMIT) or explicit fill_price")
    order = Order(
        order_id=order_id or OrderId(value=f"sim-{uuid4().hex[:12]}"),
        instrument_id=command.instrument_id,
        side=command.side,
        order_type=command.order_type,
        quantity=command.quantity,
        price=command.price,
        time_in_force=command.time_in_force,
        status=OrderStatus.PENDING,
        correlation_id=command.correlation_id,
    )
    order.transition_to(OrderStatus.SUBMITTED)
    order.transition_to(OrderStatus.FILLED)
    order.filled_quantity = command.quantity
    # ponytail: stamp avg via price field only; Order has no avg_fill — ceiling = qty parity
    _ = price
    return order


class SimulatedFillSource:
    """BACKTEST — immediate fill at command price. No I/O."""

    def submit(self, command: PlaceOrderCommand) -> Order:
        return _filled_from_command(command)

    def cancel(self, order_id: OrderId) -> None:
        return None


class PaperFillSource:
    """PAPER — delegates to paper gateway when provided; else simulates."""

    def __init__(self, gateway: Any | None = None) -> None:
        self._gateway = gateway
        self._sim = SimulatedFillSource()

    def submit(self, command: PlaceOrderCommand) -> Order:
        if self._gateway is None:
            return self._sim.submit(command)
        oid = self._place(self._gateway, command)
        if isinstance(oid, Order):
            return oid
        get = getattr(self._gateway, "get_order", None)
        if get is not None:
            return get(oid)
        return _filled_from_command(command, order_id=oid)

    def cancel(self, order_id: OrderId) -> None:
        if self._gateway is None:
            return
        cancel = getattr(self._gateway, "cancel_order", None)
        if cancel is not None:
            cancel(order_id)

    @staticmethod
    def _place(gateway: Any, command: PlaceOrderCommand) -> Order | OrderId:
        for name in ("submit_order", "place_order"):
            fn = getattr(gateway, name, None)
            if fn is not None:
                return fn(command)
        raise TypeError("paper gateway missing submit_order/place_order")


class BrokerFillSource:
    """LIVE — delegates to broker adapter submit/cancel.

    Never invents FILLED from a place-ack id alone (real-money safety).
    """

    def __init__(self, adapter: Any) -> None:
        # None allowed only for composition resolution; submit() fails closed.
        self._adapter = adapter

    def submit(self, command: PlaceOrderCommand) -> Order:
        if self._adapter is None:
            raise ValueError("LIVE BrokerFillSource requires a broker adapter")
        result = None
        for name in ("submit_order", "place_order"):
            fn = getattr(self._adapter, name, None)
            if fn is not None:
                result = fn(command)
                break
        if result is None:
            raise TypeError("broker adapter missing submit_order/place_order")
        if isinstance(result, Order):
            return result
        get = getattr(self._adapter, "get_order", None)
        if get is not None:
            return get(result)
        return _submitted_from_command(command, order_id=result)

    def cancel(self, order_id: OrderId) -> None:
        if self._adapter is None:
            raise ValueError("LIVE BrokerFillSource requires a broker adapter")
        self._adapter.cancel_order(order_id)


def _submitted_from_command(
    command: PlaceOrderCommand,
    *,
    order_id: OrderId | None = None,
) -> Order:
    """Build SUBMITTED shell — venue ack without fill confirmation."""
    order = Order(
        order_id=order_id or OrderId(value=f"live-{uuid4().hex[:12]}"),
        instrument_id=command.instrument_id,
        side=command.side,
        order_type=command.order_type,
        quantity=command.quantity,
        price=command.price,
        time_in_force=command.time_in_force,
        status=OrderStatus.PENDING,
        correlation_id=command.correlation_id,
    )
    order.transition_to(OrderStatus.SUBMITTED)
    return order


def _corr_key(key: CorrelationId | str) -> str:
    return str(key.value) if isinstance(key, CorrelationId) else str(key)


class ReplayFillSource:
    """REPLAY — returns recorded fills keyed by correlation_id."""

    def __init__(
        self,
        recorded_fills: Mapping[CorrelationId, Order] | Mapping[str, Order] | None = None,
    ) -> None:
        self._fills: dict[str, Order] = {
            _corr_key(k): o for k, o in (recorded_fills or {}).items()  # type: ignore[arg-type]
        }

    def submit(self, command: PlaceOrderCommand) -> Order:
        key = _corr_key(command.correlation_id)
        order = self._fills.get(key)
        if order is None:
            raise KeyError(f"no recorded fill for correlation_id={key}")
        return order

    def cancel(self, order_id: OrderId) -> None:
        return None

    def record(self, correlation_id: CorrelationId, order: Order) -> None:
        self._fills[_corr_key(correlation_id)] = order
