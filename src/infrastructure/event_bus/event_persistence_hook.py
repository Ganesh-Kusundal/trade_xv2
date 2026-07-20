"""Event persistence hook — capital-event fsync before dispatch."""

from __future__ import annotations

import logging
import traceback
from typing import Any

from domain.events import DomainEvent
from domain.events.capital_events import is_capital_event

logger = logging.getLogger(__name__)


class EventPersistenceHook:
    """Persist events to EventLog before handler dispatch."""

    def __init__(
        self,
        event_log: Any | None = None,
        *,
        logging_enabled: bool = True,
        replay_mode: bool = False,
        dead_letter_queue: Any | None = None,
        metrics: Any | None = None,
        fail_fast: bool = False,
    ) -> None:
        self._event_log = event_log
        self._logging_enabled = logging_enabled
        self._replay_mode = replay_mode
        self._dead_letter_queue = dead_letter_queue
        self._metrics = metrics
        self._fail_fast = fail_fast

    @property
    def logging_enabled(self) -> bool:
        return self._logging_enabled

    def set_logging_enabled(self, enabled: bool) -> None:
        self._logging_enabled = enabled

    def set_event_log(self, event_log: Any | None) -> None:
        self._event_log = event_log

    def set_replay_mode(self, enabled: bool) -> None:
        self._replay_mode = enabled

    def persist(self, event: DomainEvent) -> None:
        """Append event to log (skipped in replay mode)."""
        if self._event_log is None or not self._logging_enabled or self._replay_mode:
            return
        try:
            sync = is_capital_event(event.event_type)
            try:
                self._event_log.append(event, sync_mode=sync)  # type: ignore[call-arg]
            except TypeError:
                self._event_log.append(event)
        except Exception as exc:
            if self._metrics is not None:
                self._metrics.add_timestamped_counter(
                    event.event_type, f"log_error:{type(exc).__name__}"
                )
            logger.exception(
                "EventPersistenceHook: failed to persist %s: %s", event.event_type, exc
            )
            if self._dead_letter_queue is not None:
                self._dead_letter_queue.push_failure(
                    event=event,
                    handler_id="<event_log>",
                    exc=exc,
                    traceback=traceback.format_exc(),
                )
            if self._fail_fast:
                raise
