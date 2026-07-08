# ADR-005: Brokers as Plugins; Domain Never Imports Infrastructure

## Status
Accepted (Phase 0)

## Context
The domain is the center of gravity. If it imports infrastructure or brokers, the
whole architectural inversion collapses and nothing downstream can be tested or
swapped independently.

## Decision
Hard rule (enforced by import-linter contracts):

1. `src/domain/**` imports nothing from `src/infrastructure`, `src/plugins`,
   `brokers`, `requests`, `websocket`, or JSON serialization.
2. Brokers are plugins implementing `src/domain/ports` and `src/domain/capabilities`.
3. `domain` may import only other `domain` modules.

Import-linter contracts:
- `Domain independence`: `domain` → forbids `brokers`, `analytics`, `datalake`,
  `cli`, `application`, `api`.
- `Public domain object API independence`: the public object layer
  (`domain.instruments`, `domain.options`, `domain.ports`, `domain.aggregates`,
  `domain.entities`, `domain.value_objects`, `domain.events`, `domain.capabilities`,
  `domain.extensions`, `domain.quotes`, `domain.candles`, `domain.orders`,
  `domain.executions`) → forbids `infrastructure` and all of the above.

## Consequences
- A pure in-memory `DataFrameDataProvider` can stand in for any broker in tests.
- `cli-no-broker-impl` contract holds: `cli` imports only `src/api`/`src/application`.
