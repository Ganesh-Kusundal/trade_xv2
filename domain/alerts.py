"""Canonical alert and exit automation dataclasses.

Submodule of :mod:`domain.entities` — imported via the re-export facade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(slots=True, frozen=True)
class ConditionalAlert:
    """Conditional alert state."""

    alert_id: str = ""
    symbol: str = ""
    condition: str = ""
    status: str = "ACTIVE"


@dataclass(slots=True, frozen=True)
class ConditionalAlertRequest:
    """Request model for placing a conditional alert."""

    symbol: str = ""
    exchange: str = "NSE"
    condition_type: str = ""
    threshold: Decimal = Decimal("0")


@dataclass(slots=True, frozen=True)
class MarketIntelligenceSnapshot:
    """One-shot aggregate of market intelligence for an underlying."""

    underlying: str = ""
    pcr: Decimal = Decimal("0")
    max_pain: Decimal = Decimal("0")
    oi_data: dict = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class PnlExitPolicy:
    """Policy for PnL-based exit automation."""

    target_pnl: Decimal = Decimal("0")
    stop_loss: Decimal = Decimal("0")


@dataclass(slots=True, frozen=True)
class PnlExitResult:
    """Result returned by PnL-exit automation."""

    success: bool = False
    message: str = ""
