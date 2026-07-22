"""TradingContext — runtime handle to cache (and optional bus)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.oms.trading_cache import TradingCache


@dataclass
class TradingContext:
    """ponytail: cache (+ optional bus) only; managers wired by composition root."""

    cache: TradingCache
    bus: Any | None = None
