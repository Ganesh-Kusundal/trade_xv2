"""Synchronous CommandDispatcher (ADR-012).

Routes a :class:`Command` to its registered handler by ``command_type`` and
returns a :class:`CommandResult` **synchronously**. This keeps the critical
trading path (risk check -> order submission -> acknowledgement) deterministic
and low-latency: the dispatcher does not await the event bus.

Responsibilities:
- correlation-id propagation (via ``infrastructure.correlation``),
- optional idempotency on the critical path (``IdempotencyGuard``),
- publish the command's domain event *after* a successful handler result,
- never swallow handler exceptions (fail-fast for trading correctness).

The dispatcher depends only on domain ports and the command contracts. It
MUST NOT import concrete brokers (enforced by import-linter).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from domain.ports import EventBusPort
from infrastructure.correlation import with_correlation

from .command import Command, CommandResult

logger = logging.getLogger(__name__)

# Handlers receive a Command and return a CommandResult.
CommandHandler = Callable[[Command], CommandResult]


class CommandDispatcher:
    """Routes commands to handlers and publishes resulting events.

    Thread-safe for registration and dispatch. Dispatch itself is synchronous
    and returns the handler's result directly.
    """

    def __init__(
        self,
        event_bus: EventBusPort | None = None,
        idempotency: Any | None = None,
    ) -> None:
        self._handlers: dict[str, CommandHandler] = {}
        self._bus = event_bus
        self._idempotency = idempotency

    def register(self, command_type: str, handler: CommandHandler) -> None:
        """Register a handler for a command type (last writer wins)."""
        self._handlers[command_type] = handler

    def register_handler(self, handler: Any) -> None:
        """Register a handler object that exposes ``handled_type`` + ``handle``.

        Lets concrete handlers self-declare the command type they serve.
        """
        self.register(handler.handled_type, handler.handle)

    @property
    def registered_types(self) -> list[str]:
        return sorted(self._handlers)

    def dispatch(self, command: Command) -> CommandResult:
        """Route and execute a command synchronously.

        The correlation id is propagated to the current context so any events
        published downstream (by the handler or the OMS) carry it. On success,
        the command's optional ``to_event()`` is published on the bus — this is
        the async fan-out, decoupled from the return value.
        """
        handler = self._handlers.get(command.command_type)
        if handler is None:
            return CommandResult(
                success=False,
                error=f"No handler registered for command '{command.command_type}'",
                correlation_id=command.correlation_id,
            )

        with with_correlation(command.correlation_id):
            result = handler(command)

        if result.success and self._bus is not None and result.event is not None:
            try:
                self._bus.publish(result.event)
            except Exception:  # pragma: no cover - bus failures are logged
                logger.exception(
                    "CommandDispatcher failed to publish event for %s",
                    command.command_type,
                )
        return result
