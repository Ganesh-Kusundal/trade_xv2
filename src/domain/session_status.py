"""Connect-time session status — product surface for mode / phase / orders.

Populated by ``tradex.connect`` / ``open_session``. Domain Session exposes
this as ``session.status`` so callers can see market vs trade readiness
without probing private fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Connection phases (UX design state machine)
PHASE_READY_MARKET = "ReadyMarket"
PHASE_READY_TRADE = "ReadyTrade"
PHASE_FAILED = "Failed"

# Session modes
MODE_SIM = "sim"
MODE_MARKET = "market"
MODE_TRADE = "trade"

VALID_MODES = frozenset({MODE_SIM, MODE_MARKET, MODE_TRADE})


@dataclass(frozen=True)
class SessionStatus:
    """Readiness snapshot attached to a domain Session after connect."""

    phase: str
    broker_id: str
    mode: str
    orders_enabled: bool
    authenticated: bool = True
    instruments_loaded: bool = True
    trace_id: str = ""
    diagnostics: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def describe(self) -> dict[str, Any]:
        """Stable dict for CLI / logs / API."""
        return {
            "phase": self.phase,
            "broker_id": self.broker_id,
            "mode": self.mode,
            "orders_enabled": self.orders_enabled,
            "authenticated": self.authenticated,
            "instruments_loaded": self.instruments_loaded,
            "trace_id": self.trace_id,
            "diagnostics": list(self.diagnostics),
        }
