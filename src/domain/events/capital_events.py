"""Canonical capital-event classification for sync persistence and async dispatch."""

from __future__ import annotations

from domain.events.types import EventType

_EXPLICIT_CAPITAL: frozenset[str] = frozenset(
    {
        EventType.TRADE.value,
        EventType.TRADE_APPLIED.value,
        EventType.TRADE_FILLED.value,
        EventType.ORDER_PLACED.value,
        EventType.ORDER_UPDATED.value,
        EventType.ORDER_CANCELLED.value,
        EventType.ORDER_REJECTED.value,
        EventType.ORDER_SUBMITTED.value,
    }
)


def is_capital_event(event_type: str) -> bool:
    """True for money-path events that must not be dropped and may require fsync."""
    et = (event_type or "").upper()
    if et in _EXPLICIT_CAPITAL:
        return True
    return et.startswith("ORDER_") or et.startswith("TRADE_") or et.startswith("POSITION_")


# AsyncEventBus: never drop these under backpressure (same semantics as sync fsync set).
CAPITAL_EVENT_TYPES: frozenset[str] = frozenset(
    et for et in _EXPLICIT_CAPITAL
) | frozenset(
    # Prefix families are evaluated at runtime via is_capital_event; explicit set
    # covers known enum values. Dynamic ORDER_/TRADE_/POSITION_ strings are
    # handled by is_capital_event() in AsyncEventBus.publish().
)

__all__ = ["CAPITAL_EVENT_TYPES", "is_capital_event"]
