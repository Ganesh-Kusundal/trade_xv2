# ADR-007: OMS-First Execution (Zero-Parity)

## Context

Live orders could bypass `OrderManager`, causing duplicate risk checks and
inconsistent audit trails between CLI, API, and orchestrator paths.

## Decision

1. All live/paper/replay placement flows through
   `OrderManager.place_order(command, submit_fn=...)`.
2. Broker gateways operate in **transport-only** mode when `transport_only=True`
   on `OrderRequest` / gateway `place_order`, skipping duplicate risk checks.
3. `BrokerService.submit_order` and `make_gateway_submit_fn()` are the canonical
   transport adapters for HTTP/API paths.

## Consequences

- One risk gate, one idempotency gate, one audit trail per order.
- Backtest/replay/paper share the same OMS code path as live submission.
- Architecture tests flag direct `gateway.place_order()` from CLI/API without OMS.
