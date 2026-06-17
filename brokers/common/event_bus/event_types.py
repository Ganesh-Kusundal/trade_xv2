"""Canonical event type enumeration for the TradeXV2 event bus.

All publish and subscribe calls MUST use these enum members instead of
raw string literals. Consumers that watch the bus for risk, rejection,
or reconciliation events can rely on every declared type being emitted.

Usage::

    from brokers.common.event_bus import DomainEvent, EventType

    bus.publish(DomainEvent.now(EventType.ORDER_PLACED, {"order": order}))
    bus.subscribe(EventType.RISK_BREACH, on_risk_breach)
"""

from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    """Canonical event types for the TradeXV2 event bus.

    Every type declared here MUST be published somewhere in the system.
    Conversely, no event should be published with a type NOT in this enum.
    """

    # ── Order lifecycle ──────────────────────────────────────────────────
    ORDER_PLACED = "ORDER_PLACED"
    ORDER_UPDATED = "ORDER_UPDATED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_REJECTED = "ORDER_REJECTED"

    # ── Trade lifecycle ──────────────────────────────────────────────────
    TRADE = "TRADE"
    TRADE_APPLIED = "TRADE_APPLIED"

    # ── Position lifecycle ───────────────────────────────────────────────
    POSITION_UPDATED = "POSITION_UPDATED"

    # ── Risk events ──────────────────────────────────────────────────────
    RISK_BREACH = "RISK_BREACH"
    KILL_SWITCH_FLIPPED = "KILL_SWITCH_FLIPPED"

    # ── Reconciliation events ────────────────────────────────────────────
    RECONCILIATION_OK = "RECONCILIATION_OK"
    RECONCILIATION_DRIFT = "RECONCILIATION_DRIFT"
    RECONCILIATION_COMPLETED = "RECONCILIATION_COMPLETED"

    # ── Signal events (analytics path) ───────────────────────────────────
    SIGNAL_GENERATED = "SIGNAL_GENERATED"

    # ── Market data events ───────────────────────────────────────────────
    TICK = "TICK"
    DEPTH = "DEPTH"
