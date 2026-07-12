"""CQRS command side (ADR-012).

Public surface for the synchronous :class:`CommandDispatcher` and the command
contracts. Application/SDK/CLI/API layers dispatch intents through this package
rather than calling domain services or brokers directly.
"""

from __future__ import annotations

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
]
