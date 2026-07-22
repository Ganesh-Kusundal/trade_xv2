# 10 — Observability and Operations

## 1. Purpose

Observability is structural, not bolted on. Every message publish, order state transition, and component lifecycle event is traceable through structured logging, metrics, and distributed tracing.

## 2. Observability Stack

```
┌─────────────────────────────────────────────────────────┐
│                  OBSERVABILITY STACK                     │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Structured  │  │   Metrics    │  │   Tracing    │  │
│  │  Logging     │  │  Collection  │  │  (OpenTel)   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐                     │
│  │  Health      │  │  Audit       │                     │
│  │  Checks      │  │  Sink        │                     │
│  └──────────────┘  └──────────────┘                     │
└─────────────────────────────────────────────────────────┘
```

## 3. Structured Logging

Logging uses **structlog** for JSON output with bound context (component_id, correlation_id, session_id).

### Log Format

```json
{
  "timestamp": "2026-07-22T13:45:00.123456789Z",
  "level": "INFO",
  "component": "execution_engine",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "event": "order_submitted",
  "order_id": "ORD-12345",
  "instrument_id": "NSE:RELIANCE",
  "side": "BUY",
  "quantity": "100",
  "latency_ms": 45
}
```

### Log Levels by Event

| Level | Events |
|-------|--------|
| DEBUG | Message bus dispatch, cache reads |
| INFO | Order submitted, fill received, component started |
| WARNING | Risk rejected, reconciliation drift (LOW/MEDIUM) |
| ERROR | Venue rejection, parse failure, handler exception |
| CRITICAL | Kill switch tripped, reconciliation HIGH drift, HALTED |

### Rules

- Every log entry includes component_id and timestamp
- Order-related logs include correlation_id
- No secrets (tokens, passwords) in log output
- Structured JSON format for machine parsing (structlog JSONRenderer in production; ConsoleRenderer in dev)
- Log context propagated via contextvars — every order path binds correlation_id at entry

## 4. Metrics Collection

### Built-In Metrics

| Metric | Type | Labels |
|--------|------|--------|
| orders_submitted_total | Counter | broker, side, instrument |
| orders_filled_total | Counter | broker, side, instrument |
| orders_rejected_total | Counter | broker, reason |
| risk_rejected_total | Counter | reason |
| order_latency_seconds | Histogram | broker, operation |
| fill_latency_seconds | Histogram | broker |
| position_count | Gauge | account |
| unrealized_pnl | Gauge | account |
| message_bus_queue_depth | Gauge | component |
| message_bus_publish_total | Counter | message_type |
| reconciliation_drift_total | Counter | severity |
| broker_connected | Gauge | broker_id |
| component_health | Gauge | component_id, state |

### ExecutionEngine Metrics

```python
# In ExecutionEngine:
self._metrics.increment("orders_submitted_total", labels={"broker": broker_id})
self._metrics.observe("order_latency_seconds", latency, labels={"operation": "submit"})
```

## 5. Distributed Tracing

OpenTelemetry integration:

| Span | Parent | Attributes |
|------|--------|------------|
| order_placement | — | correlation_id, instrument, side |
| risk_check | order_placement | approved, reason |
| venue_submit | order_placement | broker, order_id |
| fill_processing | order_placement | trade_id, price, qty |
| reconciliation | — | drift_count, severity |

Trace context propagated via correlation_id across all components.

## 6. Health Checks

### Component Health

```python
@dataclass
class ComponentHealth:
    component_id: ComponentId
    state: ComponentState
    metrics: dict[str, Any]
    last_error: str | None = None
```

### Built-In Health Checks

| Check | Pass Condition |
|-------|----------------|
| message_bus_healthy | Queue depth < threshold |
| data_adapter_connected | Broker WebSocket connected |
| execution_adapter_ready | Broker auth valid, reconciliation complete |
| strategy_running | StrategyEngine state == RUNNING |
| risk_model_operational | RiskGate bound and responsive |
| datalake_accessible | DuckDB query succeeds |

### Readiness vs Liveness

| Probe | Checks | Use |
|-------|--------|-----|
| Liveness | Process running, no deadlock | Restart if fails |
| Readiness | All components RUNNING, broker connected, reconciliation done | Route traffic if passes |

## 7. Audit Sink

Append-only audit log for compliance:

```python
class AuditSink(Protocol):
    def record(self, event: AuditEvent) -> None: ...
```

### AuditEvent

```python
@dataclass(frozen=True)
class AuditEvent:
    timestamp: Timestamp
    event_type: str
    correlation_id: CorrelationId | None
    actor: str                    # component or operator
    details: dict[str, Any]
    environment: Environment
```

Mandatory audit events: order commands, risk checks, venue submissions, fills, reconciliation, kill switch, config changes.

## 8. AlertingEngine

```python
class AlertingEngine(Component):
    def publish(self, alert: Alert) -> None: ...
```

| Alert | Trigger | Severity | Action |
|-------|---------|----------|--------|
| BrokerDisconnected | WS disconnect > 30s | WARNING | Reconnect policy |
| ReconciliationHighDrift | HIGH severity drift | CRITICAL | HALTED + operator notify |
| LossCircuitBreakerTripped | daily_pnl threshold | CRITICAL | HALTED |
| KillSwitchTripped | Manual or auto trip | CRITICAL | HALTED |
| QueueBackpressure | MessageBus queue > 80% | WARNING | Log + metric |
| ComponentError | Component state == ERROR | CRITICAL | HALTED |

AlertingEngine subscribes to MessageBus system/risk events. Alerts are logged, metered, and optionally forwarded to external notification channels.

## 9. Broker Health Monitoring

BrokerHealthMonitor (see spec 06) integrates with observability:

| Metric | Type | Labels |
|--------|------|--------|
| broker_connected | Gauge | broker_id |
| broker_reconnect_total | Counter | broker_id |
| broker_reconnect_latency_seconds | Histogram | broker_id |
| reconciliation_drift_total | Counter | severity |

Health endpoint includes broker_connected in readiness probe for Live/Paper modes.

## 10. Operational Dashboards

Recommended dashboard panels:

| Panel | Metrics |
|-------|---------|
| Order Flow | orders_submitted, filled, rejected rates |
| Latency | order_latency p50/p95/p99 |
| Risk | risk_rejected rate, kill switch status |
| Positions | position_count, unrealized_pnl |
| System | component_health, queue_depth, broker_connected |
| Reconciliation | drift_count by severity |

## 11. Observability Invariants

1. Every order path produces trace spans
2. Every order state transition produces audit record
3. Metrics exported via OpenTelemetry protocol
4. Health checks exposed on HTTP endpoint
5. No secrets in logs, metrics labels, or traces
6. Audit sink is append-only
7. Component health checked by LifecycleManager periodically
8. AlertingEngine publishes on all CRITICAL risk/system events
9. BrokerHealthMonitor metrics included in readiness probe
