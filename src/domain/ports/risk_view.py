"""RiskViewPort — read-only risk-state introspection, mirroring OrderServicePort.

Domain Session / AccountView depend on this protocol, never on RiskManager
or its internals. The application layer implements it (RiskManager itself
satisfies this protocol structurally via get_risk_profile()) and it is
wired in at composition-root time, same pattern as OrderServicePort.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from domain.portfolio.risk_profile import RiskProfile


@runtime_checkable
class RiskViewPort(Protocol):
    """Expose a read-only RiskProfile snapshot. Never mutates risk state."""

    def get_risk_profile(self) -> RiskProfile:
        """Return the current risk limits and today's headroom."""
        ...
