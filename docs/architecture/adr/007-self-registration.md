# ADR-007: Broker Self-Registration at Import Time

## Status

Accepted

## Context

The plugin-based broker architecture (ADR-001) requires a discovery mechanism. When a broker package is imported, it should register its adapters with the `BrokerExtensionRegistry` without requiring explicit registration calls from the composition root. This enables the "open for extension, closed for modification" principle: adding a new broker requires only adding the package, not editing a central registry.

## Decision

Broker packages **self-register** at import time via their `__init__.py`:

1. `src/brokers/dhan/__init__.py` — registers Dhan data + execution adapters via `BrokerExtensionRegistry`.
2. `src/brokers/upstox/__init__.py` — registers Upstox data + execution adapters.
3. `src/brokers/paper/__init__.py` — registers paper data + execution adapters.

The registration pattern:

```python
# In brokers/dhan/__init__.py
# ── Extension + data/execution self-registration (ADR-007) ──
from infrastructure.adapter_factory import register_broker
register_broker("dhan", DhanDataAdapter(), DhanExecutionAdapter())
```

The `infrastructure/adapter_factory.py` module maintains the canonical registry and provides the `register_broker` entry point. The path out of domain objects and out of `brokers.common` entirely is explicit.

### Import-time registration constraint

Registration happens at module import time, not at runtime. This means the broker package must be importable without side effects beyond registration. The `tests/architecture/test_broker_kernel_guardrails.py` test verifies this invariant.

## Consequences

**Positive:**
- Adding a new broker requires zero edits to the composition root or any central file.
- Registration is discoverable — the `__init__.py` is the single entry point.
- The composition root imports the broker package, triggering registration automatically.

**Negative:**
- Import-time side effects can be surprising (mitigated by making registration idempotent).
- Lazy loading of broker packages requires explicit import in the composition root.

## Enforcement

- `tests/architecture/test_import_direction_and_layering.py` — `test_brokers_init_only_exports_common_types`, `__all__` declarations
- `tests/architecture/test_broker_kernel_guardrails.py` — registration invariants
- `tests/architecture/test_public_sdk_surface_invariants.py` — `test_broker_gateways_importable`
