"""MessageRouter for type-filtered message routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from domain.value_objects import InstrumentId, StrategyId, AccountId
from infrastructure.message_bus.bus import MessageBus, Subscription


MessageHandler = Callable[[Any], Any]


@dataclass
class RouteBuilder:
    """Builder for configuring message routes."""
    
    _bus: MessageBus
    _msg_type: type
    _instrument: InstrumentId | None = None
    _strategy: StrategyId | None = None
    _account: AccountId | None = None
    
    def to(self, handler: MessageHandler) -> Subscription:
        """Register handler with filters."""
        def filtered_handler(message: Any) -> None:
            # Check instrument filter
            if self._instrument is not None:
                msg_instrument = getattr(message, "instrument_id", None)
                if msg_instrument != self._instrument:
                    return
            
            # Check strategy filter
            if self._strategy is not None:
                msg_strategy = getattr(message, "strategy_id", None)
                if msg_strategy != self._strategy:
                    return
            
            # Check account filter
            if self._account is not None:
                msg_account = getattr(message, "account_id", None)
                if msg_account != self._account:
                    return
            
            handler(message)
        
        return self._bus.subscribe(self._msg_type, filtered_handler)


class MessageRouter:
    """Routes messages with type and attribute filters."""
    
    def __init__(self, bus: MessageBus | None = None) -> None:
        self._bus = bus or MessageBus()
    
    def route(
        self,
        msg_type: type,
        *,
        instrument: InstrumentId | None = None,
        strategy: StrategyId | None = None,
        account: AccountId | None = None,
    ) -> RouteBuilder:
        """Create a route builder for the given message type and filters."""
        return RouteBuilder(
            _bus=self._bus,
            _msg_type=msg_type,
            _instrument=instrument,
            _strategy=strategy,
            _account=account,
        )
    
    def wire(
        self,
        msg_type: type,
        handler: MessageHandler,
        *,
        instrument: InstrumentId | None = None,
        strategy: StrategyId | None = None,
        account: AccountId | None = None,
    ) -> Subscription:
        """Shorthand for route().to()."""
        return self.route(
            msg_type,
            instrument=instrument,
            strategy=strategy,
            account=account,
        ).to(handler)
    
    def publish(self, message: Any) -> None:
        """Publish a message through the underlying bus."""
        self._bus.publish(message)
