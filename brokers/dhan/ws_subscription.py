"""DhanSubscriptionManager — subscription state management.

Responsibility: Track active instrument subscriptions, handle
subscribe/unsubscribe operations with deduplication and limit enforcement,
and validate exchange codes. Thread-safe via RLock.
"""

from __future__ import annotations

import logging
import threading
from typing import Sequence

logger = logging.getLogger(__name__)

# Valid exchange codes recognized by the Dhan SDK
_VALID_EXCHANGES: set[str] = {
    "IDX_I", "IDX",
    "NSE_EQ", "NSE", "NSE_FNO", "NFO", "NSE_CURRENCY", "CDS",
    "BSE_EQ", "BSE", "MCX_COMM", "MCX",
    "BSE_FNO", "BFO", "BSE_CURRENCY",
}


class DhanSubscriptionManager:
    """Manages WebSocket instrument subscriptions.

    Tracks which instruments are currently subscribed, enforces the
    Dhan WebSocket limit (default 1000), and provides deduplication
    to prevent duplicate subscriptions.

    Thread-safe: All state mutations are protected by RLock.
    """

    def __init__(
        self,
        max_instruments: int = 1000,
        initial: Sequence[tuple] | None = None,
    ) -> None:
        """Initialize subscription manager.

        Args:
            max_instruments: Maximum number of instruments allowed (Dhan limit).
            initial: Initial list of instruments to subscribe (already in SDK format).
        """
        self._max_instruments = max_instruments
        self._lock = threading.RLock()
        self._active: set[tuple] = set()

        if initial:
            for inst in initial:
                self._active.add(inst)

    @property
    def active_count(self) -> int:
        """Number of currently subscribed instruments."""
        with self._lock:
            return len(self._active)

    @property
    def active_instruments(self) -> set[tuple]:
        """Copy of currently active instruments."""
        with self._lock:
            return set(self._active)

    def subscribe(self, instruments: Sequence[tuple]) -> list[tuple]:
        """Add instruments to subscription.

        Deduplicates — instruments already subscribed are ignored.
        Returns only the NEW instruments that were actually added.

        Args:
            instruments: List of (exchange_int, security_id_int, mode_int) tuples.

        Returns:
            List of newly subscribed instruments.

        Raises:
            ValueError: If total subscriptions would exceed max_instruments.
        """
        with self._lock:
            new_instruments = [i for i in instruments if i not in self._active]
            if not new_instruments:
                return []

            total = len(self._active) + len(new_instruments)
            if total > self._max_instruments:
                raise ValueError(
                    f"Dhan WebSocket limit is {self._max_instruments} instruments, "
                    f"would have {total}. Unsubscribe some first."
                )

            self._active.update(new_instruments)

            # Warn when approaching limit (80% threshold)
            if total > self._max_instruments * 0.8:
                logger.warning(
                    "dhan_ws_instrument_limit_approaching",
                    extra={"current": total, "max": self._max_instruments},
                )

            return list(new_instruments)

    def unsubscribe(self, instruments: Sequence[tuple]) -> None:
        """Remove instruments from subscription.

        Silently ignores instruments that are not currently subscribed.

        Args:
            instruments: List of (exchange_int, security_id_int, mode_int) tuples.
        """
        with self._lock:
            for inst in instruments:
                self._active.discard(inst)

    def is_subscribed(self, instrument: tuple) -> bool:
        """Check if an instrument is currently subscribed.

        Args:
            instrument: (exchange_int, security_id_int, mode_int) tuple.

        Returns:
            True if instrument is actively subscribed.
        """
        with self._lock:
            return instrument in self._active

    def validate_exchange(self, exchange: str) -> None:
        """Validate that an exchange code is recognized.

        Args:
            exchange: Exchange code string (e.g. "NSE_EQ", "MCX_COMM").

        Raises:
            ValueError: If exchange code is not recognized.
        """
        if exchange.upper() not in _VALID_EXCHANGES:
            raise ValueError(f"Unknown exchange: {exchange}")

    def validate_instruments(self, instruments: Sequence[tuple]) -> None:
        """Validate all instruments in a list.

        Checks that each instrument's exchange code is recognized.

        Args:
            instruments: List of (exchange, security_id, mode) tuples
                        (string or integer format).

        Raises:
            ValueError: If any instrument has an unrecognized exchange.
        """
        for item in instruments:
            if len(item) >= 1:
                exchange = item[0]
                if isinstance(exchange, str):
                    self.validate_exchange(exchange)
