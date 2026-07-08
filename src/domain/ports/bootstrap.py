"""Domain-level bootstrap types for broker readiness.

These types define the domain contract for broker gateway construction
outcomes.  Broker adapters implement these types; CLI and application
code depend on them through domain.ports, never through brokers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class BootstrapStatus(str, Enum):
    """Outcome status of broker gateway construction + readiness probes."""

    READY = "ready"
    DEGRADED = "degraded"
    REAUTH_REQUIRED = "reauth_required"
    FAILED = "failed"


@dataclass(frozen=True)
class BootstrapResult:
    """Outcome of broker gateway construction + readiness probes."""

    status: BootstrapStatus
    broker: str
    gateway: Any | None = None
    error: str | None = None
    probe_passed: bool = False
    authenticated: bool = False
    probe_name: str | None = None
    refreshed_token: bool = False

    @property
    def ok(self) -> bool:
        return self.status == BootstrapStatus.READY and self.gateway is not None

    @property
    def live_ready(self) -> bool:
        """True when gateway is ready and authenticated probe passed."""
        return self.ok and self.authenticated


def classify_exception(exc: BaseException) -> BootstrapStatus:
    """Map exceptions to bootstrap status."""
    name = type(exc).__name__
    module = type(exc).__module__ or ""
    if "Auth" in name or "Configuration" in name or "credential" in str(exc).lower():
        return BootstrapStatus.REAUTH_REQUIRED
    if "ProductionReadiness" in name:
        return BootstrapStatus.FAILED
    if module.startswith("brokers.") and ("auth" in module or "config" in module):
        return BootstrapStatus.REAUTH_REQUIRED
    return BootstrapStatus.FAILED


__all__ = [
    "BootstrapResult",
    "BootstrapStatus",
    "classify_exception",
]
