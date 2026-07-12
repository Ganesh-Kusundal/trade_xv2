# ADR-014-OBS: OpenTelemetry + Prometheus + Structured Logging

## Status

Proposed

## Context

The trading platform needs production-grade observability to:

- Trace order lifecycle across multiple services (strategy → OMS → broker).
- Monitor latency, throughput, and error rates for critical paths.
- Debug production issues with structured, searchable logs.
- Alert on anomalies (DLQ backlog, order placement failures, feed disconnects).

The current observability is ad-hoc: `logging.getLogger` in business layers (partially gated by `test_production_code_fitness_rules.py`), no distributed tracing, and no metrics export.

## Decision

Adopt a three-pillar observability stack:

### 1. OpenTelemetry (Tracing)

- **Instrumentation:** Auto-instrument FastAPI, HTTP clients, SQLite queries.
- **Custom spans:** Order placement, strategy signal generation, event bus publish.
- **Context propagation:** W3C TraceContext across service boundaries.
- **Exporter:** OTLP to collector (Jaeger/Tempo for visualization).

### 2. Prometheus (Metrics)

- **Custom metrics:**
  - `order_placement_duration_seconds` (histogram)
  - `event_bus_dlq_depth` (gauge)
  - `broker_api_latency_seconds` (histogram)
  - `strategy_signal_count` (counter)
  - `market_data_feed_reconnect_count` (counter)
- **Scrape endpoint:** `/metrics` on API and worker services.
- **Alerting:** Prometheus Alertmanager for critical thresholds.

### 3. Structured Logging

- **Format:** JSON-structured logs with correlation IDs.
- **Levels:** Application uses `infrastructure.logging_config` (canonical, enforced by `test_production_code_fitness_rules.py`).
- **Correlation:** Each request/order gets a `trace_id` that propagates through all log entries.
- **Log aggregation:** ELK stack or Loki + Grafana.

### Observability Layer Placement

- Tracing: `infrastructure/observability/tracing/`
- Metrics: `infrastructure/metrics/registry.py`
- Logging: `infrastructure/logging_config.py`

All observability code lives in `infrastructure/`. Business layers access observability through injected ports, not direct imports (partially enforced by `test_application_no_infra_imports.py`).

## Consequences

**Positive:**
- End-to-end visibility across the order lifecycle.
- Data-driven alerting on critical trading metrics.
- Structured logs enable efficient production debugging.

**Negative:**
- Instrumentation adds ~2-5% latency overhead (acceptable for trading).
- Observability infrastructure must be deployed and maintained.
- Team must learn OpenTelemetry/Prometheus tooling.

## Enforcement

- `tests/architecture/test_application_no_infra_imports.py` — application doesn't import infrastructure observability
- `tests/architecture/test_production_code_fitness_rules.py` — `test_no_direct_logging` (business layer uses centralized logging)
- `tests/architecture/test_cross_cutting_concerns.py` — no bare token logging, no inline URLs
- **NEW:** `tests/architecture/test_observability_conventions.py` (proposed)
