"""Event-log replay service for OMS crash recovery.

Replays persisted ``ORDER_UPDATED`` and ``TRADE`` events from the event log
to reconstruct order and position state after a restart.  Operates the bus in
*replay mode* so that downstream ``TRADE_APPLIED`` dispatch is suppressed and
positions are rebuilt deterministically.

Dependency direction
--------------------
``context.py`` → ``event_log_replay.py`` (one-way, no cycle).
The service receives concrete ports / managers through its constructor
and never imports from ``context.py``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.oms.order_manager import OrderManager
    from application.oms.position_manager import PositionManager
    from domain.ports import EventBusPort, EventLogPort

logger = logging.getLogger(__name__)


class EventLogReplayService:
    """Replay persisted events to rebuild OMS state after a restart.

    Parameters
    ----------
    event_bus:
        The application event bus — set into *replay mode* for the
        duration of the replay so downstream dispatch is suppressed.
    event_log:
        Source of persisted events.  Must expose an
        ``event_log.replay(event_types=...)`` iterator.
    order_manager:
        Receives ``ORDER_UPDATED`` and ``TRADE`` events during replay.
    position_manager:
        Receives ``TRADE_APPLIED`` events for accepted trades so
        positions are rebuilt even though bus dispatch is suppressed.
    """

    def __init__(
        self,
        event_bus: EventBusPort,
        event_log: EventLogPort,
        order_manager: OrderManager,
        position_manager: PositionManager,
    ) -> None:
        self._event_bus = event_bus
        self._event_log = event_log
        self._order_manager = order_manager
        self._position_manager = position_manager

    def replay(self) -> int:
        """Replay events into the OMS and return the count of replayed events.

        During replay the event bus is placed in *replay mode* (suppressing
        ``TRADE_APPLIED`` dispatch) and logging is temporarily disabled to
        avoid duplicate entries.  Both are restored in a ``finally`` block.

        Returns the number of events processed.
        """
        from domain.events.types import EventType

        if self._event_log is None:
            return 0

        # Defensive check — event_bus should always be initialized
        if self._event_bus is None:
            logger.warning("Event bus is None, skipping replay mode setup")
            return 0

        logger.info("Replaying event log into OMS")
        count = 0

        # Enable replay mode to prevent TRADE_APPLIED dispatch during replay
        # (which would cause PositionManager to double-count trades)
        replay_was_enabled = self._event_bus.replay_mode
        self._event_bus.set_replay_mode(True)

        # Prevent re-logging events while rebuilding state.
        logging_was_enabled = self._event_bus.logging_enabled
        self._event_bus.set_logging_enabled(False)
        try:
            for event in self._event_log.replay(
                event_types={EventType.ORDER_UPDATED.value, EventType.TRADE.value}
            ):
                if event.event_type == EventType.ORDER_UPDATED.value:
                    self._order_manager.on_order_update(event)
                elif event.event_type == EventType.TRADE.value:
                    # ENG-006: only rebuild positions for trades OMS accepted.
                    # Rejected/duplicate/unknown-order trades must not mutate
                    # the position book during crash recovery.
                    accepted = self._order_manager.on_trade(event)
                    if accepted:
                        # During replay, TRADE_APPLIED bus dispatch is suppressed
                        # (replay_mode=True), so invoke PositionManager directly.
                        self._position_manager.on_trade_applied(event)
                count += 1
        finally:
            self._event_bus.set_logging_enabled(logging_was_enabled)
            self._event_bus.set_replay_mode(replay_was_enabled)

        logger.info("Replayed %d events into OMS", count)
        return count
