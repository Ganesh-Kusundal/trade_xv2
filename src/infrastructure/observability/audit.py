"""Structured audit event emission for multi-broker operations.

All functions emit structured log events with consistent field names.
Callers should not rely on side effects beyond the log emission — these
are fire-and-forget observability hooks.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

"""Structured audit events and metrics catalog for the broker infrastructure.

This module defines:
1. Structured log event schemas (as typed dataclasses) for every decision and
   state change that must be auditable after the fact.
2. A metrics catalog — the canonical set of metric names and label sets
   exported to Prometheus/StatsD via the infrastructure observability layer.
3. Alerting rule definitions — thresholds and conditions that signal operational
   problems requiring human attention.

Every auto-mode routing decision, historical merge, stream state change, quota
rejection, and extension resolution produces a structured event here.  Events
are emitted via the standard ``logging`` module as ``logger.info/warning`` with
``extra=<event_dict>`` so they can be parsed by log aggregators or forwarded
to a metrics pipeline.

Usage in broker infrastructure code::

    from infrastructure.observability.audit import emit_routing_decision

    emit_routing_decision(decision)
    emit_quota_event(token, wait_ms=12.3)
    emit_stream_state_change(session, from_state, to_state, reason)
"""

logger = logging.getLogger("broker.audit")


# ---------------------------------------------------------------------------
# Structured audit event schemas
# ---------------------------------------------------------------------------


@dataclass
class RoutingDecisionEvent:
    """Emitted on every BrokerRouter.route() call — success or failure."""

    trace_id: str
    operation: str
    primary_broker: str
    fallback_brokers: list[str]
    parallel_brokers: list[str]
    policy_version: str
    reason_codes: list[str]
    rejected: dict[str, str]
    decided_at: str

    event: str = "routing.decision"


@dataclass
class QuotaEvent:
    """Emitted on quota acquire / reject."""

    broker_id: str
    endpoint_class: str
    priority_class: str
    event_type: str  # "acquire" | "reject"
    wait_ms: float
    token_id: str | None = None
    retry_after_s: float | None = None

    event: str = "quota.event"


@dataclass
class HistoricalChunkEvent:
    """Emitted on historical chunk fetch start and completion."""

    request_id: str
    chunk_id: str
    broker_id: str
    from_date: str
    to_date: str
    timeframe: str
    event_type: str  # "start" | "complete" | "failed"
    bar_count: int = 0
    latency_ms: float = 0.0
    error: str | None = None

    event: str = "historical.chunk"


@dataclass
class HistoricalMergeConflictEvent:
    """Emitted for each OHLCV conflict detected during merge."""

    request_id: str
    instrument: str
    timeframe: str
    bar_event_time: str
    primary_broker: str
    secondary_broker: str
    delta_pct: str
    resolution: str

    event: str = "historical.merge.conflict"


@dataclass
class StreamStateChangeEvent:
    """Emitted on every stream session state transition."""

    session_id: str
    broker_id: str
    stream_kind: str
    from_state: str
    to_state: str
    reason: str
    reconnect_generation: int

    event: str = "stream.session.state_change"


@dataclass
class StreamFailoverEvent:
    """Emitted when a stream session fails over to a different broker."""

    session_id: str
    primary_broker: str
    fallback_broker: str
    stale_seconds: float
    handoff_ms: float | None = None

    event: str = "stream.failover"


@dataclass
class ExtensionResolveEvent:
    """Emitted on every extension registry lookup."""

    broker_id: str
    extension_name: str
    hit: bool  # True if extension was found
    alternatives: list[str]

    event: str = "extension.resolve"


@dataclass
class DegradedModeEvent:
    """Emitted when any subsystem enters degraded mode."""

    subsystem: str  # "historical" | "stream" | "quota"
    broker_id: str | None
    reason: str
    severity: str = "warning"  # "warning" | "critical"

    event: str = "degraded_mode"


# ---------------------------------------------------------------------------
# Emitters
# ---------------------------------------------------------------------------


def _emit(event_obj: Any) -> None:
    d = asdict(event_obj) if hasattr(event_obj, "__dataclass_fields__") else vars(event_obj)
    d.setdefault("timestamp", datetime.now(tz=timezone.utc).isoformat())
    event_name = d.get("event", "unknown")
    logger.info(event_name, extra=d)


def emit_routing_decision(decision: Any) -> None:
    """Emit a structured routing decision event."""
    evt = RoutingDecisionEvent(
        trace_id=decision.trace_id,
        operation=decision.operation.value
        if hasattr(decision.operation, "value")
        else str(decision.operation),
        primary_broker=decision.primary_broker,
        fallback_brokers=list(decision.fallback_brokers),
        parallel_brokers=list(decision.parallel_brokers),
        policy_version=decision.policy_version,
        reason_codes=list(decision.reason_codes),
        rejected=dict(decision.rejected),
        decided_at=decision.decided_at.isoformat(),
    )
    _emit(evt)


def emit_quota_event(
    broker_id: str,
    endpoint_class: str,
    priority_class: str,
    event_type: str,
    wait_ms: float = 0.0,
    token_id: str | None = None,
    retry_after_s: float | None = None,
) -> None:
    """Emit a quota acquire or reject event."""
    _emit(
        QuotaEvent(
            broker_id=broker_id,
            endpoint_class=endpoint_class,
            priority_class=priority_class,
            event_type=event_type,
            wait_ms=wait_ms,
            token_id=token_id,
            retry_after_s=retry_after_s,
        )
    )


def emit_historical_chunk(
    request_id: str,
    chunk_id: str,
    broker_id: str,
    from_date: str,
    to_date: str,
    timeframe: str,
    event_type: str,
    bar_count: int = 0,
    latency_ms: float = 0.0,
    error: str | None = None,
) -> None:
    _emit(
        HistoricalChunkEvent(
            request_id=request_id,
            chunk_id=chunk_id,
            broker_id=broker_id,
            from_date=from_date,
            to_date=to_date,
            timeframe=timeframe,
            event_type=event_type,
            bar_count=bar_count,
            latency_ms=latency_ms,
            error=error,
        )
    )


def emit_merge_conflict(
    request_id: str,
    instrument: str,
    timeframe: str,
    bar_event_time: str,
    primary_broker: str,
    secondary_broker: str,
    delta_pct: str,
    resolution: str,
) -> None:
    _emit(
        HistoricalMergeConflictEvent(
            request_id=request_id,
            instrument=instrument,
            timeframe=timeframe,
            bar_event_time=bar_event_time,
            primary_broker=primary_broker,
            secondary_broker=secondary_broker,
            delta_pct=delta_pct,
            resolution=resolution,
        )
    )


def emit_stream_state_change(
    session_id: str,
    broker_id: str,
    stream_kind: str,
    from_state: str,
    to_state: str,
    reason: str,
    reconnect_generation: int = 0,
) -> None:
    _emit(
        StreamStateChangeEvent(
            session_id=session_id,
            broker_id=broker_id,
            stream_kind=stream_kind,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            reconnect_generation=reconnect_generation,
        )
    )


def emit_stream_failover(
    session_id: str,
    primary_broker: str,
    fallback_broker: str,
    stale_seconds: float,
    handoff_ms: float | None = None,
) -> None:
    logger.warning(
        "stream.failover",
        extra=asdict(
            StreamFailoverEvent(
                session_id=session_id,
                primary_broker=primary_broker,
                fallback_broker=fallback_broker,
                stale_seconds=stale_seconds,
                handoff_ms=handoff_ms,
            )
        ),
    )


def emit_extension_resolve(
    broker_id: str,
    extension_name: str,
    hit: bool,
    alternatives: list[str],
) -> None:
    level = logging.DEBUG if hit else logging.INFO
    logger.log(
        level,
        "extension.resolve",
        extra=asdict(
            ExtensionResolveEvent(
                broker_id=broker_id,
                extension_name=extension_name,
                hit=hit,
                alternatives=alternatives,
            )
        ),
    )


def emit_degraded_mode(
    subsystem: str,
    reason: str,
    broker_id: str | None = None,
    severity: str = "warning",
) -> None:
    log_level = logging.CRITICAL if severity == "critical" else logging.WARNING
    logger.log(
        log_level,
        "degraded_mode",
        extra=asdict(
            DegradedModeEvent(
                subsystem=subsystem,
                broker_id=broker_id,
                reason=reason,
                severity=severity,
            )
        ),
    )


# Re-export catalog for backward compatibility
from infrastructure.observability._catalog import (
    ALERTING_RULES,
    FAILURE_TAXONOMY,
    METRICS_CATALOG,
)
