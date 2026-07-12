# ADR-017: Single Composition Root

- **Status:** Accepted
- **Date:** 2026-07-11
- **Deciders:** Runtime lane, Chief Architect

## Context

Multiple entry points wire dependencies today:

- `tradex.open_session()`
- `TradingRuntimeFactory.build_from_broker_service()`
- `interface.ui.services.oms_bootstrap`
- `infrastructure.gateway.factory`

This fragments lifecycle, tracing, and test doubles.

## Decision

1. **Target:** `runtime.factory.build(mode, transport, …)` is the sole
   composition root for production paths (Phase 5).
2. **Transitional:** existing factories remain as **thin delegates** with
   documented removal conditions in `RUNTIME_KERNEL.md`.
3. All entry points (`tradex`, CLI `connect`, API lifecycle) call the same
   builder within one release after Phase 5 cutover.
4. `TradingContext` registration stays process-singleton; duplicate register
   is a test/architecture failure.

## Consequences

- New features inject ports at `runtime.factory`, not in UI commands.
- `infrastructure.gateway.factory` stays private to runtime (import-linter).
- Phase 5 deletes duplicate wiring once parity tests pass.

## Alternatives rejected

- Monolithic `Runtime` god-object — violates bounded contexts
- UI-owned OMS bootstrap long-term — breaks headless/SDK parity

## Compliance

- `RUNTIME_KERNEL.md`, TRANS-P5 composition tasks