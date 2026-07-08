"""QuoteStream — an ordered buffer of QuoteSnapshot for an instrument.

Stores the most recent N quotes, providing time-series access for
indicators and analytics. Thread-safe for concurrent append/read.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Iterator

from domain.entities.market import QuoteSnapshot


class QuoteStream:
    """Bounded, thread-safe buffer of QuoteSnapshot for one instrument."""

    def __init__(self, symbol: str, exchange: str, max_size: int = 500) -> None:
        self._symbol = symbol
        self._exchange = exchange
        self._max_size = max_size
        self._buffer: deque[QuoteSnapshot] = deque(maxlen=max_size)
        self._lock = threading.Lock()

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def exchange(self) -> str:
        return self._exchange

    @property
    def latest(self) -> QuoteSnapshot | None:
        with self._lock:
            return self._buffer[-1] if self._buffer else None

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._buffer)

    def append(self, quote: QuoteSnapshot) -> None:
        with self._lock:
            self._buffer.append(quote)

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()

    def last_n(self, n: int) -> list[QuoteSnapshot]:
        with self._lock:
            return list(self._buffer)[-n:]

    def __iter__(self) -> Iterator[QuoteSnapshot]:
        with self._lock:
            return iter(list(self._buffer))

    def __len__(self) -> int:
        return self.size
