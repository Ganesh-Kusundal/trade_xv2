"""Unified broker session lifecycle state.

Single FSM for broker connectivity across plugins. Composes existing
BootstrapStatus and stream-health dimensions as read-only views — does not
replace them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from domain.ports.bootstrap import BootstrapStatus
from domain.stream_health import FreshnessState, SubscriptionState, TransportState


class BrokerSessionState(str, Enum):
    """Broker session lifecycle — canonical single source of truth."""

    CREATED = "CREATED"
    INITIALIZING = "INITIALIZING"
    AUTHENTICATING = "AUTHENTICATING"
    CONNECTED = "CONNECTED"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    RECOVERING = "RECOVERING"
    DISCONNECTED = "DISCONNECTED"
    SHUTDOWN = "SHUTDOWN"


# Valid transitions (spec state machine).
_ALLOWED: dict[BrokerSessionState, frozenset[BrokerSessionState]] = {
    BrokerSessionState.CREATED: frozenset(
        {BrokerSessionState.INITIALIZING, BrokerSessionState.SHUTDOWN}
    ),
    BrokerSessionState.INITIALIZING: frozenset(
        {BrokerSessionState.AUTHENTICATING, BrokerSessionState.DEGRADED, BrokerSessionState.SHUTDOWN}
    ),
    BrokerSessionState.AUTHENTICATING: frozenset(
        {BrokerSessionState.CONNECTED, BrokerSessionState.DEGRADED, BrokerSessionState.SHUTDOWN}
    ),
    BrokerSessionState.CONNECTED: frozenset(
        {BrokerSessionState.HEALTHY, BrokerSessionState.DEGRADED, BrokerSessionState.DISCONNECTED}
    ),
    BrokerSessionState.HEALTHY: frozenset(
        {BrokerSessionState.DEGRADED, BrokerSessionState.DISCONNECTED, BrokerSessionState.SHUTDOWN}
    ),
    BrokerSessionState.DEGRADED: frozenset(
        {
            BrokerSessionState.HEALTHY,
            BrokerSessionState.RECOVERING,
            BrokerSessionState.DISCONNECTED,
            BrokerSessionState.SHUTDOWN,
        }
    ),
    BrokerSessionState.RECOVERING: frozenset(
        {BrokerSessionState.HEALTHY, BrokerSessionState.CONNECTED, BrokerSessionState.DEGRADED}
    ),
    BrokerSessionState.DISCONNECTED: frozenset(
        {BrokerSessionState.RECOVERING, BrokerSessionState.INITIALIZING, BrokerSessionState.SHUTDOWN}
    ),
    BrokerSessionState.SHUTDOWN: frozenset(),
}


class InvalidSessionTransitionError(ValueError):
    """Raised when a broker session state transition is not allowed."""


def assert_valid_transition(
    current: BrokerSessionState,
    target: BrokerSessionState,
) -> None:
    """Raise if *target* is not reachable from *current*."""
    allowed = _ALLOWED.get(current, frozenset())
    if target not in allowed:
        raise InvalidSessionTransitionError(
            f"Invalid broker session transition: {current.value} -> {target.value}"
        )


def transition_state(
    current: BrokerSessionState,
    target: BrokerSessionState,
) -> BrokerSessionState:
    """Validate and return *target*."""
    assert_valid_transition(current, target)
    return target


def force_session_state(target: BrokerSessionState) -> BrokerSessionState:
    """Set terminal/teardown state without validating (close path only)."""
    return target


@dataclass(frozen=True)
class BrokerSessionStatus:
    """Composite broker session snapshot for callers and certification."""

    state: BrokerSessionState
    broker_id: str
    authenticated: bool = True
    instruments_loaded: bool = True
    bootstrap_status: BootstrapStatus | None = None
    transport: TransportState | None = None
    subscription: SubscriptionState | None = None
    freshness: FreshnessState | None = None
    phase: str = ""
    mode: str = ""
    orders_enabled: bool = False
    trace_id: str = ""
    diagnostics: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def is_usable(self) -> bool:
        return self.state in {
            BrokerSessionState.CONNECTED,
            BrokerSessionState.HEALTHY,
            BrokerSessionState.DEGRADED,
        }

    @property
    def is_live_ready(self) -> bool:
        return self.is_usable and self.authenticated

    def describe(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "broker_id": self.broker_id,
            "authenticated": self.authenticated,
            "instruments_loaded": self.instruments_loaded,
            "bootstrap_status": self.bootstrap_status.value if self.bootstrap_status else None,
            "transport": self.transport.value if self.transport else None,
            "subscription": self.subscription.value if self.subscription else None,
            "freshness": self.freshness.value if self.freshness else None,
            "phase": self.phase,
            "mode": self.mode,
            "orders_enabled": self.orders_enabled,
            "trace_id": self.trace_id,
            "diagnostics": list(self.diagnostics),
            "is_usable": self.is_usable,
            "is_live_ready": self.is_live_ready,
        }


def derive_bootstrap_status(connect_status: Any | None) -> BootstrapStatus | None:
    """Map connect-time SessionStatus to BootstrapStatus when possible."""
    if connect_status is None:
        return None
    if not getattr(connect_status, "authenticated", True):
        return BootstrapStatus.REAUTH_REQUIRED
    phase = getattr(connect_status, "phase", "")
    if phase == "Failed":
        return BootstrapStatus.FAILED
    if not getattr(connect_status, "instruments_loaded", True):
        return BootstrapStatus.DEGRADED
    return BootstrapStatus.READY


def build_session_status(
    *,
    state: BrokerSessionState,
    connect_status: Any | None,
    broker_id: str,
    transport: TransportState | None = None,
    subscription: SubscriptionState | None = None,
    freshness: FreshnessState | None = None,
) -> BrokerSessionStatus:
    """Build a :class:`BrokerSessionStatus` from connect snapshot + FSM state."""
    if connect_status is not None and hasattr(connect_status, "describe"):
        d = connect_status.describe()
        return BrokerSessionStatus(
            state=state,
            broker_id=broker_id,
            authenticated=bool(d.get("authenticated", True)),
            instruments_loaded=bool(d.get("instruments_loaded", True)),
            bootstrap_status=derive_bootstrap_status(connect_status),
            transport=transport,
            subscription=subscription,
            freshness=freshness,
            phase=str(d.get("phase", "")),
            mode=str(d.get("mode", "")),
            orders_enabled=bool(d.get("orders_enabled", False)),
            trace_id=str(d.get("trace_id", "")),
            diagnostics=tuple(d.get("diagnostics") or ()),
        )
    return BrokerSessionStatus(
        state=state,
        broker_id=broker_id,
        bootstrap_status=derive_bootstrap_status(connect_status),
        transport=transport,
        subscription=subscription,
        freshness=freshness,
    )


__all__ = [
    "BrokerSessionState",
    "BrokerSessionStatus",
    "InvalidSessionTransitionError",
    "assert_valid_transition",
    "build_session_status",
    "derive_bootstrap_status",
    "transition_state",
]
