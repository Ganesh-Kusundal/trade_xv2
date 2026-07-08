# ADR-002: Domain Ports as the Only Broker Contract

## Status
Accepted (Phase 0)

## Context
Brokers previously exposed bespoke gateways/manager objects that domain and
application code imported directly, creating hard coupling and broker
conditionals throughout the codebase.

## Decision
The **only** contract a broker must satisfy is a set of domain-defined protocols
in `domain/ports` (the target `src/domain/ports`):

- `MarketDataProvider` — quotes, ltp, depth, history, option chain, subscription.
- `ExecutionProvider` — order placement/modification/cancellation, fills.
- `Subscription` — streaming lifecycle (`subscribe`/`unsubscribe`/`is_active`).

Brokers implement these ports as **plugins** (`src/plugins/<broker>/`). No code
outside `src/plugins` and `src/infrastructure` may import `brokers.*`.

## Consequences
- Domain and application never name a specific broker.
- Adding a broker = implementing the ports + registering capabilities; no changes
  to domain/app.
- The old `brokers/common/gateway.py` / `gateway_interfaces.py` are deleted and
  replaced by these ports.
