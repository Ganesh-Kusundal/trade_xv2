"""CQRS command side (ADR-012).

Public surface for the synchronous :class:`CommandDispatcher` and the command
contracts. Application/SDK/CLI/API layers dispatch intents through this package
rather than calling domain services or brokers directly.
"""

from __future__ import annotations

from typing import Any, Callable

from .command import (
    Command,
    CommandResult,
    LoadHistoryCommand,
    PlaceOrderCommand,
    SubscribeInstrumentCommand,
)
from .dispatcher import CommandDispatcher
from .handlers import (
    HistoryCommandHandler,
    OrderCommandHandler,
    SubscribeCommandHandler,
)


def build_order_dispatcher(
    order_manager: Any,
    *,
    submit_fn: Any | None = None,
    event_bus: Any | None = None,
) -> tuple[CommandDispatcher, Callable[[Any], Any]]:
    """Build the ADR-012 order-command closure backed by ``OrderManager.place_order``.

    Returns the configured CommandDispatcher and the order closure.
    """
    from application.oms.order_manager import OrderResult

    command_dispatcher = CommandDispatcher(event_bus=event_bus)
    command_dispatcher.register_handler(
        OrderCommandHandler(order_manager, submit_fn=submit_fn)
    )

    def order_command_fn(oms_cmd: Any) -> OrderResult:
        cmd = PlaceOrderCommand(
            correlation_id=oms_cmd.correlation_id,
            symbol=oms_cmd.symbol,
            exchange=oms_cmd.exchange,
            side=oms_cmd.side,
            quantity=oms_cmd.quantity,
            price=oms_cmd.price,
            order_type=oms_cmd.order_type,
            product_type=oms_cmd.product_type,
        )
        result = command_dispatcher.dispatch(cmd)
        return OrderResult(
            success=result.success,
            order=result.data,
            error=result.error or "",
        )

    # Tag so OrderPlacer can assert the closure is OMS-backed (ADR-012).
    order_command_fn.__oms_backed__ = True  # type: ignore[attr-defined]
    return command_dispatcher, order_command_fn


__all__ = [
    "Command",
    "CommandResult",
    "LoadHistoryCommand",
    "PlaceOrderCommand",
    "SubscribeInstrumentCommand",
    "CommandDispatcher",
    "HistoryCommandHandler",
    "OrderCommandHandler",
    "SubscribeCommandHandler",
    "build_order_dispatcher",
]
