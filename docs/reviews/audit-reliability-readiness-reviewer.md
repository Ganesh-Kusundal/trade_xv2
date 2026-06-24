# Reliability & Operational Readiness Audit — Trade_XV2

**Agent:** reliability-readiness-reviewer  
**Date:** 2026-06-23  
**Context:** All prior audit findings

---

## Executive Summary

Reliability primitives are well-designed: `LifecycleManager` with ordered start/stop, DLQ on handler failure, circuit breakers, kill switch, and idempotent trade processing. However, **SPOFs in composition root** (CLI-owned BrokerService), **broken API bootstrap import**, **non-persistent trade ledger**, and **Upstox live fill path failure** create production incident risk at market open.

---

## Phase 1: Single Points of Failure

| SPOF | Severity | Location |
|------|----------|----------|
| Single TradingContext writer per SQLite store | High | `application/oms/context.py:54-58` — documented, not enforced |
| CLI BrokerService as sole composition root | High | `runtime/trading_runtime_factory.py:78,94` |
| In-memory ProcessedTradeRepository | Critical | `application/oms/context.py:71-73` |
| In-memory broker idempotency caches | High | `brokers/dhan/orders.py:226-229` |
| Single EventBus instance per process | Medium | By design — no horizontal scaling |

---

## Phase 2: Failover Mechanisms

| Mechanism | Status | Location |
|-----------|--------|----------|
| IntelligentGateway multi-broker | Present | `brokers/common/intelligent_gateway.py` |
| Broker health monitor | Present | `brokers/common/resilience/broker_health_monitor.py` |
| Dhan WS reconnect with backoff | Present | `brokers/dhan/websocket.py:253-290` |
| Upstox WS lifecycle wrapper | Partial | `brokers/upstox/websocket/lifecycle_wrapper.py` |
| API failover if primary broker down | Partial | IntelligentGateway optional via env |

---

## Phase 3: Retry Strategies

| Retry | Idempotent? | Location |
|-------|-------------|----------|
| HTTP retry with backoff | Yes (GET); order POST uses idempotency key | `brokers/common/resilience/retry.py` |
| Unknown-order trade retry | Yes — ledger not marked | `application/oms/order_manager.py:426-434` |
| WS reconnect | Yes — events may duplicate; ledger must dedup | Dhan WS |
| EventLog replay on restart | **Risk** — duplicates if ledger empty | `application/oms/context.py:511-512` |

---

## Phase 4: Circuit Breakers

| CB | Present | Tested | Location |
|----|---------|--------|----------|
| HTTP circuit breaker | Yes | Yes | `brokers/common/resilience/circuit_breaker.py` |
| Dhan HTTP client CB split | Yes | Yes | `brokers/dhan/tests/unit/test_http_client_circuit_breaker_split.py` |
| Kill switch (risk) | Yes | Yes | `application/oms/_internal/risk_manager.py` |
| Runaway strategy CB | Partial | Via daily loss limit only |

---

## Phase 5: Dead Letter Queues

| Aspect | Status | Location |
|--------|--------|----------|
| DLQ on handler failure | Yes | `infrastructure/event_bus/dead_letter_queue.py` |
| DLQ monitor on lifecycle | Yes | `application/oms/context.py:480-490` |
| DLQ depth alerting | Yes — logs warning every 60s | `context.py:483-487` |
| Failed orders to DLQ | No — only failed event handlers | Design limitation |
| DLQ replay procedure | Not documented in code | Gap |

---

## Phase 6: Health Checks

| Endpoint | Location | Accurate? |
|----------|----------|-----------|
| `/health`, `/readyz` | `api/routers/health.py` | Yes — container service checks |
| `/healthz`, `/readyz`, `/metrics` | `infrastructure/observability/http_server.py` | Yes — LifecycleManager + EventMetrics |
| RiskManager snapshot | `risk_manager.py:238-258` | Yes — kill_switch, daily_pnl |
| Dhan WS health | `brokers/dhan/websocket.py:900-908` | Yes — reconnect_count, message_count |

---

## Phase 7: Monitoring (Four Golden Signals)

| Signal | Implementation | Location |
|--------|---------------|----------|
| Latency | Partial — event metrics | `infrastructure/observability/event_metrics.py` |
| Traffic | Event counters | `event_metrics.py` |
| Errors | Handler error counts + DLQ | `event_bus.py:328-332` |
| Saturation | DLQ depth monitor | `context.py:483-487` |
| Business metrics | Trades processed/duplicated | `order_manager.py:447` |

---

## Phase 8: Alerting

| Aspect | Status | Location |
|--------|--------|----------|
| Threshold rules | Present | `infrastructure/observability/alerting.py` |
| Dedup | Present | `alerting.py` |
| Tests on canonical path | Shim path only | `brokers/common/observability/tests/test_alerting.py` |

---

## Phase 9: Recovery Procedures

| Scenario | Handled? | Gap |
|----------|----------|-----|
| Broker WS disconnect during market open | Dhan: reconnect | Upstox: no OMS update path |
| Order confirmation lost (network partition) | Partial — reconciliation | No automatic repair on CLI |
| Rate limit during strategy execution | Backoff in HTTP client | No strategy-level pause |
| Token expiry during active trading | Dhan token scheduler | Upstox TOTP scheduler unit tested only |
| DB drop during position update | SQLite in-process | Single-writer; no failover |
| Graceful shutdown | Yes | `infrastructure/lifecycle/lifecycle.py`, `api/main.py` lifespan |
| Crash recovery via EventLog replay | **Risk** | Ledger not persisted → duplicate trades |
| Stale event_bus import breaks API bootstrap | **Broken** | `runtime/trading_runtime_factory.py:77` |

---

## Market-Open Scenario Simulation

```
T+0  Market opens, Dhan WS connected
T+1  Partial fill: cumulative qty published as incremental → position 2x actual
T+2  Upstox order placed via OMS, fill arrives on portfolio_stream → OMS ignores
T+3  Process crash, EventLog replay → TRADE re-applied (empty ledger)
T+4  Operator sees position drift, reconciliation reports drift, auto_repair=False
```

---

## Top Findings

| # | Finding | Severity | Location |
|---|---------|----------|----------|
| 1 | Trade ledger not persisted on CLI path | Critical | `cli/services/oms_setup.py:150-157` |
| 2 | API bootstrap broken import | Critical | `runtime/trading_runtime_factory.py:77` |
| 3 | Upstox fills never reach OMS | Critical | `brokers/upstox/websocket/portfolio_stream.py:127-138` |
| 4 | EventLog replay + empty ledger = duplicate trades | Critical | `application/oms/context.py:511-512` |
| 5 | Single-writer not enforced at runtime | High | `application/oms/context.py:54-58` |
| 6 | CLI as composition SPOF | High | `runtime/trading_runtime_factory.py:78,94` |
| 7 | DLQ has no order-level failed submission routing | Medium | Design gap |
| 8 | Observability tests on shim path not canonical | Medium | `brokers/common/observability/tests/` |

**Reliability Score (internal): 5/10** — Good primitives; persistence and live-path gaps undermine recovery.
