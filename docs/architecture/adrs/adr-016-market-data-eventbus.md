# ADR-016: Market Data EventBus Canonical Path

- **Status:** Accepted
- **Date:** 2026-07-11
- **Deciders:** Market Data lane, Chief Architect

## Context

Dhan market feeds publish normalized ticks to `EventBus` via
`StreamOrchestrator` and `TickRouter`. Upstox streaming paths historically
delivered data through adapter callbacks without always publishing bus events,
creating asymmetric strategy behavior across brokers.

## Decision

1. **Canonical path:** all live normalized market data (`TICK`, `DEPTH*`,
   `QUOTE`) MUST be published to `DomainEventBus` before consumer delivery.
2. Broker adapters MAY use private callbacks internally, but the
   **application boundary** observes bus events only.
3. `StreamOrchestrator` owns subscription lifecycle events
   (`SUBSCRIPTION_STARTED`, `SUBSCRIPTION_ENDED`, degraded signaling).
4. Gap closure for Upstox is **Phase 5** (TRANS-P5-*) with contract test
   `test_live_candles_normalize_consistently` as parity evidence.

## Consequences

- Strategies and aggregators subscribe to bus — not broker WS types.
- Certification adds bus-publish assertion per broker stream mode.
- Until Upstox gap closed, doctor reports `advisory: bus_asymmetry`.

## Compliance

- `EVENT_CATALOG.md` § Market data
- Phase 5 streaming refactor tasks