# ADR-001: Plugin-Based Broker Architecture

## Status

Accepted

## Context

The trading platform needs to support multiple Indian brokers (Dhan, Upstox, and future additions) without tight coupling to any specific broker implementation. The original design had broker-specific logic scattered across `brokers/common/`, creating implicit dependencies and making it difficult to add or remove broker support without touching shared code.

The core problem: how do we make broker implementations composable, independently testable, and removable without touching the core trading engine?

## Decision

Adopt a **plugin-based broker architecture** where each broker is a self-contained package under `src/brokers/<name>/` that:

1. Exports a `BrokerPlugin` (or equivalent extension) defining data adapters and execution adapters.
2. Registers itself with a `BrokerExtensionRegistry` at import time (see ADR-007).
3. Declares its capabilities via metadata (not name-based branching — see ADR test `test_no_broker_name_branching.py`).
4. Exposes a frozen public surface via `BrokerGateway` (see `test_gateway_surface_freeze.py`).

The registry maps broker IDs to extension descriptors; the OMS, certification suite, and rate limiter dispatch on **capabilities**, never on broker name strings.

### Package layout

```
src/brokers/
├── common/          # Shared contracts, capabilities, OMS margin helpers
├── dhan/            # Dhan-specific: wire, execution, data adapters
├── upstox/          # Upstox-specific: wire, execution, data adapters
├── paper/           # Synthetic paper broker for backtest/paper-trading
├── certification/   # Unified cert suite (dispatches via capabilities)
├── diagnostics/     # Doctor schema
├── cli/             # CLI broker facade
├── mcp/             # MCP broker tools
└── services/        # Core services (run_verify, run_certify, run_doctor)
```

## Consequences

**Positive:**
- Adding a new broker requires zero edits to OMS, certification, or rate limiter.
- Each broker is independently testable and deployable.
- Brokers cannot import from each other (enforced by `test_import_direction_and_layering.py`).

**Negative:**
- Initial boilerplate for new broker packages.
- Capability metadata must be kept in sync with actual adapter implementations.

## Enforcement

- `tests/architecture/test_import_direction_and_layering.py` — broker isolation rules
- `tests/architecture/test_no_broker_name_branching.py` — capability-driven dispatch
- `tests/architecture/test_gateway_surface_freeze.py` — frozen gateway API surface
- `tests/architecture/test_broker_kernel_guardrails.py` — broker kernel constraints
