# 13 — Migration Plan

## 1. Overview

This document outlines the phased migration from the current TradeXV2 codebase
to the V2 architecture. Each phase produces a working system — no phase requires
the next phase to be useful.

```
Phase 1: Foundation (Weeks 1-4)
Phase 2: Message Bus (Weeks 5-8)
Phase 3: Broker Adapters (Weeks 9-12)
Phase 4: Execution Engine (Weeks 13-16)
Phase 5: Data Engine (Weeks 17-20)
Phase 6: Strategy System (Weeks 21-24)
Phase 7: Observability (Weeks 25-28)
Phase 8: Production Hardening (Weeks 29-32)
```

## 2. Phase 1: Foundation (Weeks 1-4)

### Goals
- Extract domain layer into clean package structure
- Enforce import-linter contracts in CI
- Establish component lifecycle base class

### Tasks

**Week 1-2: Domain Extraction**
```bash
# Create domain package structure
mkdir -p src/domain/entities
mkdir -p src/domain/value_objects
mkdir -p src/domain/events
mkdir -p src/domain/commands
mkdir -p src/domain/ports
mkdir -p src/domain/services
mkdir -p src/domain/policies

# Move existing domain types
mv src/entities/* src/domain/entities/
mv src/value_objects/* src/domain/value_objects/
mv src/events/* src/domain/events/
```

- Extract `Order`, `Position`, `Trade`, `Quote`, `MarketDepth` into `domain/entities/`
- Extract `Price`, `Quantity`, `Money`, `Symbol`, `Exchange` into `domain/value_objects/`
- Extract domain events into `domain/events/`
- Create `domain/ports/` with Protocol definitions
- Ensure no framework imports in domain layer

**Week 3: Import-Linter**
```ini
# .importlinter
[importlinter]
root_packages = domain, application, infrastructure, runtime, interface

[importlinter:contract:1]
name = Domain purity
type = forbidden
source_modules = domain
forbidden_modules = application, infrastructure, runtime, interface
```

- Add import-linter to CI
- Fix all violations
- Document allowed dependencies

**Week 4: Component Lifecycle**
- Create `shared/messaging/component.py` with `Component` base class
- Implement state machine: UNINITIALIZED → INITIALIZED → RUNNING → STOPPED
- Add lifecycle tests

### Deliverables
- Clean domain layer with zero outer imports
- Import-linter passing in CI
- Component base class with tests

### Risk Mitigation
- Keep existing code working during migration
- Use feature flags for gradual rollout
- Run old and new code in parallel

## 3. Phase 2: Message Bus (Weeks 5-8)

### Goals
- Implement MessageBus with sync/async dispatch
- Migrate inter-component calls to message-based
- Add dead-letter queue

### Tasks

**Week 5-6: MessageBus Implementation**
- Implement `MessageBus` class in `shared/messaging/message_bus.py`
- Add sync and async dispatch
- Implement subscription management
- Add metrics collection

**Week 7: Dead-Letter Queue**
- Implement DLQ for failed deliveries
- Add DLQ replay mechanism
- Add DLQ monitoring

**Week 8: Migration**
- Identify all direct component calls
- Replace with message-based communication
- Test parity between old and new

### Deliverables
- MessageBus with full test coverage
- All inter-component calls via MessageBus
- DLQ with monitoring

## 4. Phase 3: Broker Adapters (Weeks 9-12)

### Goals
- Refactor broker module to Gateway → Connection → Sub-Adapters
- Reduce god-class degree from 376 to < 50
- Implement SymbolResolver

### Tasks

**Week 9-10: Dhan Refactor**
- Create `brokers/dhan/adapters/` directory
- Extract `DhanOrdersAdapter` from `DhanBroker`
- Extract `DhanMarketDataAdapter`
- Extract `DhanPortfolioAdapter`
- Extract `DhanInstrumentAdapter`
- Extract `DhanStreamingAdapter`
- Create `DhanConnection` that owns adapters
- Rename `DhanBroker` to `DhanGateway`

**Week 11: Upstox Refactor**
- Same pattern for Upstox
- Extract adapters, create connection, rename to gateway

**Week 12: SymbolResolver**
- Implement `SymbolResolver` in `brokers/common/`
- Migrate symbol resolution logic
- Ensure wire types don't leak

### Deliverables
- Dhan and Upstox refactored to new pattern
- Max class degree < 50
- SymbolResolver preventing wire type leakage

## 5. Phase 4: Execution Engine (Weeks 13-16)

### Goals
- Implement ExecutionEngine with FillSource protocol
- Create three FillSource implementations
- Achieve zero-parity across backtest/paper/live

### Tasks

**Week 13-14: ExecutionEngine**
- Implement `ExecutionEngine` in `application/execution/`
- Integrate with MessageBus
- Add risk check integration
- Add fill handling

**Week 15: FillSource Implementations**
- Implement `SimulatedFillSource` for backtest
- Implement `PaperFillSource` for paper trading
- Implement `BrokerFillSource` for live

**Week 16: Zero-Parity Verification**
- Write parity tests
- Verify same strategy produces same orders across modes
- Fix any discrepancies

### Deliverables
- ExecutionEngine with full test coverage
- Three FillSource implementations
- Zero-parity verified by tests

## 6. Phase 5: Data Engine (Weeks 17-20)

