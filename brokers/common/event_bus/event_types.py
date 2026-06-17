"""Canonical event-type catalogue for the in-process event bus (REF-11).

Why this module exists
----------------------
The :class:`EventBus` accepts arbitrary string ``event_type`` values.
This was a deliberate design choice early on — strings are flexible
and require no schema migration when adding new event types — but it
has a real cost:

- A typo (``"TICk"`` vs ``"TICK"``) silently creates a separate
  event type that no subscriber will ever see. There is no test
  that catches this.
- The set of canonical event types is implicit; a new contributor
  reads the code to discover what is in use.
- Refactoring an event type requires grep across the entire
  codebase with no compiler help.

This module centralises the contract:

- :class:`EventType` is a :class:`str`-backed enum so existing
  code that compares ``event.event_type == "TICK"`` keeps working.
- :class:`EventPayload` declares the canonical payload keys for
  each event type. Validation is optional — see
  :func:`make_payload` — but the contract is documented.
- :func:`canonical_event_types` returns the full set so tests
  and lint rules can verify no unknown event types are introduced.

Migration
---------
New code SHOULD use :class:`EventType` directly. Existing code MAY
continue to pass strings; the bus does not enforce the enum and the
constants on the enum are the same as the legacy strings. A future
audit pass can tighten this — for now the goal is to provide a
single, grep-able source of truth, not to break callers.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """Canonical event types published on the :class:`EventBus`.

    Inheriting from :class:`str` means existing ``==`` comparisons
    with bare strings continue to work:

        if event.event_type == EventType.TICK:   # works
        if event.event_type == "TICK":          # also works

    The order is intentional — new types should be appended, never
    inserted, to keep the wire-format stable across deployments.
    """

    # ── Market data ────────────────────────────────────────────────────
    TICK = "TICK"
    DEPTH = "DEPTH"
    INDEX_QUOTE = "INDEX_QUOTE"
    OPTION_CHAIN = "OPTION_CHAIN"

    # ── Orders / OMS ───────────────────────────────────────────────────
    ORDER_PLACED = "ORDER_PLACED"
    ORDER_UPDATED = "ORDER_UPDATED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    TRADE = "TRADE"
    # TRADE_APPLIED is the OMS-private downstream of TRADE — published
    # only after the OMS has accepted the trade (idempotency check
    # passed). External consumers should subscribe to TRADE; the
    # position manager subscribes to TRADE_APPLIED to avoid double-
    # counting on duplicate websocket fills.
    TRADE_APPLIED = "TRADE_APPLIED"

    # ── Risk / position ────────────────────────────────────────────────
    POSITION_CHANGED = "POSITION_CHANGED"
    RISK_BREACH = "RISK_BREACH"
    KILL_SWITCH_FLIPPED = "KILL_SWITCH_FLIPPED"

    # ── Reconciliation ─────────────────────────────────────────────────
    RECONCILIATION_DRIFT = "RECONCILIATION_DRIFT"
    RECONCILIATION_OK = "RECONCILIATION_OK"

    # ── Lifecycle / system ─────────────────────────────────────────────
    SERVICE_STARTED = "SERVICE_STARTED"
    SERVICE_STOPPED = "SERVICE_STOPPED"
    SERVICE_FAILED = "SERVICE_FAILED"

    # ── Legacy aliases (still published by existing callers) ─────────
    POSITION_UPDATED = "POSITION_UPDATED"
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    RECONCILIATION_COMPLETED = "RECONCILIATION_COMPLETED"


@dataclass(frozen=True)
class EventPayload:
    """Payload contract for one :class:`EventType`.

    ``required_keys`` are the keys that MUST be present in
    ``DomainEvent.payload``. ``optional_keys`` are recognised but
    not enforced.

    The contract is *informative* today (validated by
    :func:`make_payload` if ``validate=True``). It exists so:

    - A subscriber reading ``event.payload["ltp"]`` knows ``ltp``
      is part of the contract and can rely on it.
    - A publisher adding a new key is forced to update this dataclass
      (because tests grep for changes).

    It is intentionally NOT used for runtime schema validation in
    production — that would couple the bus too tightly to the
    payload shape and break replay-compatibility for events
    recorded with older schemas.
    """

    event_type: EventType
    required_keys: tuple[str, ...] = ()
    optional_keys: tuple[str, ...] = ()
    notes: str = ""


# Catalogue — append-only. Adding a new entry does not require
# touching the enum; the linter / test will catch mismatches.
EVENT_PAYLOADS: dict[EventType, EventPayload] = {
    EventType.TICK: EventPayload(
        event_type=EventType.TICK,
        required_keys=(),
        optional_keys=("ltp", "open", "high", "low", "close", "volume"),
        notes=(
            "TICK carries the latest quote snapshot for one symbol. "
            "Subscribers MUST tolerate missing optional keys — a partial "
            "tick is valid during warmup."
        ),
    ),
    EventType.DEPTH: EventPayload(
        event_type=EventType.DEPTH,
        required_keys=("bids", "asks"),
        optional_keys=("ltp", "timestamp"),
        notes=(
            "DEPTH carries the order-book snapshot. bids/asks are "
            "lists of [price, quantity, orders] triples."
        ),
    ),
    EventType.ORDER_PLACED: EventPayload(
        event_type=EventType.ORDER_PLACED,
        required_keys=("order",),
        optional_keys=(),
        notes="ORDER_PLACED is published after a successful place_order().",
    ),
    EventType.ORDER_UPDATED: EventPayload(
        event_type=EventType.ORDER_UPDATED,
        required_keys=("order",),
        optional_keys=(),
        notes="ORDER_UPDATED is published on every order status transition.",
    ),
    EventType.ORDER_CANCELLED: EventPayload(
        event_type=EventType.ORDER_CANCELLED,
        required_keys=("order_id",),
        optional_keys=("order",),
    ),
    EventType.ORDER_REJECTED: EventPayload(
        event_type=EventType.ORDER_REJECTED,
        required_keys=("order_id", "reason"),
        optional_keys=("error_code",),
    ),
    EventType.TRADE: EventPayload(
        event_type=EventType.TRADE,
        required_keys=("trade",),
        optional_keys=(),
        notes="TRADE is published when a fill is received.",
    ),
    EventType.TRADE_APPLIED: EventPayload(
        event_type=EventType.TRADE_APPLIED,
        required_keys=("trade",),
        optional_keys=(),
        notes=(
            "TRADE_APPLIED is the OMS-private downstream of TRADE. "
            "Published only after the OMS has accepted the trade "
            "(idempotency check passed). External consumers should "
            "subscribe to TRADE."
        ),
    ),
    EventType.POSITION_CHANGED: EventPayload(
        event_type=EventType.POSITION_CHANGED,
        required_keys=("symbol", "quantity"),
        optional_keys=("avg_price", "realized_pnl"),
    ),
    EventType.RISK_BREACH: EventPayload(
        event_type=EventType.RISK_BREACH,
        required_keys=("rule", "value", "limit"),
        optional_keys=("symbol",),
    ),
    EventType.KILL_SWITCH_FLIPPED: EventPayload(
        event_type=EventType.KILL_SWITCH_FLIPPED,
        required_keys=("active",),
        optional_keys=("actor", "reason"),
    ),
    EventType.RECONCILIATION_DRIFT: EventPayload(
        event_type=EventType.RECONCILIATION_DRIFT,
        required_keys=("symbol", "internal", "broker"),
        optional_keys=("side", "quantity_diff"),
    ),
    EventType.RECONCILIATION_OK: EventPayload(
        event_type=EventType.RECONCILIATION_OK,
        required_keys=(),
        optional_keys=("checked_at", "symbols"),
        notes="Heartbeat-style: published after each successful reconcile cycle.",
    ),
    EventType.SERVICE_STARTED: EventPayload(
        event_type=EventType.SERVICE_STARTED,
        required_keys=("service_name",),
        optional_keys=("detail",),
    ),
    EventType.SERVICE_STOPPED: EventPayload(
        event_type=EventType.SERVICE_STOPPED,
        required_keys=("service_name",),
        optional_keys=("detail",),
    ),
    EventType.SERVICE_FAILED: EventPayload(
        event_type=EventType.SERVICE_FAILED,
        required_keys=("service_name", "error"),
        optional_keys=("traceback",),
    ),
    EventType.INDEX_QUOTE: EventPayload(
        event_type=EventType.INDEX_QUOTE,
        required_keys=("index",),
        optional_keys=("ltp", "change", "change_pct"),
    ),
    EventType.OPTION_CHAIN: EventPayload(
        event_type=EventType.OPTION_CHAIN,
        required_keys=("underlying", "expiry"),
        optional_keys=("calls", "puts", "timestamp"),
    ),
}


def canonical_event_types() -> frozenset[str]:
    """Return every event type known to the bus, as strings.

    Use this in tests that want to assert "no unknown event types
    are being published". Tests can diff the live set returned by
    the bus against this canonical set to catch typos.
    """
    return frozenset(t.value for t in EventType)


def make_payload(
    event_type: EventType,
    payload: dict[str, Any],
    validate: bool = False,
) -> dict[str, Any]:
    """Optionally validate ``payload`` against the contract for ``event_type``.

    If ``validate=False`` (default), this is a pass-through. The
    default is intentionally permissive because runtime validation
    would block legacy events on the event log.

    If ``validate=True``, :class:`KeyError` is raised if any
    required key is missing.

    Returns the (possibly mutated) payload dict so the call site
    can chain into :meth:`DomainEvent.now`.
    """
    if not validate:
        return payload
    contract = EVENT_PAYLOADS.get(event_type)
    if contract is None:
        # Unknown event type — allowed but flagged.
        return payload
    missing = [k for k in contract.required_keys if k not in payload]
    if missing:
        raise KeyError(
            f"{event_type.value} payload missing required keys: {missing}; "
            f"contract: {contract.notes}"
        )
    return payload


__all__ = [
    "EVENT_PAYLOADS",
    "EventPayload",
    "EventType",
    "canonical_event_types",
    "make_payload",
]
