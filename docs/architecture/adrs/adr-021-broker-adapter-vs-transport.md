# ADR-021: BrokerAdapter (app) vs BrokerTransport (wire)

**Status:** Accepted  
**Date:** 2026-07-12  
**Related:** ADR-013, ADR-014, TOS-P1-001, DR-B5/B6

## Context

Two overlapping "unified port" abstractions existed:

- `domain.ports.broker_adapter.BrokerAdapter` — Protocol combining data + execution for application/domain callers (`InstrumentId`, `OrderRequest`).
- `domain.ports.broker_transport.BrokerTransport` — ABC for low-level wire/transport (reconnect, raw subscribe).

Wire adapters historically exposed `(symbol, exchange)` string methods, allowing call sites to bypass typed ports.

## Decision

1. **Application-facing contract:** `BrokerAdapter` (and the focused `DataProvider` / `ExecutionProvider` Protocols) are the only ports that `application` and `domain` may depend on.
2. **Wire contract:** `BrokerTransport` (and broker-specific wire adapters) are infrastructure/broker concerns. They may use string identifiers at the wire edge only.
3. **Forbidden:** `application` and `domain` must not call wire methods with bare `(symbol, exchange)` string signatures on concrete adapters.
4. **Enforcement:** architecture tests + import-linter; composition root wires adapters that implement the Protocols.

## Consequences

- Adding a broker means implementing ports + registering a plugin, not editing OMS.
- Wire signature divergence is contained to the broker package.
- Existing `BrokerTransport` remains for reconnect/stream plumbing; it is not the OMS order path.
