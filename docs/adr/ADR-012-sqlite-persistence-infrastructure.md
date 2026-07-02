# ADR-012: SQLite Persistence Relocation to Infrastructure Layer

**Status**: Accepted  
**Date**: 2026-07-02  
**Authors**: Chief Quant Architect  
**Labels**: architecture, infrastructure, persistence

## Context

`SqliteOrderStore` (including the OMS writer lock mechanism) was located at `application/oms/persistence/sqlite_order_store.py`. This placed concrete SQLite I/O operations in the application layer, violating Clean Architecture: the application layer should contain only orchestration logic and depend on abstractions (ports), not concrete infrastructure implementations.

The application layer should define *what* needs to be stored (via port interfaces), while the infrastructure layer decides *how* to store it (SQLite, PostgreSQL, file-based, etc.).

## Decision

Move `SqliteOrderStore` and `OmsWriterLockError` to `infrastructure/persistence/sqlite_order_store.py` as the canonical location. The original `application/oms/persistence/sqlite_order_store.py` becomes a backward-compatible re-export shim.

**Canonical location:**
```python
from infrastructure.persistence.sqlite_order_store import SqliteOrderStore
```

**Backward-compatible re-export:**
```python
# application/oms/persistence/sqlite_order_store.py (shim)
from infrastructure.persistence.sqlite_order_store import SqliteOrderStore
```

The application layer's `context.py` and `order_manager.py` now import `SqliteOrderStore` from `infrastructure.persistence`, which is tracked as known debt in the import-linter `application-infrastructure-separation` contract. Future work should introduce a port interface so the application layer depends only on abstractions.

## Consequences

### Positive
- SQLite I/O is now correctly categorized as infrastructure
- Application layer no longer contains concrete database operations
- Clear path for future port-based dependency injection

### Negative
- Application layer still imports from infrastructure (tracked as debt)
- Backward-compat shim adds indirection

### Risks
- Future developers may add more infrastructure to application/oms/persistence — mitigated by import-linter contracts

## Alternatives Considered

### Alternative 1: Introduce a port interface immediately
**Description**: Create `OrderStorePort` in domain ports, have `SqliteOrderStore` implement it, inject via composition root.  
**Why Deferred**: The port interface already exists conceptually (`application/oms/protocols.py`). Full DI wiring is a larger refactor tracked for a future iteration.

### Alternative 2: Keep in application layer
**Why Rejected**: Concrete SQLite operations in the application layer violate the dependency rule. The application should not know about storage technology.

## Implementation Notes

- [x] Create `infrastructure/persistence/` package
- [x] Move `sqlite_order_store.py` to infrastructure
- [x] Replace original with backward-compat re-export shim
- [x] Update all import sites (context.py, order_manager.py, tests)
- [ ] Introduce port-based DI to eliminate application→infrastructure direct imports

## Related ADRs

- [ADR-001](./ADR-001-domain-single-source.md) — Domain as single source of truth
- [ADR-007](./ADR-007-oms-first-execution.md) — OMS-first execution model

---
