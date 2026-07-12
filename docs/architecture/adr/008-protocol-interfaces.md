# ADR-008: Protocol-Based Interfaces Over ABCs

## Status

Accepted

## Context

Python's `abc.ABC` has a long history but introduces class hierarchy overhead and requires explicit inheritance. For a trading platform where interfaces are defined in `domain/ports/`, the interface mechanism should:

1. Be lightweight (no base class required).
2. Support structural subtyping (duck typing with static analysis).
3. Work with `isinstance` / `issubclass` at runtime when needed.
4. Be compatible with `mypy` and `pyright` structural type checking.

## Decision

Use **`typing.Protocol`** for all domain port interfaces:

- `domain/ports/broker_adapter.py` — `MarketDataAdapter`, `ExecutionAdapter` protocols
- `domain/ports/protocols.py` — general service protocols
- `domain/ports/market_data.py` — market data provider protocol

Concrete implementations (broker adapters, infrastructure services) satisfy protocols structurally — they don't need to inherit from the protocol class. This is the standard Python approach (PEP 544).

### Exception: BrokerGateway

`BrokerGateway` classes use `abc.ABC` (or concrete class hierarchies) because they expose a **frozen public surface** that is enforced by test (`test_gateway_surface_freeze.py`). The gateway API surface is intentional and explicit, not structural.

## Consequences

**Positive:**
- Domain ports have zero runtime overhead.
- Structural subtyping allows broker adapters to implement ports without import dependency on `domain.ports`.
- Static type checkers can validate protocol conformance.

**Negative:**
- `isinstance` checks against protocols require `runtime_checkable` decorator (used selectively).
- Structural conformance errors are caught at type-check time, not import time.

## Enforcement

- `tests/architecture/test_domain_isolation.py` — domain layer independence (ports have no outward imports)
- `tests/architecture/test_domain_ports_forbid_tradex_imports.py` — ports don't import composition root
- `tests/architecture/test_gateway_surface_freeze.py` — gateway surface uses explicit class hierarchy
