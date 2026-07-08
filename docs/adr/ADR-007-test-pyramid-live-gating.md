# ADR-007: Test Pyramid & Live Gating

## Status
Accepted (Phase 0)

## Context
Real broker connections are necessary for certification, but placing real orders
and hitting live endpoints in CI is unsafe and expensive.

## Decision
Full pyramid, mapped to pytest markers:

| Layer | Network | Markers |
|---|---|---|
| Unit | none | default |
| Property-based | none | `property` |
| Component | mock/double | `component` |
| Contract (per plugin) | mock/double | `contract`, `dhan`, `upstox_integration` |
| Integration | mock adapter | `integration` |
| E2E | real (gated) | `e2e`, `live_readonly`, `upstox_live_readonly`, `off_market_safe` |
| E2E live orders | real (gated) | `live_orders` (needs `TRADEX_LIVE_ORDERS=1`) |
| Performance | bench | `performance` |
| Stress | bench | `stress` |
| Mutation | — | `mutation` |

Live gating:
- `TRADEX_LIVE_TESTS=1` enables read-only live endpoints (validated by
  `CredentialValidator.broker_available(name)`).
- `TRADEX_LIVE_ORDERS=1` (separate flag) enables **guarded** real order placement:
  1-lot INTRADAY, marketable→immediate cancel, idempotency correlation id, assert
  cancel before fill assertions. Never set in CI.

New markers added in Phase 0: `live_orders`, `property`, `component`, `mutation`.

## Consequences
- `pytest tests/ -m "not integration and not live"` is the default safe gate.
- Real-money paths are explicit, gated, and self-cancelling.
