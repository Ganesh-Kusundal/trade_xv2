# ADR-009: ExecutionService Facade

## Context

ADR-007 established OMS-first execution via `OrderManager.place_order(command,
submit_fn=...)`. Callers (CLI, API, orchestrator) each wired `submit_fn`
independently, creating drift risk and bypass paths.

## Decision

1. Add `ExecutionService` in `brokers/common/execution/execution_service.py`.
2. Live mode uses `make_gateway_submit_fn(gateway, transport_only=True)` internally.
3. Paper/replay modes delegate to existing `ExecutionModeAdapter` implementations.
4. `BrokerService.execution_service` is the composition-root accessor for live trading.

## Consequences

- Single facade for place/cancel through OMS across presentation layers.
- Orchestrator may accept optional `execution_service` instead of raw `submit_fn`.
- `PlaceOrderUseCase` is intentionally not added to avoid a third orchestration path.
