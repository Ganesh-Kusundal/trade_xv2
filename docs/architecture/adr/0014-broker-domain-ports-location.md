# ADR-0014: Keep Broker Contracts in `domain/ports/`

## Status

Accepted — 2026-07-21

## Context

The broker hybrid facade program
(`docs/superpowers/specs/2026-07-21-broker-hybrid-facade-design.md`) delivers a
simple public API:

```python
from brokers import BrokerSession
session = BrokerSession.connect("dhan")
session.stock("RELIANCE").refresh()
session.gateway.place_order(...)
```

A proposed layout moved broker contracts into `domain/brokers/{models,contracts}.py`.
Constitution gap analysis (`docs/constitution/09-broker-subsystem-gap-analysis.md`)
already maps the subsystem constitution’s `I*` interfaces onto existing ports:

- `BrokerAdapter` / `BrokerMarketDataPort` / `BrokerExecutionPort` / `BrokerStreamingPort`
- `DataProvider` / `ExecutionProvider`
- `OrderTransportPort`

Relocating those ports into `domain/brokers/` would touch the protected domain
layer, import-linter contracts, and every consumer without changing behavior.

## Decision

1. **Keep broker contracts in `domain/ports/`** (and related `domain/capabilities/`).
2. **Do not** introduce `domain/brokers/` in this program.
3. Public product entry remains the `brokers` package facade (`BrokerSession`,
   `BrokerGateway`).
4. Revisit only if onboarding evidence shows glossary/port discovery pain that
   outweighs the migration cost — then open a dedicated ADR with a migration plan.

## Consequences

- Hybrid facade mental model stays simple without domain-layer churn.
- Glossary / constitution §09 remain the alias map for constitution `I*` names.
- Providers live under `src/brokers/providers/{dhan,upstox,paper}/`.
- Generic resilience/auth stay in `infrastructure/`.

## Related

- ADR-0002 (layer dependency rule)
- ADR-0012 (paper-only OMS boundary)
- Spec: `docs/superpowers/specs/2026-07-21-broker-hybrid-facade-design.md`
