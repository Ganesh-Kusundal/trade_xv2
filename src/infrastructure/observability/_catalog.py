"""Metrics catalog, alerting rules, and failure taxonomy."""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Metrics catalog
# ---------------------------------------------------------------------------

METRICS_CATALOG = """
# Broker infrastructure metrics catalog
# All metrics are labeled with at minimum {broker} and {operation} where applicable.

broker_request_latency_ms{broker, operation}
    - Histogram of request round-trip latency per broker per operation kind.

broker_errors_total{broker, operation, error_class}
    - Counter: total errors per broker per operation per error type
      (error_class: timeout, auth, quota, network, broker_error).

routing_decisions_total{operation, selected_broker, policy_version}
    - Counter: total routing decisions made per operation and selected broker.

routing_rejections_total{operation, rejected_broker, reason}
    - Counter: brokers rejected during routing and why.

quota_tokens_available{broker, endpoint_class}
    - Gauge: non-reserved tokens currently available in each bucket.

quota_utilization_ratio{broker, endpoint_class}
    - Gauge: fraction of bucket capacity consumed (0.0=empty used, 1.0=fully consumed).

quota_wait_seconds{broker, endpoint_class, priority_class}
    - Histogram: how long callers waited for a quota token.

quota_rejections_total{broker, endpoint_class, priority_class}
    - Counter: quota hard rejections (deadline exceeded).

stream_sessions_active{broker, stream_kind}
    - Gauge: number of currently active stream sessions per broker per kind.

stream_sessions_healthy{broker, stream_kind}
    - Gauge: number of healthy (connected + subscribed + fresh) sessions.

stream_staleness_seconds{broker, session_id}
    - Gauge: seconds since last valid tick for each active session.

stream_reconnects_total{broker, stream_kind}
    - Counter: total reconnect attempts per broker per stream kind.

stream_failovers_total{primary_broker, fallback_broker, stream_kind}
    - Counter: successful failovers between brokers.

historical_bars_fetched_total{broker, timeframe}
    - Counter: total bars successfully fetched per broker per timeframe.

historical_chunks_total{broker, event_type}
    - Counter: total chunks fetched (event_type: complete, failed).

historical_merge_conflicts_total{primary_broker, secondary_broker}
    - Counter: bar-level OHLCV conflicts detected during multi-source merge.

historical_fetch_latency_ms{broker, timeframe}
    - Histogram: chunk fetch latency per broker per timeframe.

extension_resolves_total{broker, extension, hit}
    - Counter: extension registry lookups (hit=true/false).
"""


# ---------------------------------------------------------------------------
# Alerting rule definitions
# ---------------------------------------------------------------------------

ALERTING_RULES = [
    {
        "name": "ExecutionQuotaExhausted",
        "severity": "critical",
        "condition": "rate(quota_rejections_total{priority_class='EXECUTION_CRITICAL'}[5m]) > 0",
        "description": "Execution-critical quota is being hard-rejected. "
        "Investigate quota headroom reservation and execution traffic volume.",
    },
    {
        "name": "HistoricalConsuming80PctBudget",
        "severity": "warning",
        "condition": "quota_utilization_ratio{endpoint_class='historical'} > 0.80",
        "description": "Historical backfill is consuming >80% of non-reserved quota. "
        "Risk of quota starvation for portfolio reads.",
    },
    {
        "name": "StreamStaleForBroker",
        "severity": "warning",
        "condition": "stream_staleness_seconds > 60",
        "description": "A stream session has not received valid data for >60 seconds. "
        "Check broker connectivity and subscription status.",
    },
    {
        "name": "StreamSessionsUnhealthy",
        "severity": "critical",
        "condition": "stream_sessions_healthy / stream_sessions_active < 0.5",
        "description": "More than half of active stream sessions are unhealthy.",
    },
    {
        "name": "BrokerHighErrorRate",
        "severity": "warning",
        "condition": "rate(broker_errors_total[5m]) / rate(broker_request_latency_ms_count[5m]) > 0.05",
        "description": "Broker error rate exceeds 5% of requests.",
    },
    {
        "name": "HistoricalFetchDegraded",
        "severity": "warning",
        "condition": "rate(historical_chunks_total{event_type='failed'}[5m]) > 0",
        "description": "Historical fetch chunks are failing. "
        "Coordinator may be using degraded/fallback mode.",
    },
    {
        "name": "MergeConflictsBurst",
        "severity": "warning",
        "condition": "rate(historical_merge_conflicts_total[10m]) > 10",
        "description": "High rate of OHLCV conflicts during multi-source merge. "
        "Investigate broker data quality alignment.",
    },
]


# ---------------------------------------------------------------------------
# Failure taxonomy
# ---------------------------------------------------------------------------

FAILURE_TAXONOMY = {
    "broker_unavailable": {
        "detection": "BrokerHealthSnapshot.alive=False OR BrokerUnavailableError raised",
        "impact": "Routing skips broker; failover attempted if policy allows",
        "recovery": "Automatic via health monitor re-check + re-registration",
        "observability": "routing_rejections_total{reason='unhealthy'}, broker.deregistered event",
    },
    "quota_exhausted": {
        "detection": "QuotaScheduler deadline exceeded → QuotaExhaustedError",
        "impact": "Throttle (queued) or reject (hard) based on priority",
        "recovery": "Backoff and retry; execution-critical never starved by lower priority",
        "observability": "quota_rejections_total, QuotaEvent{event_type='reject'}",
    },
    "stream_stale": {
        "detection": "FreshnessState.STALE after SLA threshold breach",
        "impact": "Session marked degraded; failover triggered if policy allows",
        "recovery": "Reconnect with idempotent resubscribe from SubscriptionPlan",
        "observability": "stream_staleness_seconds, stream.session.state_change{to_state='STALE'}",
    },
    "partial_historical_fetch": {
        "detection": "One or more chunks failed (ChunkRecord.error != None)",
        "impact": "Partial HistoricalSeries with explicit Gap records; degraded flag set",
        "recovery": "Fallback broker attempted for failed chunks; ledger records all attempts",
        "observability": "historical_chunks_total{event_type='failed'}, DegradedModeEvent",
    },
    "conflicting_overlap_bars": {
        "detection": "OverlapValidator finds |primary.close - secondary.close| / base > tolerance",
        "impact": "ConflictRecord logged; resolution applies merge_strategy",
        "recovery": "prefer_primary keeps existing; fail_on_conflict raises MergeConflictError",
        "observability": "historical_merge_conflicts_total, HistoricalMergeConflictEvent",
    },
    "unsupported_feature": {
        "detection": "ExtensionRegistry.require() for unregistered extension → UnsupportedExtensionError",
        "impact": "Caller receives error with alternatives list; never silent None",
        "recovery": "Route to alternative broker via alternatives list or policy update",
        "observability": "extension_resolves_total{hit='false'}, ExtensionResolveEvent",
    },
    "stream_auth_failure": {
        "detection": "StreamAuthError during connect or re-auth",
        "impact": "Session stays DISCONNECTED; reconnect loop retries with backoff",
        "recovery": "Token refresh triggered; reconnect attempted after token valid",
        "observability": "stream.session.state_change{reason='auth_failed'}, broker_errors_total{error_class='auth'}",
    },
}
