"""Handler dispatch + DLQ recording extracted from EventBus (GC-01)."""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from domain.events import DomainEvent

if TYPE_CHECKING:
    from domain.ports.observability import EventMetricsPort
    from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue

logger = logging.getLogger(__name__)

EventHandler = Callable[[DomainEvent], None]


class EventDispatchHook:
    """Dispatch events to subscribers; record handler failures to DLQ."""

    def __init__(
        self,
        *,
        dead_letter_queue: DeadLetterQueue | None = None,
        metrics: EventMetricsPort | None = None,
        fail_fast: bool = False,
    ) -> None:
        self._dead_letter_queue = dead_letter_queue
        self._metrics = metrics
        self._fail_fast = fail_fast

    def dispatch(
        self,
        event: DomainEvent,
        handlers: list[tuple[str, EventHandler]],
    ) -> int:
        failures = 0
        for handler_id, handler in handlers:
            if self._metrics is not None:
                self._metrics.add_timestamped_counter(event.event_type, "dispatched")
            try:
                handler(event)
            except Exception as exc:
                failures += 1
                self.handle_failure(event, handler_id, exc)
                if self._fail_fast:
                    raise
        return failures

    def handle_failure(
        self,
        event: DomainEvent,
        handler_id: str,
        exc: BaseException,
    ) -> None:
        error_type = type(exc).__name__
        if self._metrics is not None:
            self._metrics.add_timestamped_counter(event.event_type, f"handler_error:{error_type}")
            self._metrics.add_timestamped_counter(event.event_type, "dead_letter")
        logger.warning(
            "EventBus: handler %s failed on %s (event_id=%s, symbol=%s): %s: %s",
            handler_id,
            event.event_type,
            event.event_id,
            event.symbol,
            error_type,
            exc,
        )
        if self._dead_letter_queue is not None:
            self._dead_letter_queue.push_failure(
                event=event,
                handler_id=handler_id,
                exc=exc,
                traceback=traceback.format_exc(),
            )
        else:
            logger.error(
                "EventBus: handler %s failed on %s but no DeadLetterQueue is "
                "attached. The failure is only visible in logs.",
                handler_id,
                event.event_type,
            )


__all__ = ["EventDispatchHook", "EventHandler"]
