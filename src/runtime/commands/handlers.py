"""Concrete command handlers (ADR-012).

Each handler is a thin adapter: it translates a :class:`Command` into a call on
an existing domain service and wraps the result in a :class:`CommandResult`.
No business logic lives here — the domain services (``OrderManager``,
subscription manager, historical-data coordinator) remain the owners of
behavior and state.

Handlers depend only on domain ports + the command contracts, never on
``brokers.*`` (import-linter enforced).
"""

from __future__ import annotations

from typing import Any

from domain.events.types import DomainEvent, EventType

from .command import (
    CommandResult,
    LoadHistoryCommand,
    PlaceOrderCommand,
    SubscribeInstrumentCommand,
)


class OrderCommandHandler:
    """Routes :class:`PlaceOrderCommand` to ``OrderManager.place_order``.

    The OMS already performs the synchronous risk check and broker I/O outside
    its lock; this handler just delegates and adapts the ``OrderResult``.
    """

    handled_type = "place_order"

    def __init__(self, order_manager: Any, submit_fn: Any | None = None) -> None:
        self._order_manager = order_manager
        self._submit_fn = submit_fn

    def handle(self, command: PlaceOrderCommand) -> CommandResult:
        oms_cmd = command.to_oms_command()
        result = self._order_manager.place_order(oms_cmd, submit_fn=self._submit_fn)
        event = None
        if result.success and result.order is not None:
            event = make_order_placed_event(command, result.order)
        return CommandResult(
            success=result.success,
            data=result.order,
            error=result.error,
            correlation_id=command.correlation_id,
            event=event,
        )


class SubscribeCommandHandler:
    """Routes :class:`SubscribeInstrumentCommand` to a DataProvider.subscribe."""

    handled_type = "subscribe_instrument"

    def __init__(self, data_provider: Any) -> None:
        self._data_provider = data_provider

    def handle(self, command: SubscribeInstrumentCommand) -> CommandResult:
        # DataProvider.subscribe requires a callback; in the dispatcher path we
        # subscribe without a live callback (callers attach handlers via the bus).
        handle = self._data_provider.subscribe(
            command.instrument_id,
            callback=lambda iid, snap: None,
            depth=(command.mode == "depth"),
        )
        return CommandResult(
            success=True,
            data={"instrument_id": command.instrument_id, "handle": str(handle)},
            correlation_id=command.correlation_id,
        )


class HistoryCommandHandler:
    """Routes :class:`LoadHistoryCommand` to a DataProvider.history_batch."""

    handled_type = "load_history"

    def __init__(self, data_provider: Any) -> None:
        self._data_provider = data_provider

    def handle(self, command: LoadHistoryCommand) -> CommandResult:
        series = self._data_provider.history_batch(
            [command.symbol],
            timeframe=command.timeframe,
            lookback_days=command.lookback,
        )
        return CommandResult(
            success=True,
            data=series,
            correlation_id=command.correlation_id,
        )


def make_order_placed_event(command: PlaceOrderCommand, order: Any) -> DomainEvent:
    """Build the ``ORDER_PLACED`` event published after a successful order."""
    return DomainEvent.now(
        EventType.ORDER_PLACED.value,
        {"symbol": command.symbol, "order_id": getattr(order, "order_id", None)},
    )
