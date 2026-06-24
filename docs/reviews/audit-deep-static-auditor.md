# Deep Static Analysis — Trade_XV2

**Agent:** deep-static-auditor  
**Date:** 2026-06-23  
**Context:** Architecture boundary leaks (AR-1–AR-5); EDA violations (EDA-1–EDA-5)

---

## Executive Summary

The codebase shows disciplined use of Decimal for risk calculations, explicit orchestration contracts, and thread-safe locking patterns in OMS. However, **three god-class modules** (OrderManager 631L, TradingContext 516L, TradingOrchestrator 585L) violate SRP, **broker adapters embed application-layer concerns**, and **error handling in event publishing uses silent swallow patterns** in adapter code.

---

## SOLID Violations

### Single Responsibility Principle (SRP)

| Class | Lines | Responsibilities | Severity | Location |
|-------|-------|------------------|----------|----------|
| OrderManager | 631 | Placement, risk gate, idempotency, persistence, event handlers, cancel, audit, metrics | High | `application/oms/order_manager.py` |
| TradingContext | 516 | EventBus wiring, OMS, PM, RM, reconciliation, replay, DLQ monitor, PnL reset, orchestrator hook | High | `application/oms/context.py` |
| TradingOrchestrator | 585 | Scanner→strategy→OMS, features, signals, sizing, kill switch, execution events | High | `application/trading/trading_orchestrator.py` |
| BrokerService | 434 | Gateway, lifecycle, OMS, execution, observability composition | Medium | `cli/services/broker_service.py` |
| IntelligentGateway | 578 | Multi-broker failover, health, routing | Medium | `brokers/common/intelligent_gateway.py` |

**Prescription:** Extract `OrderPlacementService`, `TradeRecordingService`, `EventReplayService` from OrderManager. Extract `ServiceWiringFactory` from TradingContext.

### Dependency Inversion Principle (DIP)

| Violation | Severity | Location | Prescription |
|-----------|----------|----------|--------------|
| Paper gateway imports concrete TradingContext | Critical | `brokers/paper/paper_gateway.py:25-26` | Depend on `BrokerGatewayPort` only; inject OMS at composition root |
| Upstox factory accepts RiskManager | High | `brokers/upstox/factory.py:18,33` | Risk belongs in application layer; pass via submit_fn |
| Dhan connection imports application.oms | High | `brokers/dhan/connection.py` | Remove upward import |
| Runtime imports CLI BrokerService | High | `runtime/trading_runtime_factory.py:78,94` | Extract neutral composition module |

### Open/Closed Principle (OCP)

| Finding | Severity | Location |
|---------|----------|----------|
| ExecutionModeAdapter is clean ABC | Pass | `application/execution/execution_mode_adapter.py:16-26` |
| Broker order adapters duplicate risk-check logic | Medium | `brokers/dhan/orders.py:261-277`, `brokers/upstox/orders/order_command_adapter.py` |
| Event type handling via string match in replay | Medium | `application/oms/context.py:508-512` |

---

## Code Smell Density

### Long methods

| Method | Approx Lines | Location |
|--------|-------------|----------|
| OrderManager.place_order | ~120 | `application/oms/order_manager.py:240-360` |
| TradingOrchestrator.on_candidate | ~80+ | `application/trading/trading_orchestrator.py` |
| IntelligentGateway routing | ~100+ | `brokers/common/intelligent_gateway.py` |

### Feature envy

| Finding | Location |
|---------|----------|
| PaperOrders manipulates OMS + PM directly | `brokers/paper/paper_orders.py:189-191` |
| UpstoxReconciliationService holds OMS ref | `brokers/upstox/broker.py:237` |

### Magic numbers/strings

| Finding | Severity | Location |
|---------|----------|----------|
| Risk defaults from domain constants | Pass | `application/oms/_internal/risk_manager.py:59-61` |
| Hardcoded reconciliation interval | Low | `cli/services/oms_setup.py:153` — `300.0` |
| AsyncEventBus maxsize=2000 | Low | `runtime/trading_runtime_factory.py:82` |

---

## Error Handling

| Pattern | Severity | Location |
|---------|----------|----------|
| EventBus never silently swallows handler failures | Pass | `infrastructure/event_bus/event_bus.py:11-17` |
| Upstox adapter swallows event publish errors | High | `brokers/upstox/orders/order_command_adapter.py:244-246` — `except Exception: return` |
| Dhan WS publish wrapped in try/except log | Medium | `brokers/dhan/websocket.py:1008-1009` |
| oms_setup defensive except on TradingContext build | Medium | `cli/services/oms_setup.py:169` — `except Exception` |

---

## Dead Code and Duplicates

| Duplicate | Locations |
|-----------|-----------|
| OMS test suites | `application/oms/tests/` + `brokers/common/oms/tests/` |
| Execution test suites | `application/execution/tests/` + `brokers/common/execution/tests/` |
| Shim re-exports | `brokers/common/oms/__init__.py`, `execution/__init__.py`, `orchestrator/__init__.py` |
| TradingOrchestrator shim | `application/execution/trading_orchestrator.py` (5 lines) |

---

## Type Annotation Completeness

| Area | Status |
|------|--------|
| Application layer | Good — typed dataclasses, protocols |
| Domain entities | Good |
| Brokers | MyPy reports ~499 errors (CI non-blocking) — `.github/workflows/ci.yml:40-54` |
| `# type: ignore` in context.py | Present | `application/oms/context.py:40-41` |

---

## Prioritized Findings by Consequence

| # | Finding | Principle | Risk if unfixed | Location |
|---|---------|-----------|-----------------|----------|
| 1 | Paper gateway embeds OMS | DIP, SRP | Paper/live parity broken; double position apply | `brokers/paper/paper_gateway.py:25-26` |
| 2 | OrderManager god class | SRP | Untestable paths; regression on any change | `application/oms/order_manager.py` |
| 3 | Silent event publish swallow | Error handling | Lost order events with no DLQ | `brokers/upstox/orders/order_command_adapter.py:244-246` |
| 4 | TradingContext owns too many concerns | SRP | Lifecycle bugs affect all subsystems | `application/oms/context.py` |
| 5 | Runtime→CLI coupling | DIP | API cannot bootstrap independently | `runtime/trading_runtime_factory.py:78,94` |

**Code Quality Score (internal): 6/10** — Good patterns in core OMS/risk; god classes and adapter violations degrade maintainability.
