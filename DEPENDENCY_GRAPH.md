# TradeXV2 - Comprehensive Dependency Graph

## 1. Architecture Overview

### Service Layer Dependencies (Critical Path)

ENTRY POINTS
  cli/main.py           datalake/api/main.py
        │                      │
        ▼                      ▼
  BrokerService    <-> TradingContext <-> OMS Core
        │                │         │
        │                │         ▼
        │                │    EventBus
        ▼                      │
  Lifecycle Manager ◄──────────┘

IMPLEMENTATIONS
brokers/dhan/main.py      brokers/upstox/      brokers/paper/
brokers/dhan/websocket     brokers/upstox/ws    brokers/paper/

## 2. Quant Bug Dependency Graph

### Critical Path for Quant Fixes

  OMS OPT-IN FIX
  (brokers/common/oms/)
  MUST BE SEQUENTIAL
        │
        ▼
LOOK-AHEAD CACHE FIX
OPTIONS BID/ASK MAPPING FIX
INDICATOR MISSING VALUES FIX

## 3. Parallel Development Opportunities

### Independent Modules (Safe Parallel Development)

| Module | Dependencies | Parallel Safe | Risk Level |
|--------|-------------|---------------|------------|
| CLI Commands | Gateway ABC, EventBus | Yes | LOW |
| API Routers | TradingContext, Gateway | Yes | LOW |
| Analytics Indicators | None (standalone) | Yes | LOW |
| Analytics Scanners | Indicators, DataLakeGateway | Yes | LOW |
| Broker Adapters | Gateway ABC | Yes | LOW |
| Tests Unit | None (mocked) | Yes | LOW |
| Tests Integration | Brokers, Services | Conditional | MEDIUM |

### Sequential Dependencies (Must Be Handled Carefully)

| Module | Must Complete Before | Reason |
|--------|---------------------|---------|
| TradingContext | Gateway ABC, OMS | Core state container |
| BrokerService | TradingContext | Service orchestration |
| FastAPI App | TradingContext | API wire-up |
| CLI Main | BrokerService | Entry point |
| OMS Mandatory Fix | None | Critical bug fix |

## 4. Critical Path Analysis (Production Deployment)

### Phase 0: Foundation (Sequential - Days 1-3)
1. brokers/common/gateway.py - Gateway ABC
2. brokers/common/oms/context.py - TradingContext
3. brokers/common/oms/order_manager.py - OMS Fix (zero-parity)
4. brokers/common/lifecycle.py - LifecycleManager

### Phase 1: Core Services (Parallel - Days 4-10)
5. Broker Adapters (Dhan, Upstox, Paper) - PARALLEL
6. ServiceContainer DI - PARALLEL
7. EventBus Enhancement - PARALLEL
8. Circuit Breakers - PARALLEL

### Phase 2: Applications (Parallel - Days 11-20)
9. CLI Commands - PARALLEL
10. API Routers - PARALLEL
11. Analytics Features - PARALLEL
12. WebSocket Services - PARALLEL

### Phase 3: Testing & Validation (Parallel - Days 21-30)
13. Unit Tests - PARALLEL
14. Integration Tests - PARALLEL (isolated)
15. Chaos Tests - PARALLEL
16. Performance Tests - PARALLEL

## 5. Risk Matrix

### High Risk Areas (Sequential Required)
| Area | Risk | Mitigation |
|------|------|------------|
| OMS State Management | Catastrophic | Fix before any caching |
| TradingContext Initialization | High | Must be atomic |
| EventBus Throughput | High | Backpressure needed |
| Security Boundary | Critical | Must be isolated |

### Medium Risk Areas (Parallel with Coordination)
| Area | Risk | Mitigation |
|------|------|------------|
| Broker Adapters | Medium | Shared test suite |
| API Routers | Medium | Shared mocks |
| CLI Commands | Medium | Gateway abstraction |
| Analytics Modules | Medium | Feature isolation |

### Low Risk Areas (Safe Parallel)
| Area | Risk | Mitigation |
|------|------|------------|
| Unit Tests | Low | Isolated |
| Documentation | Low | Standalone |
| Config Changes | Low | Environment specific |
| UI Components | Low | Frontend isolated |

## 6. Multi-Agent Parallel Execution Plan

### Agent 1: Architecture Agent
- Scope: Service graph, dependency injection, bounded contexts
- Parallel Safe: Yes
- Deliverable: Architecture diagram, service matrix

### Agent 2: Quant Bugs Agent
- Scope: Look-ahead bias, options pricing, indicators, slippage
- Parallel Safe: Conditional (needs OMS fix first)
- Deliverable: Quant bug report, fix priorities

### Agent 3: Code Quality Agent
- Scope: God classes, large methods, duplication
- Parallel Safe: Yes
- Deliverable: Code smell report, refactoring plan

### Agent 4: Testing Agent
- Scope: Test coverage, test pyramid, gaps
- Parallel Safe: Yes
- Deliverable: Testing gap analysis, recommendations

### Agent 5: Performance Agent
- Scope: Bottlenecks, latency, throughput
- Parallel Safe: Yes
- Deliverable: Performance analysis, optimization plan

### Agent 6: Reliability Agent
- Scope: Circuit breakers, failover, retry
- Parallel Safe: Conditional
- Deliverable: Reliability assessment, improvements

## 7. Implementation Timeline

### Week 1: Critical Fixes (Sequential)
Day 1-2: OMS Zero-Parity Fix
Day 3: Look-ahead Bias Fix
Day 4-5: Options Bid/Ask Fix
Day 6-7: Indicator Missing Values Fix

### Week 2-4: Parallel Development
Week 2: Broker Adapters + API Routers (Parallel)
Week 3: CLI Commands + Analytics (Parallel)
Week 4: Testing + Performance (Parallel)

### Week 5-6: Integration & Validation
Week 5: Integration Testing (Sequential)
Week 6: Chaos Testing + Production Readiness