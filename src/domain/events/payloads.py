"""Event payload contracts — schema definitions for each EventType.

Split from ``types.py`` (ADR-010) to reduce file size while maintaining
backward compatibility via re-exports in ``types.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domain.events.types import EventType


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

    ``version`` tracks schema evolution.
    """

    required_keys: tuple[str, ...] = ()
    optional_keys: tuple[str, ...] = ()
    notes: str = ""
    version: int = 1


# Catalogue — append-only. The dict key is the canonical EventType;
# the linter / test will catch mismatches.
EVENT_PAYLOADS: dict[EventType, EventPayload] = {
    EventType.TICK: EventPayload(
        required_keys=(),
        optional_keys=("ltp", "open", "high", "low", "close", "volume"),
        notes=(
            "TICK carries the latest quote snapshot for one symbol. "
            "Subscribers MUST tolerate missing optional keys — a partial "
            "tick is valid during warmup."
        ),
    ),
    EventType.QUOTE: EventPayload(
        required_keys=("symbol", "exchange", "ltp"),
        optional_keys=("bid", "ask", "volume", "open", "high", "low", "close"),
        notes="QUOTE carries a real-time quote snapshot for one instrument.",
    ),
    EventType.DEPTH: EventPayload(
        required_keys=("bids", "asks"),
        optional_keys=("ltp", "timestamp"),
        notes=(
            "DEPTH carries the order-book snapshot. bids/asks are "
            "lists of [price, quantity, orders] triples."
        ),
    ),
    EventType.DEPTH_20: EventPayload(
        required_keys=("bids", "asks"),
        optional_keys=("ltp", "timestamp"),
        notes="DEPTH_20 carries a 20-level order-book snapshot.",
    ),
    EventType.DEPTH_200: EventPayload(
        required_keys=("bids", "asks"),
        optional_keys=("ltp", "timestamp"),
        notes="DEPTH_200 carries a 200-level order-book snapshot.",
    ),
    EventType.ORDER_PLACED: EventPayload(
        required_keys=("order",),
        notes="ORDER_PLACED is published after a successful place_order().",
    ),
    EventType.ORDER_SUBMITTED: EventPayload(
        required_keys=("order",),
        notes="ORDER_SUBMITTED is published when an order is submitted to the broker.",
    ),
    EventType.ORDER_UPDATED: EventPayload(
        required_keys=("order",),
        notes="ORDER_UPDATED is published on every order status transition.",
    ),
    EventType.ORDER_CANCELLED: EventPayload(
        required_keys=("order_id",),
        optional_keys=("order",),
    ),
    EventType.ORDER_REJECTED: EventPayload(
        required_keys=("order_id", "reason"),
        optional_keys=("error_code",),
    ),
    EventType.TRADE: EventPayload(
        required_keys=("trade",),
        notes="TRADE is published when a fill is received.",
    ),
    EventType.TRADE_FILLED: EventPayload(
        required_keys=("trade",),
        notes="TRADE_FILLED is published when a fill is confirmed.",
    ),
    EventType.TRADE_APPLIED: EventPayload(
        required_keys=("trade",),
        notes=(
            "TRADE_APPLIED is the OMS-private downstream of TRADE. "
            "Published only after the OMS has accepted the trade "
            "(idempotency check passed). External consumers should "
            "subscribe to TRADE."
        ),
    ),
    EventType.RISK_LIMIT_BREACHED: EventPayload(
        required_keys=("rule", "value", "limit"),
        optional_keys=("symbol",),
        notes=(
            "Published by RiskManager when the continuous daily-loss MTM "
            "feed crosses a configured threshold — independent of any "
            "single order's approve/reject decision."
        ),
    ),
    EventType.RECONCILIATION_DRIFT: EventPayload(
        required_keys=("symbol", "internal", "broker"),
        optional_keys=("side", "quantity_diff"),
    ),
    EventType.RECONCILIATION_COMPLETED: EventPayload(
        optional_keys=("checked_at", "symbols", "drift_count"),
    ),
    EventType.SERVICE_STARTED: EventPayload(
        required_keys=("service_name",),
        optional_keys=("detail",),
    ),
    EventType.SERVICE_STOPPED: EventPayload(
        required_keys=("service_name",),
        optional_keys=("detail",),
    ),
    EventType.SERVICE_FAILED: EventPayload(
        required_keys=("service_name", "error"),
        optional_keys=("traceback",),
    ),
    EventType.INDEX_QUOTE: EventPayload(
        required_keys=("index",),
        optional_keys=("ltp", "change", "change_pct"),
    ),
    EventType.OPTION_CHAIN: EventPayload(
        required_keys=("underlying", "expiry"),
        optional_keys=("calls", "puts", "timestamp"),
    ),
    EventType.POSITION_UPDATED: EventPayload(
        required_keys=("symbol", "quantity"),
        optional_keys=("avg_price",),
    ),
    EventType.POSITION_OPENED: EventPayload(
        required_keys=("symbol", "quantity", "avg_price"),
    ),
    EventType.POSITION_CLOSED: EventPayload(
        required_keys=("symbol", "realized_pnl"),
    ),
    EventType.SIGNAL_GENERATED: EventPayload(
        required_keys=("signal",),
    ),
    EventType.KILL_SWITCH_TOGGLED: EventPayload(
        required_keys=("active",),
        optional_keys=("actor", "reason"),
    ),
    EventType.DAILY_PNL_RESET: EventPayload(
        optional_keys=("reset_at",),
    ),
    EventType.DRAWDOWN_LIMIT_HIT: EventPayload(
        required_keys=("drawdown", "limit"),
    ),
    EventType.BROKER_CONNECTED: EventPayload(
        required_keys=("broker_name",),
        optional_keys=("environment",),
    ),
    EventType.BROKER_DISCONNECTED: EventPayload(
        required_keys=("broker_name", "reason"),
    ),
    EventType.TOKEN_REFRESHED: EventPayload(
        required_keys=("broker_name",),
        optional_keys=("expires_at",),
    ),
    EventType.TOKEN_EXPIRED: EventPayload(
        required_keys=("broker_name",),
    ),
    EventType.CIRCUIT_BREAKER_OPENED: EventPayload(
        required_keys=("reason",),
        optional_keys=("duration",),
    ),
    EventType.CIRCUIT_BREAKER_CLOSED: EventPayload(
        optional_keys=("down_time",),
    ),
    EventType.SCAN_STARTED: EventPayload(
        required_keys=("profile",),
        optional_keys=("universe",),
    ),
    EventType.CANDIDATE_GENERATED: EventPayload(
        required_keys=("symbol", "score"),
        optional_keys=("reason",),
    ),
    EventType.SCAN_COMPLETED: EventPayload(
        required_keys=("candidate_count",),
        optional_keys=("duration", "universe"),
    ),
    EventType.SIGNAL_EXECUTED: EventPayload(
        required_keys=("signal", "order_id"),
    ),
    EventType.QUOTE_UPDATED: EventPayload(
        required_keys=("symbol", "exchange", "ltp"),
        optional_keys=("bid", "ask", "volume"),
        notes="QUOTE_UPDATED is published when an instrument's quote is refreshed.",
    ),
    EventType.DEPTH_UPDATED: EventPayload(
        required_keys=("symbol", "exchange"),
        optional_keys=("bids", "asks"),
        notes="DEPTH_UPDATED is published when market depth is fetched.",
    ),
    EventType.SUBSCRIPTION_STARTED: EventPayload(
        required_keys=("symbol", "exchange"),
        optional_keys=("depth",),
        notes="SUBSCRIPTION_STARTED is published when a live subscription begins.",
    ),
    EventType.SUBSCRIPTION_ENDED: EventPayload(
        required_keys=("symbol", "exchange"),
        notes="SUBSCRIPTION_ENDED is published when a live subscription ends.",
    ),
    EventType.SYSTEM_STARTED: EventPayload(
        required_keys=("service_name",),
        optional_keys=("version",),
    ),
    EventType.SYSTEM_SHUTDOWN: EventPayload(
        required_keys=("service_name",),
        optional_keys=("reason",),
    ),
    EventType.HEALTH_CHECK_PASSED: EventPayload(
        optional_keys=("component",),
    ),
    EventType.HEALTH_CHECK_FAILED: EventPayload(
        required_keys=("component", "error"),
    ),
    EventType.RISK_APPROVED: EventPayload(
        required_keys=("order_id",),
        notes="RISK_APPROVED is published when risk check passes for an order.",
    ),
    EventType.RISK_REJECTED: EventPayload(
        required_keys=("order_id", "rule", "value", "limit"),
        notes="RISK_REJECTED is published when risk check fails for an order.",
    ),
    EventType.PORTFOLIO_UPDATED: EventPayload(
        required_keys=("total_pnl", "capital", "positions_count"),
        optional_keys=("drawdown", "sharpe"),
        notes="PORTFOLIO_UPDATED is published when portfolio state changes.",
    ),
    EventType.METRICS_UPDATED: EventPayload(
        required_keys=("metric_name", "value"),
        optional_keys=("symbol", "strategy"),
        notes="METRICS_UPDATED is published when a metric value changes.",
    ),
    EventType.SCANNER_STATE_CHANGED: EventPayload(
        required_keys=("scanner_name", "state"),
        optional_keys=("reason",),
        notes="SCANNER_STATE_CHANGED is published when scanner state changes.",
    ),
    EventType.STRATEGY_ACTIVATED: EventPayload(
        required_keys=("strategy_name",),
        optional_keys=("activated_by",),
    ),
    EventType.STRATEGY_PAUSED: EventPayload(
        required_keys=("strategy_name",),
        optional_keys=("reason",),
    ),
    EventType.STRATEGY_DISABLED: EventPayload(
        required_keys=("strategy_name", "reason"),
    ),
    EventType.EXECUTION_PLAN_BUILT: EventPayload(
        required_keys=("symbol", "strategy", "signal_type", "legs_count"),
        optional_keys=("confidence", "total_qty", "sizing_method", "slicing_algo"),
        notes=(
            "EXECUTION_PLAN_BUILT is published after a signal is converted "
            "into an ExecutionPlan aggregate (post-gating)."
        ),
    ),
    EventType.ORDER_REQUESTED: EventPayload(
        required_keys=("symbol", "request"),
        optional_keys=("order_id", "slicing_algo"),
        notes=(
            "ORDER_REQUESTED is published when a concrete order request is issued for a plan leg."
        ),
    ),
    EventType.BAR_CLOSED: EventPayload(
        required_keys=("symbol", "timeframe"),
        optional_keys=("open", "high", "low", "close", "volume"),
        notes="BAR_CLOSED is published when a trading bar completes.",
    ),
}


_CANONICAL: frozenset[str] = frozenset(t.value for t in EventType)


def canonical_event_types() -> frozenset[str]:
    """Return every event type known to the bus, as strings."""
    return _CANONICAL


def make_payload(
    event_type: EventType,
    payload: dict[str, Any],
    validate: bool = False,
) -> dict[str, Any]:
    """Optionally validate ``payload`` against the contract for ``event_type``.

    If ``validate=False`` (default), this is a pass-through.
    If ``validate=True``, :class:`KeyError` is raised if any required key
    is missing.

    Returns the (possibly mutated) payload dict.
    """
    if not validate:
        return payload
    contract = EVENT_PAYLOADS.get(event_type)
    if contract is None:
        return payload
    missing = [k for k in contract.required_keys if k not in payload]
    if missing:
        raise KeyError(
            f"{event_type.value} payload missing required keys: {missing}; "
            f"contract: {contract.notes}"
        )
    return payload
