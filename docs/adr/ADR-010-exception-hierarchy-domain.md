# ADR-010: Platform Exception Hierarchy in Domain Layer

**Status**: Accepted  
**Date**: 2026-07-02  
**Authors**: Chief Quant Architect  
**Labels**: architecture, domain

## Context

The root exception class `TradeXV2Error` was defined in `brokers/common/resilience/errors.py`, an outer-layer broker module. This violated Clean Architecture dependency rules: the domain layer (inner) must not depend on the brokers layer (outer), yet all platform-wide exception handling required importing from the brokers layer.

The application layer, infrastructure layer, and even domain consumers all needed the root exception type, creating an inverted dependency where inner layers depended on outer layers.

## Decision

Move the platform-level exception hierarchy (`TradeXV2Error`, `DataError`, `ConfigError`, `ValidationError`) to `domain/exceptions.py` as the canonical location. The `brokers/common/resilience/errors.py` module retains broker-specific exceptions (`BrokerError`, `RetryableError`, etc.) that inherit from `domain.exceptions.TradeXV2Error`, and re-exports the platform exceptions for backward compatibility.

**Canonical imports:**
```python
from domain.exceptions import TradeXV2Error, DataError, ConfigError, ValidationError
```

**Backward-compatible re-exports:**
```python
# brokers/common/resilience/errors.py re-exports for existing code
from domain.exceptions import TradeXV2Error, DataError, ConfigError, ValidationError
```

## Consequences

### Positive
- Domain layer is now self-contained for platform-level abstractions
- Application and infrastructure layers import from domain (correct direction)
- Broker-specific exceptions still extend the platform root (correct inheritance)
- Backward-compatible re-exports prevent breaking existing imports

### Negative
- Two valid import paths exist temporarily (canonical + re-export)
- Migration requires updating import sites across the codebase over time

### Risks
- New developers may import from the old location — mitigated by import-linter contracts

## Alternatives Considered

### Alternative 1: Keep exceptions in brokers layer
**Why Rejected**: Violates Clean Architecture — inner layers cannot depend on outer layers.

### Alternative 2: Create a separate `platform` package
**Why Rejected**: Unnecessary package proliferation. The domain layer is the natural home for platform-wide abstractions.

## Implementation Notes

- [x] Create `domain/exceptions.py` with core exception classes
- [x] Update `brokers/common/resilience/errors.py` to import from domain and re-export
- [x] Update all infrastructure and application import sites
- [ ] Deprecate re-export path in a future release

## Related ADRs

- [ADR-001](./ADR-001-domain-single-source.md) — Domain as single source of truth
- [ADR-011](./ADR-011-domain-event-canonical-imports.md) — Domain event canonical imports

---
