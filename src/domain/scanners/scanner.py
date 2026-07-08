"""Scanner ABC and ScannerResult value object.

A Scanner scans market instruments against a set of criteria and returns
ranked ScannerResult instances. Scanners are stateless; all context is
passed via the ``scan()`` parameters.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ScannerResult:
    """A single scan hit — instrument reference + score + metadata."""

    symbol: str
    exchange: str
    score: float
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def instrument_key(self) -> str:
        return f"{self.exchange}:{self.symbol}"


class Scanner(ABC):
    """Abstract base for market scanners.

    Subclasses implement ``scan()`` to return ranked ``ScannerResult``
    instances. Scanners must be stateless — all context is injected via
    method parameters.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable scanner name."""

    @abstractmethod
    def scan(
        self,
        symbols: list[str],
        exchange: str,
        **kwargs: Any,
    ) -> list[ScannerResult]:
        """Scan *symbols* and return results sorted by descending score."""
