"""ScannerEngine — High-performance dynamic market scanner core.

Filters symbols across active universes and generates deterministic candidate IDs.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ScannerCandidate:
    symbol: str
    exchange: str
    score: Decimal
    signal_type: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def candidate_id(self) -> str:
        """Deterministic candidate hash derived from symbol, exchange, signal_type, and score."""
        raw = f"{self.symbol}:{self.exchange}:{self.signal_type}:{self.score}"
        h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
        return f"cand_{h}"


ScreenerFn = Callable[[dict[str, Any]], ScannerCandidate | None]


class ScannerEngine:
    """Orchestrates market screeners and universe filtering."""

    def __init__(self) -> None:
        self._screeners: list[ScreenerFn] = []

    def add_screener(self, screener: ScreenerFn) -> None:
        self._screeners.append(screener)

    def scan(self, universe_quotes: list[dict[str, Any]]) -> list[ScannerCandidate]:
        """Evaluate screeners against universe quote data. Returns qualified candidates."""
        results: list[ScannerCandidate] = []
        for quote_data in universe_quotes:
            for screener in self._screeners:
                candidate = screener(quote_data)
                if candidate is not None:
                    results.append(candidate)
        return results
