# Reliability Assessment

## Verdict

The platform has retries, circuit breakers, health checks, reconnectors, reconciliation, alerts, and event persistence. They are fragmented, frequently best-effort, and not composed into one operational state machine. A process can remain “healthy” while trading is unsafe.

## Failure scenarios

### Ambiguous order write

1. Client submits an order.
2. Broker accepts it.
3. Network fails before the response.
4. Generic retry submits the POST again (`src/brokers/dhan/api/http_client.py:425-453`, `src/brokers/upstox/auth/http.py:305-387`).
5. Local idempotency cannot guarantee broker-side dedupe across processes.

Required behavior: persist an intent before submission, use a broker-supported idempotency key where available, classify the result as `UNKNOWN` on transport ambiguity, and reconcile before any retry.

### Event handler failure

EventBus logs/DLQs handler failures but continues when `fail_fast` is false (`src/infrastructure/event_bus/event_bus.py:423-517`). The order projection may advance while position/PnL or audit handlers fail. Required behavior: transactional ledger append, durable consumer checkpoints, explicit projection lag, and readiness failure for economically stale projections.

### Market-data outage

Socket connectivity, receipt timestamps, and callback delivery are not the same as fresh market data. Upstox timestamps can be local receipt times (`src/brokers/upstox/adapters/streaming_gateway.py:214-249`); Dhan has multiple reconnect loops. A callback exception can be swallowed while the feed appears connected (`src/brokers/dhan/data/data_provider.py:197-209`).

Required behavior: per-instrument freshness, sequence/gap detection, event-time validation, callback error counters, and a fail-closed decision gate.

### Recovery and reconciliation

Reconciliation currently compares incomplete state. Account refresh can swallow broker errors and mark the view refreshed (`src/domain/portfolio/account_view.py:70-101`). This risks interpreting a failed account read as no positions or zero funds.

Required behavior: `UNKNOWN` account state blocks new risk decisions; recovery must compare full economic state and leave an auditable discrepancy until resolved.

## Operational weaknesses

- `/healthz` can return HTTP 200 even when the registry is unhealthy; `/readyz` is separate and incomplete (`src/interface/api/routers/health.py:18-96`).
- Health checks run serially without timeout (`src/infrastructure/health.py:71-89`).
- Unknown brokers can pass health selection with no observations (`src/infrastructure/resilience/broker_health_monitor.py:137-147`).
- TLS readiness can pass when hardened sessions are absent (`src/application/services/production_readiness.py:363-394`).
- Alerts require an external polling loop and have no durable acknowledgement (`src/infrastructure/observability/alerting.py:156-176,285-317`).
- Session/audit/metrics failures can be swallowed, creating incomplete incident evidence.
- Circuit-breaker half-open mode is not concurrency-limited (`src/infrastructure/resilience/circuit_breaker.py:56-63,103-108`).
- Synchronous retry sleeps can exhaust worker capacity (`src/infrastructure/resilience/retry.py:130-151`).

## Target reliability model

Use one `TradingReadiness` state derived from:

`configuration → auth → broker connectivity → market-data freshness → order-stream continuity → account freshness → reconciliation clean → audit durable`

Each dependency has `READY`, `DEGRADED`, `UNKNOWN`, or `FAILED`. New entry orders require `READY`; emergency exits use a separately authorized policy. Recovery is a state transition with evidence, not a log message.