### Goals
- Implement DataCatalog with DuckDB + Parquet
- Implement DataEngine with source selection
- Implement LiveTickPipeline

### Tasks

**Week 17-18: DataCatalog**
- Implement `DataCatalog` in `datalake/catalog.py`
- Set up DuckDB schema
- Implement Parquet I/O
- Add query interface

**Week 19: DataEngine**
- Implement `DataEngine` in `application/data/`
- Implement source selection policy
- Add auto-sync capability

**Week 20: LiveTickPipeline**
- Implement `LiveTickPipeline` in `application/streaming/`
- Add tick buffering
- Add periodic flush to DataLake

### Deliverables
- DataCatalog with DuckDB + Parquet
- DataEngine with source selection
- LiveTickPipeline with buffering

## 7. Phase 6: Strategy System (Weeks 21-24)

### Goals
- Implement StrategyBase with lifecycle
- Implement BacktestEngine
- Implement ReplayEngine
- Implement PaperTradingEngine

### Tasks

**Week 21-22: StrategyBase**
- Implement `StrategyBase` in `application/strategy/`
- Add lifecycle hooks
- Add order methods (buy, sell, cancel)
- Add position queries

**Week 23: BacktestEngine**
- Implement `BacktestEngine` in `application/execution/`
- Integrate with SimulatedFillSource
- Add result collection

**Week 24: Replay & Paper**
- Implement `ReplayEngine` for tick replay
- Implement `PaperTradingEngine` with PaperFillSource
- Add example strategies

### Deliverables
- StrategyBase with full test coverage
- BacktestEngine with result reporting
- ReplayEngine and PaperTradingEngine
- Example strategy library

## 8. Phase 7: Observability (Weeks 25-28)

### Goals
- Implement structured logging with structlog
- Implement Prometheus metrics
- Implement health checks
- Implement distributed tracing

### Tasks

**Week 25-26: Logging & Metrics**
- Set up structlog configuration
- Implement MetricsRegistry
- Add key metrics to all components
- Add Prometheus endpoint

**Week 27: Health Checks**
- Implement HealthChecker
- Add built-in health checks
- Add `/health` endpoint

**Week 28: Tracing**
- Implement TraceContext
- Add correlation ID flow
- Add trace export

### Deliverables
- Structured logging throughout
- Prometheus metrics endpoint
- Health check system
- Distributed tracing

## 9. Phase 8: Production Hardening (Weeks 29-32)

### Goals
- Complete CI/CD pipeline
- Kubernetes deployment
- Monitoring stack
- Documentation

### Tasks

**Week 29-30: CI/CD**
- Complete GitHub Actions workflow
- Add Docker build
- Add Kubernetes deployment
- Add import-linter to CI

**Week 31: Monitoring**
- Set up Prometheus + Grafana
- Set up Loki for logs
- Create dashboards
- Set up alerting

**Week 32: Documentation & Testing**
- Write user guide
- Write developer guide
- Write API documentation
- Load testing
- Chaos testing

### Deliverables
- Full CI/CD pipeline
- Kubernetes deployment
- Monitoring stack
- Complete documentation

## 10. Migration Checklist

### Phase 1: Foundation
- [ ] Domain layer extracted
- [ ] Import-linter in CI
- [ ] Component lifecycle base class
- [ ] All domain tests passing

### Phase 2: Message Bus
- [ ] MessageBus implemented
- [ ] DLQ implemented
- [ ] All inter-component calls migrated
- [ ] MessageBus tests passing

### Phase 3: Broker Adapters
- [ ] Dhan refactored
- [ ] Upstox refactored
- [ ] SymbolResolver implemented
- [ ] Max degree < 50

### Phase 4: Execution Engine
- [ ] ExecutionEngine implemented
- [ ] Three FillSource implementations
- [ ] Zero-parity verified
- [ ] Execution tests passing

### Phase 5: Data Engine
- [ ] DataCatalog implemented
- [ ] DataEngine implemented
- [ ] LiveTickPipeline implemented
- [ ] Data tests passing

### Phase 6: Strategy System
- [ ] StrategyBase implemented
- [ ] BacktestEngine implemented
- [ ] ReplayEngine implemented
- [ ] PaperTradingEngine implemented
- [ ] Example strategies

### Phase 7: Observability
- [ ] Structured logging
- [ ] Prometheus metrics
- [ ] Health checks
- [ ] Distributed tracing

### Phase 8: Production
- [ ] CI/CD pipeline
- [ ] Docker + Kubernetes
- [ ] Monitoring stack
- [ ] Documentation

## 11. Rollback Strategy

Each phase is designed to be independently deployable. If a phase fails:

1. **Feature flags** — New code can be disabled without rollback
2. **Parallel run** — Old and new code run side-by-side during migration
3. **Database migrations** — All schema changes are reversible
4. **Gradual rollout** — New features rolled out to 10% → 50% → 100%

## 12. Success Metrics

| Metric | Target | Measurement |
|---|---|---|
| Max class degree | < 50 | graphify analysis |
| Import-linter violations | 0 | CI check |
| Test coverage | > 80% | pytest-cov |
| Zero-parity | Verified | Parity tests |
| CI pipeline time | < 10 min | GitHub Actions |
| Deployment frequency | Daily | Kubernetes |
| Mean time to recovery | < 5 min | Monitoring |
