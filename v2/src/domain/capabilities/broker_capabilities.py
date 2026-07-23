"""Domain capability profiles (minimal v2 port).

Only :class:`RateLimitProfile` is ported so far — the fields the broker
plugins actually consume (429 cooldown + optional per-bucket min-interval
overrides). The full capability matrix from the legacy tree can be ported
incrementally as v2 grows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class RateLimitProfile:
    """Rate-limit envelope sourced from broker capabilities.

    cooldown_on_429_s — mandatory back-off after a 429 response (seconds).
    min_interval_ms   — optional per-bucket overrides mapping bucket name
                        (e.g. ``"orders"``) to a minimum inter-request
                        interval in milliseconds.
    """

    cooldown_on_429_s: float | None = None
    min_interval_ms: Mapping[str, float] | None = None


__all__ = ["RateLimitProfile"]
