# Import Direction Rules — Architectural Invariants

## Dependency flow

```
cli → brokers / analytics / datalake
domain ← brokers.common, analytics, datalake (types only)
brokers.dhan/upstox/paper → brokers.common + domain
```

## Rules

1. `domain/` MUST NOT import `brokers`, `analytics`, `datalake`, or `cli`
2. `analytics/` MUST NOT import `brokers.dhan`, `brokers.upstox`, or `brokers.paper`
3. `datalake/` SHOULD depend on `domain.repositories` protocols, not `brokers.common.oms` directly
4. `brokers.common` MUST NOT import broker adapters
5. Cross-broker imports are forbidden

## Enforcement

- `lint-imports` (import-linter) in CI
- `tests/architecture/` AST checks
- Ruff `banned-api` in `pyproject.toml`

## Canonical imports

Prefer:

```python
from domain import Order, OrderStatus
from domain.events import EventType
from domain.repositories import OrderRepository
```

Deprecated (shim cycle):

```python
from brokers.common.core.domain import Order  # forwards to domain
```
