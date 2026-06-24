# Broker Adapter Audit — Trade_XV2

**Agent:** broker-auditor  
**Date:** 2026-06-23  
**Context:** Architecture AR-3; EDA EDA-1–5; Static DIP violations in adapters

---

## Executive Summary

The broker layer has strong resilience primitives (circuit breakers, retry with backoff, rate limiters) and a clean `transport_only` pattern via `gateway_submit.py`. Dhan has the most complete WS reconnection and event publishing. **Upstox live fill path is broken** (wrong event contract, no TRADE events). **Paper adapter violates ports/adapters discipline** by embedding OMS and double-applying positions. **Dhan partial fill math is wrong** (cumulative qty treated as incremental).

---

## Adapter Interface Contracts

| Port | Location | Implemented By |
|------|----------|----------------|
| OrderTransportPort | `domain/ports/broker_gateway.py` | Dhan/Upstox/Paper gateways |
| transport_only submit_fn | `application/execution/gateway_submit.py:37-59` | ExecutionService, BrokerService |

**Clean pattern:** `make_gateway_submit_fn(gateway, transport_only=True)` — risk enforced once in OMS.

| Finding | Severity | Location |
|---------|----------|----------|
| transport_only respected in Dhan | Pass | `brokers/dhan/orders.py:262` — skips risk when `transport_only` |
| transport_only wired in BrokerService | Pass | `cli/services/broker_service.py:372-379` |
| Upstox adapter publishes events outside OMS | High | `brokers/upstox/orders/order_command_adapter.py:247-254` |
| Paper gateway constructs TradingContext | Critical | `brokers/paper/paper_gateway.py:25-26` |

---

## Per-Broker Assessment

### Dhan

| Check | Status | Evidence |
|-------|--------|----------|
| WS reconnection with backoff | Pass | `brokers/dhan/websocket.py:253-290` — exponential backoff, reset on success |
| ORDER_UPDATED + TRADE event publish | Pass (shape) | `brokers/dhan/websocket.py:986-1007` |
| TRADE qty semantics | **Fail** | `websocket.py:991-1001` — cumulative `filled_quantity` used as trade qty |
| Idempotency cache on correlation_id | Partial | `brokers/dhan/orders.py:226-229` — in-memory only |
| Token lifecycle | Pass | `brokers/dhan/token_manager.py`, `token_scheduler.py` |
| Rate limit handling | Pass | `brokers/dhan/http_client.py` + resilience layer |
| Reconciliation | Present | `brokers/dhan/reconciliation.py` |

### Upstox

| Check | Status | Evidence |
|-------|--------|----------|
| WS reconnection | Partial | `brokers/upstox/websocket/lifecycle_wrapper.py` — lifecycle managed |
| ORDER_UPDATED canonical Order | **Fail** | `brokers/upstox/websocket/portfolio_stream.py:134-138` — raw payload |
| TRADE events | **Absent** | Zero TRADE publishes under `brokers/upstox/` |
| Kill switch adapter | Present | `brokers/upstox/kill_switch/adapter.py` — no dedicated integration test |
| Order command adapter | Partial | `brokers/upstox/orders/order_command_adapter.py` — duplicate risk + events |
| OMS coupling in broker | High | `brokers/upstox/broker.py:237` — `UpstoxReconciliationService(..., oms=self._oms)` |
| Static IP client | Present | `brokers/upstox/static_ip/client.py` |

### Paper

| Check | Status | Evidence |
|-------|--------|----------|
| Simulated fills via OMS | Partial | Uses OMS but bypasses event contract |
| Double position apply | **Fail** | `brokers/paper/paper_orders.py:189-191` |
| Mock broker imports TradingContext | Critical | `brokers/paper/mock_broker.py:9` |
| Contract tests | Pass | `brokers/paper/tests/contract/test_paper_contract.py` |

### Shared (brokers/common)

| Component | Status | Location |
|-----------|--------|----------|
| Gateway abstraction | Present | `brokers/common/gateway.py` |
| IntelligentGateway failover | Present | `brokers/common/intelligent_gateway.py` (578 lines) |
| Circuit breaker | Present | `brokers/common/resilience/circuit_breaker.py` |
| Retry + backoff | Present | `brokers/common/resilience/retry.py`, `backoff.py` |
| Broker health monitor | Present | `brokers/common/resilience/broker_health_monitor.py` |

---

## Critical Rules Assessment

| Rule | Status | Evidence |
|------|--------|----------|
| No stub returning fake data in prod path | Pass | Paper explicitly marked as paper mode |
| No provider-specific fields outside adapter | Pass | Domain entities used at OMS boundary |
| Typed exception handling | Partial | Dhan `exceptions.py`; Upstox `auth/exceptions.py`; some bare `except Exception` |
| Streaming handler reconnection | Pass (Dhan) / Partial (Upstox) | See above |
| Sandbox/paper must not validate prod paths | Risk | Paper OMS path deviates from live contract |

---

## Order Lifecycle Completeness

| Scenario | Dhan | Upstox | Paper |
|----------|------|--------|-------|
| Place order | Yes | Yes | Yes |
| Partial fill | **Broken qty** | No WS path | Double apply |
| Cancel | Yes | Yes | Yes |
| Reject | Yes | Yes | Yes |
| Reconciliation | Yes | Partial | N/A |

---

## Top Findings

| # | Finding | Severity | Location |
|---|---------|----------|----------|
| 1 | Dhan cumulative fill as incremental trade | Critical | `brokers/dhan/websocket.py:991-1001` |
| 2 | Upstox WS incompatible with OMS | Critical | `brokers/upstox/websocket/portfolio_stream.py:127-138` |
| 3 | No Upstox TRADE events | Critical | `brokers/upstox/` (grep: no TRADE publish) |
| 4 | Paper double position apply | Critical | `brokers/paper/paper_orders.py:189-191` |
| 5 | Paper gateway embeds OMS | Critical | `brokers/paper/paper_gateway.py:25-26` |
| 6 | Upstox duplicate ORDER_PLACED | High | `brokers/upstox/orders/order_command_adapter.py:247-254` |
| 7 | In-memory broker idempotency caches | High | `brokers/dhan/orders.py:226-229` |
| 8 | Upstox broker holds OMS ref | High | `brokers/upstox/broker.py:237` |

**Broker Score (internal): 4/10** — Dhan infrastructure solid but fill math wrong; Upstox live path non-functional for OMS; Paper violates adapter contract.
